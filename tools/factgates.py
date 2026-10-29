"""Fact-level gate index: what each quest phase sets and what it tests.

W3 gates quests through the facts database, not by naming other quests: a phase sets a fact
(CQuestFactsDBChangingBlock) and another phase waits on it (CQuestFactsDBCondition / a condition
block whose label names the fact). Joining set-side to test-side gives a game-file gate, with the
condition's own readable label as the evidence line.

  py factgates.py build                 build/update fact_index.json
  py factgates.py sets <quest>          facts that quest's phases set
  py factgates.py tests <quest>         facts that quest's phases wait on, and who sets them
  py factgates.py gate <A> <B>          does A set a fact that B waits on?
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cr2w

from paths import HERE, REDKIT_R4 as R4  # noqa: F401
import resources

CACHE = HERE / "fact_index.json"

FACTISH = re.compile(r"^[a-z][a-z0-9_]{3,}$")
CONDITION_CLASSES = {"CQuestConditionBlock", "CQuestPauseConditionBlock", "CQuestFactsDBCondition"}


def quest_prefix(path):
    m = re.match(r"^(q\d+_[a-z0-9_]+)", path.stem)
    return m.group(1) if m else path.stem


def scan(path):
    p = cr2w.parse(path)
    src = str(path.relative_to(R4))
    q = quest_prefix(path)
    out = []
    cache = {}

    def props(i):
        if i not in cache:
            cache[i] = {x["name"]: x["value"] for x in cr2w.props(p, p["exports"][i - 1])} if 1 <= i <= len(p["exports"]) else {}
        return cache[i]

    for e in p["exports"]:
        cn = e["className"]
        if cn == "CQuestFactsDBChangingBlock":
            ps = props(e["index"])
            f = ps.get("factID") or ps.get("factId")
            if isinstance(f, str) and f:
                out.append({"src": src, "quest": q, "kind": "set", "fact": f,
                            "value": ps.get("value"), "label": str(ps.get("comment") or "")[:70]})
        elif cn == "CQuestFactsDBCondition":
            ps = props(e["index"])
            f = ps.get("factId") or ps.get("factID")
            if isinstance(f, str) and f:
                out.append({"src": src, "quest": q, "kind": "test", "fact": f,
                            "cmp": ps.get("compareFunc"), "label": ""})
        elif cn == "CQuestConditionBlock":
            ps = props(e["index"])
            lab = ps.get("name") or ""
            cond = ps.get("questCondition")
            cls = ""
            if isinstance(cond, dict) and cond.get("ref_chunk"):
                cls = p["exports"][cond["ref_chunk"] - 1]["className"] if cond["ref_chunk"] <= len(p["exports"]) else ""
            out.append({"src": src, "quest": q, "kind": "test", "fact": "", "cond_class": cls,
                        "label": str(lab)[:80]})
    return out


def build(limit=None):
    # Base game plus every DLC data root. The cache is keyed on the path relative to r4data, so
    # adding DLC files only scans the new ones and never rewrites a base row.
    files = resources.phase_files()
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
        if i % 100 == 0 or i == len(todo):
            json.dump(rows, open(CACHE, "w"))
            print(f"  {i}/{len(todo)}  {time.time()-t0:.0f}s rows={len(rows)}", flush=True)
    json.dump(rows, open(CACHE, "w"))
    print(f"done: {len(rows)} rows")
    return rows


def load():
    return json.load(open(CACHE))


def sets(quest):
    for r in load():
        if r["quest"] == quest and r["kind"] == "set":
            print(f"  {r['fact']:42s} = {r['value']}   ({r['src']}) {r['label']!r}")


def tests(quest):
    rows = load()
    setters = {}
    for r in rows:
        if r["kind"] == "set" and r["fact"]:
            setters.setdefault(r["fact"], set()).add(r["quest"])
    for r in rows:
        if r["quest"] != quest or r["kind"] != "test":
            continue
        if r["fact"]:
            who = sorted(setters.get(r["fact"], []))
            who = [w for w in who if w != quest]
            print(f"  fact {r['fact']:38s} {str(r['cmp']):14s} set by: {', '.join(who) if who else '-'}")
        elif r.get("label") and FACTISH.match(r["label"].split(" ")[0]):
            f = r["label"].split(" ")[0]
            who = sorted(setters.get(f, []))
            who = [w for w in who if w != quest]
            if who:
                print(f"  cond {r['label'][:50]:52s} set by: {', '.join(who)}")


def gate(a, b):
    rows = load()
    sa = {}
    for r in rows:
        if r["kind"] == "set" and r["fact"] and r["quest"] == a:
            sa.setdefault(r["fact"], []).append(r)
    shared = []
    for r in rows:
        if r["quest"] != b or r["kind"] != "test":
            continue
        f = r["fact"] or (r.get("label", "").split(" ")[0] if FACTISH.match(r.get("label", " ").split(" ")[0] or " ") else "")
        if f and f in sa:
            shared.append((f, r, sa[f][0]))
    print(f"{a} -> {b}: {len(shared)} shared fact(s)")
    for f, t, s in shared:
        print(f"  {f}")
        print(f"     set  by {a}: {s['src']} {s['label']!r}")
        print(f"     tested by {b}: {t['src']} {t.get('cond_class','')} {t['label']!r}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
    elif sys.argv[1] == "build":
        limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
        build(limit)
    elif sys.argv[1] == "sets":
        sets(sys.argv[2])
    elif sys.argv[1] == "tests":
        tests(sys.argv[2])
    elif sys.argv[1] == "gate":
        gate(sys.argv[2], sys.argv[3])
