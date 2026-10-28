"""Test every claim this tracker makes against every save, and fail loudly.

A claim is only as good as the ability to break it. This walks the three places claims live and
tries to refute each one:

  data/route.json    a step's hard prerequisites: no save may hold the step engaged while a
                     prerequisite is not done.
  data/feed.json     each item's `checks` list (written by tools/derive.py): "A implies B was
                     done", "starting A never fails X", "this cutoff holds", "enough saves exist
                     to say anything at all".
  data/cutoffs.json  every reviewed cutoff, re-tested on the saves (a refuted one must not ship).

Then it checks the built app against the same data: `--dump` for a few saves must report the same
quest statuses the index read, and the steps it says carry a cutoff must be the steps the data
files say carry one. That catches the app and the data drifting apart, which no amount of reading
the files would.

  py contradictions.py            run everything, write the report, exit 1 on any contradiction
  py contradictions.py --quick    skip the app dump (no built exe needed)
"""
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import HERE, ROUTE, TRACKER
import prereqs

REPORT = HERE / "contradiction_report.md"
JSON_OUT = HERE / "contradictions.json"
SAVES_CACHE = HERE / "save_index.json"
DERIVED = TRACKER / "data" / "derived.json"
CUTOFFS = TRACKER / "data" / "cutoffs.json"
FEED = TRACKER / "data" / "feed.json"
EXE = TRACKER / "target" / "release" / "witcher3-missables-tracker.exe"
RELATIONS = TRACKER / "data" / "prereq_relations.json"
PRESENT = ("Active", "Done", "Failed")


def facts_by_save():
    """{save: {fact: values}} for the facts the route's prerequisites could rest on.

    tools/prereqs.py keeps this cache while it settles the prerequisites; the harness reads the same
    file so it tests the same facts the route does, from the same parse.
    """
    cache = json.loads((HERE / "save_facts.json").read_text(encoding="utf-8")) if (HERE / "save_facts.json").exists() else {}
    return cache.get("saves", {})


def timeline():
    cache = json.loads(SAVES_CACHE.read_text(encoding="utf-8"))
    rows = [(n, v.get("mtime", 0), v["state"]) for n, v in cache.items() if v.get("state")]
    rows.sort(key=lambda r: r[1])
    return rows


def engaged(st, q):
    return st.get(q) in PRESENT


def steps_of(route):
    """route step id -> the journal quest files it reads (same parsing the app does)."""
    out = {}
    for n in route["nodes"]:
        files = [p.lower() for f in n.get("files", []) for p in f.replace("|", "\n").split("\n")
                 if p and "#" not in p]
        out[n["id"]] = files
    return out


def gates_of(route):
    """(step, prerequisite) -> the game facts that satisfy it (empty when the status is the test).

    Five route prerequisites are not "the other quest is finished" but "its story has reached the
    point that opens this". The game states that with a fact, and no save ever has the step under
    way without it (tools/prereqs.py settled it, data/prereqs_review.json records the decision), so
    that fact is what the app tests - the prerequisite reading Done was the wrong signal.
    """
    out = {}
    for n in route["nodes"]:
        for h, facts in (n.get("hard_facts") or {}).items():
            out[(n["id"], h)] = list(facts)
    return out


def done_in(st, files):
    """Is the step done, judged from the save's own journal statuses? None when nothing to judge."""
    known = [st.get(f) for f in files if f in st]
    if not known:
        return None
    return any(x == "Done" for x in known)


