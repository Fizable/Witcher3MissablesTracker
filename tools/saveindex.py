"""Index the save folder: per save, the quest journal status the game itself recorded.

Read-only. Caches to save_index.json so it can be resumed and re-queried.

  py saveindex.py build [--limit N]     build/update the cache (newest saves first)
  py saveindex.py show <quest> [...]    every save where those quests appear, with their statuses
  py saveindex.py gate <A> <B>          test "B starts only after A": does any save hold B without A done?
  py saveindex.py facts <save> <sub>    dump facts matching a substring from one save

Quest names are journal file short names, the same strings route.json uses in `files`
(e.g. q206berserkers, giant, q203him, q208heroesmead).
"""
import glob
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import save_reader as sr

from paths import HERE, QDB, SAVES

CACHE = HERE / "save_index.json"

PRESENT = ("Active", "Done", "Failed")


def quest_db():
    """journal short name -> [ (entry name, guid) ] ; first entry is the quest itself"""
    db = json.load(open(QDB))
    out = {}
    for key, val in db.items():
        short = os.path.basename(key).replace(".journal", "")
        out[short] = val["ids"]
    return out


def quest_table():
    """journal short -> (quest-level guid, [other entry guids]).

    The quest-level entry is the journal file's own CJournalQuest (REDkit), not quest_db's first id:
    quest_db's scan takes the first 'name GUID' string, which for 46 quests is a map pin or a
    description entry. Measured over 517 saves, reading the real quest entry fixes The Lord of Undvik
    and The King is Dead (0 -> 268 / 313 saves) and matches the journal for the rest.
    """
    db = quest_db()
    try:
        import questgraph as qg
        for key in qg.JOURNAL_DIR.glob("*.journal"):
            short = key.stem.lower()
            if short not in db:
                continue
            try:
                g = qg.G(key)
            except Exception:
                continue
            for e in g.p["exports"]:
                if e["className"] != "CJournalQuest":
                    continue
                gd = g.props(e["index"]).get("guid")
                if isinstance(gd, dict) and gd.get("raw_hex"):
                    db[short] = [[db[short][0][0] if db[short] else short, gd["raw_hex"]]] + db[short]
                break
    except Exception as ex:
        print(f"quest_table: REDkit journal read failed ({ex}); using quest_db order", flush=True)
    out = {}
    for short, ids in db.items():
        raw = ([ids[0][1]] if ids else []) + [g for _, g in ids]
        # keep everything in the save's own byte order so it can be compared with a save's journal guid
        out[short] = [g if "-" not in g else guid_raw(g) for g in raw]
    return out


def save_files():
    return sorted(glob.glob(os.path.join(SAVES, "*.sav")), key=os.path.getmtime)


def guid_raw(dashed):
    """quest_db's 'B5130AE1-468A2171-...' -> the save's raw 16 bytes as hex ('e10a13b5...')."""
    return b"".join(int(p, 16).to_bytes(4, "little") for p in dashed.split("-")).hex()


RANK = {"JS_Success": 3, "JS_Active": 2, "JS_Failed": 1}


def read_states(path, table):
    raw = sr.load_raw(path)
    names = sr.name_table(raw)
    entries = sr.journal(raw, names)
    by_guid = {}
    for e in entries:
        if e["guid"]:
            by_guid[e["guid"].lower()] = e["status"]
    st = {}
    for short, guids in table.items():
        if not guids:
            continue
        s = by_guid.get(guids[0].lower(), "")
        if s not in RANK:
            # the game leaves some quests' own entry inactive and moves a description/objective entry instead
            best = ""
            for g in guids[1:]:
                c = by_guid.get(g.lower(), "")
                if c in RANK and RANK[c] > RANK.get(best, 0):
                    best = c
            s = best
        st[short] = {"JS_Success": "Done", "JS_Active": "Active", "JS_Failed": "Failed"}.get(s, "Inactive")
    return st


def build(limit=None):
    table = quest_table()
    files = save_files()
    cache = json.load(open(CACHE)) if CACHE.exists() else {}
    cache = {k: v for k, v in cache.items() if "error" not in v}
    todo = [f for f in files if os.path.basename(f) not in cache]
    if limit:
        todo = todo[-limit:]
    print(f"{len(files)} saves, {len(cache)} cached, {len(todo)} to read", flush=True)
    t0 = time.time()
    for i, f in enumerate(todo, 1):
        try:
            cache[os.path.basename(f)] = {"mtime": os.path.getmtime(f), "state": read_states(f, table)}
        except Exception as ex:
            cache[os.path.basename(f)] = {"error": str(ex)}
        if i % 50 == 0 or i == len(todo):
            json.dump(cache, open(CACHE, "w"))
            print(f"  {i}/{len(todo)}  {time.time()-t0:.0f}s", flush=True)
    json.dump(cache, open(CACHE, "w"))
    bad = [k for k, v in cache.items() if "error" in v]
    print(f"done: {len(cache)} saves cached, {len(bad)} unreadable")
    return cache


def load():
    return json.load(open(CACHE))


def ordered(cache):
    return sorted(cache.items(), key=lambda kv: kv[1].get("mtime", 0))


def show(quests):
    cache = load()
    for name, v in ordered(cache):
        st = v.get("state")
        if not st:
            continue
        if all(st.get(q) in PRESENT for q in quests):
            print(f"{name:52s} " + "  ".join(f"{q}={st[q]}" for q in quests))


def gate(a, b):
    """Every save holding b, with a's status: any row where a is not Done refutes the gate."""
    cache = load()
    rows, violations, seen = [], [], 0
    for name, v in ordered(cache):
        st = v.get("state")
        if not st:
            continue
        if st.get(b) in PRESENT:
            seen += 1
            rows.append((name, st.get(a), st.get(b)))
            if st.get(a) != "Done":
                violations.append((name, st.get(a), st.get(b)))
    print(f"{b} present in {seen} saves")
    print(f"  {a} not Done in {len(violations)} of them")
    for r in violations[:20]:
        print(f"    VIOLATION {r[0]}  {a}={r[1]}  {b}={r[2]}")
    return violations


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "build":
        limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
        build(limit)
    elif cmd == "show":
        show(sys.argv[2:])
    elif cmd == "gate":
        gate(sys.argv[2], sys.argv[3])
    elif cmd == "facts":
        sub = sys.argv[3] if len(sys.argv) > 3 else ""
        raw = sr.load_raw(os.path.join(SAVES, sys.argv[2]))
        for k, v in sorted(sr.facts(raw).items()):
            if sub in k:
                print(k, v)


if __name__ == "__main__":
    main()
