"""Build the game-file start-gate index.

Scans every quest phase (.w2phase) in the REDkit data and records, for each journal entry path a
phase activates (CJournalQuestBlock / CJournalQuestTrackBlock), which phase file did it and at which
block. link a target to quest_db.json's per-journal entry list and a row is either

  quest-level   the activation adds the quest itself  -> that phase file STARTS that quest
  objective     the activation only updates an objective of it

This is the strict rule: it is what the game's own files do, not what the ordering of saves suggests.

  py gateindex.py build [--limit N]     build/update gate_index.json
  py gateindex.py quest <journal>       who activates <journal>, quest-level rows first
  py gateindex.py theirs <phase file>   what that phase file activates in other quests
"""
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cr2w

from paths import HERE, QUEST_ROOT, REDKIT_R4 as R4  # noqa: F401
from paths import QDB

CACHE = HERE / "gate_index.json"

START_BLOCKS = {"CJournalQuestBlock", "CJournalQuestTrackBlock"}


def guid_fmt(raw_hex):
    """REDkit CGUID bytes -> the dashed uppercase form quest_db.json uses."""
    b = bytes.fromhex(raw_hex)
    return "-".join(f"{int.from_bytes(b[4*k:4*k+4], 'little'):08X}" for k in range(4))


def quest_prefix(path):
    """q206_berserkers from any phase file of that quest."""
    m = re.match(r"^(q\d+_[a-z0-9_]+)", path.stem)
    return m.group(1) if m else path.stem


def scan(path):
    p = cr2w.parse(path)
    props_cache = {}

    def props(i):
        if i not in props_cache:
            props_cache[i] = {x["name"]: x["value"] for x in cr2w.props(p, p["exports"][i - 1])} if 1 <= i <= len(p["exports"]) else {}
        return props_cache[i]

    def chain(chunk):
        res, guids, i, guard = None, [], chunk, 0
        while i and 1 <= i <= len(p["exports"]) and guard < 12:
            ps = props(i)
            r = ps.get("resource")
            r = r.get("ref_import") if isinstance(r, dict) else r
            if r:
                res = r
            g = ps.get("guid")
            if isinstance(g, dict) and g.get("raw_hex"):
                guids.append(guid_fmt(g["raw_hex"]))
            ch = ps.get("child")
            i = ch.get("ref_chunk") if isinstance(ch, dict) else None
            guard += 1
        return res, guids

    rows = []
    for e in p["exports"]:
        if e["className"] not in START_BLOCKS:
            continue
        ps = props(e["index"])
        qe = ps.get("questEntry")
        chunk = qe.get("ref_chunk") if isinstance(qe, dict) else None
        if not chunk:
            continue
        res, guids = chain(chunk)
        if not res:
            continue
        lab = ps.get("comment") or ps.get("name") or ""
        rows.append({"src": str(path.relative_to(R4)), "src_quest": quest_prefix(path),
                     "class": e["className"], "block": e["index"],
                     "target": res, "leaf": guids[-1] if guids else None, "label": str(lab)[:80]})
    return rows


def build(limit=None):
    files = sorted(QUEST_ROOT.rglob("*.w2phase"))
    if limit:
        files = files[:limit]
    rows = json.load(open(CACHE)) if CACHE.exists() else []
    done = {r["src"] for r in rows}
    todo = [f for f in files if str(f.relative_to(R4)) not in done]
    print(f"{len(files)} phase files, {len(done)} scanned, {len(todo)} to go", flush=True)
    t0 = time.time()
    for i, f in enumerate(todo, 1):
        try:
            rows.extend(scan(f))
        except Exception as ex:
            print(f"  ! {f.name}: {ex}", flush=True)
        if i % 50 == 0 or i == len(todo):
            json.dump(rows, open(CACHE, "w"))
            print(f"  {i}/{len(todo)}  {time.time()-t0:.0f}s  rows={len(rows)}", flush=True)
    json.dump(rows, open(CACHE, "w"))
    print(f"done: {len(rows)} activation rows")
    return rows


def qdb():
    db = json.load(open(QDB))
    out = {}
    for key, val in db.items():
        short = os.path.basename(key).replace(".journal", "")
        out[short] = val["ids"]
    return out


def by_target(resource, db):
    """journal file path -> short name from quest_db"""
    base = os.path.basename(resource).replace(".journal", "")
    return base if base in db else None


def quest(journal):
    rows = json.load(open(CACHE))
    db = qdb()
    me = db.get(journal, [])
    quest_guid = me[0][1] if me else None
    print(f"{journal}: quest-level guid {quest_guid}")
    for r in rows:
        t = by_target(r["target"], db)
        if t != journal:
            continue
        kind = "QUEST" if r["leaf"] == quest_guid else "objective"
        print(f"  {'*' if kind=='QUEST' else ' '} {kind:9s} by {r['src']:70s} #{r['block']} {r['class']}")
    print("\n  rows targeting this entry (quest-level):")
    for r in rows:
        if by_target(r["target"], db) == journal and r["leaf"] == quest_guid:
            print(f"    from {r['src_quest']:28s} {r['src']}  #{r['block']} {r['class']} {r['label']!r}")


def theirs(src):
    rows = json.load(open(CACHE))
    db = qdb()
    for r in rows:
        if r["src"] != src:
            continue
        t = by_target(r["target"], db)
        me = db.get(t, [])
        kind = "QUEST" if me and r["leaf"] == me[0][1] else "objective"
        if kind == "QUEST" and r["src_quest"] != t:
            print(f"  STARTS {t:28s} #{r['block']} {r['class']} {r['label']!r}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
    elif sys.argv[1] == "build":
        limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
        build(limit)
    elif sys.argv[1] == "quest":
        quest(sys.argv[2])
    elif sys.argv[1] == "theirs":
        theirs(sys.argv[2])