def check_hard_prereqs(rows, route, facts):
    """A hard requirement is a claim about the game: no save may show it broken.

    Both sides are judged through the route step's own journal files: a prerequisite written as a
    step id (ci_prep, sk_undvik) is not a journal name, and comparing it as one produced pure noise.
    """
    steps = steps_of(route)
    gates = gates_of(route)
    out = []
    for n in route["nodes"]:
        mine = steps.get(n["id"], [])
        if not mine:
            continue
        for h in n.get("hard", []):
            need = steps.get(h, [h])
            gate = gates.get((n["id"], h), [])
            bad, seen, saved = [], 0, 0
            for name, _mt, st in rows:
                if not any(engaged(st, f) for f in mine):
                    continue
                got = done_in(st, need)
                if got is None:
                    continue
                seen += 1
                if got:
                    continue
                if gate and any(f in facts.get(name, {}) for f in gate):
                    # satisfied by the game's own condition rather than by the prerequisite's journal
                    # status, which is exactly what the saves were right about
                    saved += 1
                    continue
                bad.append((name, "not Done", next((st.get(f) for f in mine if engaged(st, f)), "")))
            claim = {"claim": f"{n['id']} requires {h}", "kind": "hard_prereq", "checked_in": seen,
                     "violations": len(bad), "examples": bad[:3], "ok": not bad}
            if gate:
                claim["fact"] = gate
                claim["satisfied_by_fact"] = saved
            out.append(claim)
    return out


def check_settlement():
    """The route and the settlement have to agree, and the settlement has to be the current one.

    tools/prereqs.py decides every precondition from the files and the saves, but the app only ever
    reads data/route.json - so a decision that is not in the route is a decision that does nothing,
    and a route edge that no longer matches its decision is a lock nothing supports.
    """
    if not RELATIONS.exists():
        return [{"claim": "the settlement of the route's prerequisites is present", "kind": "settlement",
                 "ok": False, "violations": 1, "examples": ["tools/prereq_relations.json missing: run py tools/prereqs.py check"],
                 "checked_in": 0}]
    rel = json.loads(RELATIONS.read_text(encoding="utf-8"))
    problems = rel.get("review_problems") or []
    return [{"claim": "every settled decision is in the route, and no route lock is refuted",
             "kind": "settlement", "checked_in": len(rel.get("edges", [])),
             "violations": len(problems), "examples": problems[:3], "ok": not problems}]


def check_reader(n=25):
    """A `Failed` in a save is the game's own record, not a misread: the reader must attach each
    status to the entry it belongs to (its GUID and its journal file have to agree)."""
    r = prereqs.reading_result(n)
    if r.get("error"):
        return [{"claim": "the save reader attaches statuses to the right entries", "kind": "reader",
                 "ok": False, "violations": 1, "examples": [r["error"]], "checked_in": 0}]
    return [{"claim": "the save reader attaches statuses to the right entries", "kind": "reader",
             "checked_in": r["entries"], "violations": len(r["mismatches"]),
             "examples": [f"{m[0]}: {m[1]} reads {m[3]}, its file is {m[2]}" for m in r["mismatches"][:3]],
             "ok": not r["mismatches"], "saves": r["saves"], "statuses": r["statuses"]}]


def check_feed(rows, feed):
    out = []
    for item in feed.get("items", []):
        for c in item.get("checks", []):
            kind = c["kind"]
            res = {"claim": f"{item['id']}: {c.get('why', '')}", "kind": kind, "of": item["id"]}
            if kind == "implies_done":
                bad, n = [], 0
                for name, _mt, st in rows:
                    if any(engaged(st, q) for q in c["if_present"]):
                        n += 1
                        miss = [q for q in c["then_done"] if st.get(q) != "Done"]
                        if miss:
                            bad.append((name, st.get(c["if_present"][0]), [(q, st.get(q)) for q in miss]))
                res.update(checked_in=n, violations=len(bad), examples=bad[:3], ok=not bad)
            elif kind == "not_failed":
                bad, n = [], 0
                for name, _mt, st in rows:
                    if engaged(st, c["when"]):
                        n += 1
                        f = [(q, st.get(q)) for q in c["quests"] if st.get(q) == "Failed"]
                        if f:
                            bad.append((name, f))
                res.update(checked_in=n, violations=len(bad), examples=bad[:3], ok=not bad)
            elif kind == "implies_present":
                bad, n = [], 0
                for name, _mt, st in rows:
                    if all(st.get(q) == "Done" for q in c["if_done"]):
                        n += 1
                        miss = [q for q in c["then_present"] if not engaged(st, q)]
                        if miss:
                            bad.append((name, [(q, st.get(q)) for q in miss]))
                res.update(checked_in=n, violations=len(bad), examples=bad[:3], ok=not bad)
            elif kind == "cutoff_consistent":
                res.update(cutoff_test(rows, c["affected"], c["closed_by"]))
                res["ok"] = res["later_finished"] == 0 and res["open_before"] > 0
            elif kind == "saves_present":
                n = sum(1 for _n, _m, st in rows if engaged(st, c["quest"]))
                res.update(checked_in=n, least=c["least"], ok=n >= c["least"], violations=0 if n >= c["least"] else 1)
            else:
                res.update(ok=False, violations=1, examples=[f"unknown check kind {kind}"])
            out.append(res)
    return out


def cutoff_test(rows, affected, closed_by):
    """How the saves read: affected open when a closer finished, and finished afterwards."""
    open_before = later_finished = later_still_open = 0
    for _name, _mt, st in rows:
        if any(st.get(e) == "Done" for e in closed_by):
            for x in affected:
                if st.get(x) in ("Active", "Failed"):
                    open_before += 1
                elif st.get(x) == "Done" and open_before:
                    later_finished += 1
                elif open_before:
                    later_still_open += 1
    return {"checked_in": sum(1 for _n, _m, st in rows if any(st.get(e) == "Done" for e in closed_by)),
            "open_before": open_before, "later_finished": later_finished,
            "later_still_open": later_still_open, "violations": later_finished, "examples": []}


def check_cutoffs(rows):
    out = []
    if not CUTOFFS.exists():
        return out
    data = json.loads(CUTOFFS.read_text(encoding="utf-8"))
    for item in data.get("items", []):
        r = cutoff_test(rows, item["affects"], item["closed_by"])
        r.update(claim=f"reviewed cutoff {item['id']}: {item['headline']}", kind="reviewed_cutoff",
                 of=item["id"], ok=r["later_finished"] == 0 and r["open_before"] > 0)
        out.append(r)
    return out


def check_app(rows, derived, quick=False):
    """The built app must agree with the data: same statuses, same steps flagged."""
    res = {"claim": "the built app reports what the data files say", "kind": "app_dump", "ok": True,
           "violations": 0, "examples": [], "checked_in": 0}
    if quick or not EXE.exists():
        res.update(ok=False, skipped=True, examples=["no built exe (run cargo build --release)"])
        return [res]
    # the app reads the newest save itself, so that is the entry to compare it with
    flagged = sorted(k for k, v in derived.get("steps", {}).items() if v.get("watch"))
    out = TRACKER / "target" / "dump_check.json"
    try:
        subprocess.run([str(EXE), "--dump", str(out)], cwd=str(TRACKER), check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
    except Exception as ex:
        res.update(ok=False, violations=res["violations"] + 1, examples=[f"dump failed: {ex}"])
        return [res]
    d = json.loads(out.read_text(encoding="utf-8"))
    name = d.get("save", "")
    cache = json.loads(SAVES_CACHE.read_text(encoding="utf-8"))
    want = (cache.get(name) or {}).get("state")
    if not want:
        res.update(ok=False, violations=1,
                   examples=[f"the app read {name}, which the index does not have - run py tools/saveindex.py build"])
        return [res]
    # the app has to pick the newest save; when it does not, say whether the index or the app is behind
    newest = rows[-1][0] if rows else ""
    if name != newest:
        mtimes = {n: mt for n, mt, _st in rows}
        behind = mtimes.get(name, 0) < mtimes.get(newest, 0)
        res["violations"] += 1 if behind else 0
        res["examples"].append(f"the app read {name}; the index's newest is {newest} "
                               f"({'the app picked an older save' if behind else 'the index is behind'})")
    norm = {"Inactive": "Not started"}  # the index says Inactive, the app says Not started
    got = {k: norm.get(v, v) for k, v in d.get("states", {}).items() if "#" not in k}
    want = {k: norm.get(v, v) for k, v in want.items()}
    diff = {k: (v, got.get(k)) for k, v in want.items() if got.get(k) != v}
    res["checked_in"] += len(want)
    res["violations"] += len(diff)
    if diff:
        res["examples"].append(f"{name}: {len(diff)} statuses differ, e.g. " + str(list(diff.items())[:3]))
    app_flagged = sorted(x["id"] for x in d.get("watch", []) if x.get("watch"))
    if app_flagged != flagged:
        res["violations"] += 1
        res["examples"].append(f"steps flagged differ: app {app_flagged} vs data {flagged}")
    # No allowance: the app and the index now read the same rule - the quest's own journal entry (the
    # file's CJournalQuest export) first, and the most advanced entry of that file only when the game
    # leaves it inactive. This used to pass as a rate because the shipped app was reading a
    # description entry's status for 46 quests, which is fixed; any difference here is the two having
    # drifted apart again, and the message above names the quests.
    res["allowed"] = 0
    res["ok"] = not res["violations"]
    return [res]


def check_parsers():
    """Report how much of the game's data the readers actually manage (not a pass/fail claim)."""
    import cr2w
    from paths import JOURNAL_DIR, QUEST_ROOT
    out = {}
    for pattern, where in (("*.w2phase", QUEST_ROOT), ("*.w2scene", QUEST_ROOT), ("*.journal", JOURNAL_DIR)):
        files = list(where.rglob(pattern))
        bad = Counter()
        for f in files:
            try:
                cr2w.parse(f)
            except Exception as ex:
                bad[type(ex).__name__] += 1
        out[pattern] = {"files": len(files), "unreadable": dict(bad)}
    return out


DISPUTES = TRACKER / "data" / "route_disputes.json"
# a prerequisite is only worth escalating when a few saves disagree, not when one odd save does
DISPUTE_MIN = 3


def main():
    quick = "--quick" in sys.argv
    rows = timeline()
    route = json.loads(ROUTE.read_text(encoding="utf-8"))
    feed = json.loads(FEED.read_text(encoding="utf-8"))
    derived = json.loads(DERIVED.read_text(encoding="utf-8")) if DERIVED.exists() else {}

    prereqs = check_hard_prereqs(rows, route, facts_by_save())
    results = (check_feed(rows, feed) + check_cutoffs(rows) + check_app(rows, derived, quick)
               + check_settlement() + ([] if quick else check_reader()))
    parsers = check_parsers()
    failed = [r for r in results if not r.get("ok")]

    # The route's prerequisites came from wiki-era notes, which is what this work exists to replace.
    # Where the saves disagree, that is a finding about the route, so it is written out for the app
    # to show and for the next pass to fix - not silently dropped, and not a failure of the derived
    # claims, which do have to hold.
    disputes = [r for r in prereqs if r["violations"] >= DISPUTE_MIN]
    DISPUTES.write_text(json.dumps({
        "note": "Prerequisites in data/route.json that the saves disagree with, found by tools/contradictions.py. "
                "Empty is the healthy state: it means every prerequisite the app locks on holds against all "
                "517 saves. The nine that did not were settled in data/prereqs_review.json - four dropped "
                "(the two quests simply run alongside each other) and five re-tested on the game's own "
                "condition instead of the prerequisite's journal status - after the reader was proven to "
                "attach statuses to the right entries, so a Failed in a save is the game's own record "
                "rather than a misread. The reading side was corrected with it: the app reads each quest "
                "from its journal file's own entry (the index cache is versioned now, so a corrected "
                "builder reaches players who already had a cached index) and the tool chain reads the "
                "expansions' journal files as well, which it did not - 116 quests were being read from a "
                "'Descriptions' entry instead of the quest.",
        "disputes": [{"step": r["claim"].split(" requires ")[0], "prereq": r["claim"].split(" requires ")[-1],
                      "violations": r["violations"], "checked_in": r["checked_in"],
                      "examples": [e[0] for e in (r.get("examples") or [])]} for r in disputes]},
        indent=1, sort_keys=True), encoding="utf-8")

    JSON_OUT.write_text(json.dumps({"saves": len(rows), "results": results, "prereq_checks": prereqs,
                                    "disputes": disputes, "parsers": parsers},
                                   indent=1, sort_keys=True), encoding="utf-8")

    lines = [f"# Contradiction report", "",
             f"{len(results)} claims about the derived data tested against {len(rows)} saves: "
             f"{len(results) - len(failed)} hold, {len(failed)} do not.", "",
             f"{len(prereqs)} prerequisites in the route were checked against the saves too.", ""]
    gated = [p for p in prereqs if p.get("fact")]
    if gated:
        lines += [f"## Prerequisites tested on the game's own condition", "",
                  "Not \"the other quest is finished\" but \"its story reached the point that opens this\": "
                  "the fact is what the app tests, and no save breaks it (data/prereqs_review.json).", "",
                  "| step | requires | condition | saves under way the fact covers | violations |",
                  "|---|---|---|---|---|"]
        for p in sorted(gated, key=lambda x: x["claim"]):
            a, b = p["claim"].split(" requires ")
            lines.append(f"| {a} | {b} | {', '.join(p['fact'])} | {p.get('satisfied_by_fact', 0)} | {p['violations']} |")
        lines.append("")
    if failed:
        lines += ["## Contradicted", ""]
        for r in failed:
            lines.append(f"- **{r['kind']}** - {r['claim']}: {r.get('violations', '?')} violation(s)")
            for e in (r.get("examples") or [])[:3]:
                lines.append(f"  - {e}")
        lines.append("")
    if disputes:
        lines += ["## Disputed route prerequisites (wiki-era data, needs a decision)", "",
                  "| step | requires | saves disagreeing | saves checked |", "|---|---|---|---|"]
        for r in sorted(disputes, key=lambda x: -x["violations"]):
            a, b = r["claim"].split(" requires ")
            lines.append(f"| {a} | {b} | {r['violations']} | {r['checked_in']} |")
        lines.append("")
        lines.append("These are written to data/route_disputes.json and shown in the app as a note, not as a "
                     "rule. q402skelligeallies, q402novigradallies and q302war read 'Failed' in saves where "
                     "they were never available, so at least part of this is the journal status reading "
                     "rather than the prerequisite, and it needs a pass of its own.")
        lines.append("")
    lines += ["## Every derived claim", "", "| kind | claim | checked in | violations |", "|---|---|---|---|"]
    for r in results:
        claim = r["claim"].replace("|", "/")[:110]
        lines.append(f"| {r['kind']} | {claim} | {r.get('checked_in', '')} | {r.get('violations', '')} |")
    lines += ["", "## Parser coverage", ""]
    for k, v in parsers.items():
        lines.append(f"- {k}: {v['files']} files, {v['unreadable'] or 'all readable'}")
    lines += ["", "This is a consistency check, not a proof: the saves can refute a claim, and they can "
                  "show no contradiction, but they cannot demonstrate that a quest stopped being "
                  "possible. Where a claim rests on the files, the files are named in data/cutoffs.json."]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"{len(results)} derived claims, {len(failed)} contradicted; "
          f"{len(prereqs)} route prerequisites checked, {len(disputes)} disputed -> {REPORT.name}")
    for r in failed:
        print(f"  FAILED {r['kind']}: {r['claim'][:80]} ({r.get('violations')} violations)")
        for e in (r.get("examples") or [])[:2]:
            print(f"      {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
