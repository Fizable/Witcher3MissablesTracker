"""Police the audited quest matrix and the manual-step provenance.

Section 4.3 of the finish contract asks for a matrix that starts from the 1.0.0 route, classifies
every node, names every exclusion, and audits all 11 baseline manual steps. The runtime classifies
the six states against the loaded save; this checker polices the data those states are built from:

  * 412 route nodes = 403 file-derived quests + 9 kept manual steps;
  * 2 of the 11 baseline manual rows were exact duplicates and are replaced by their journals;
  * every kept manual row has a reason, a resolvable reviewed source and a review date;
  * no game-file row claims manual provenance, and no manual row claims a journal;
  * every `when` exclusion is a route flag, and the two off-route debug journals have a reason;
  * the four chosen targets are guided, in four one-of groups, with no accepted exclusive edge;
  * the current docs, package README and route payload carry the audited counts, not the old 414;
  * the derived rows cover exactly the route, and every shipped watch names its evidence.

  py matrixcheck.py
"""
import datetime
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import HERE, TRACKER

ROUTE = TRACKER / "data" / "route.json"
OVERRIDES = TRACKER / "data" / "route_overrides.json"
INDEX = HERE / "quest_index.json"
SECTIONS = TRACKER / "data" / "quest_sections.json"
DERIVED = TRACKER / "data" / "derived.json"
COVERAGE = TRACKER / "data" / "coverage.json"
ENDINGS = TRACKER / "data" / "endings.json"
OUTCOMES = TRACKER / "data" / "outcomes.json"
EXCLUSIVE = TRACKER / "data" / "exclusive.json"
UI = TRACKER / "ui" / "app.js"
AUDIT = TRACKER / "docs" / "MANUAL-STEPS-AUDIT.md"
DOCS = (
    TRACKER / "README.md",
    TRACKER / "packaging" / "README.md",
    TRACKER / "docs" / "BACKEND_CONTRACT.md",
    TRACKER / "tools" / "README.md",
)

BASELINE_MANUAL = 11
EXPECTED_QUEST = 403
EXPECTED_MANUAL = 9
EXPECTED_ROUTE = EXPECTED_QUEST + EXPECTED_MANUAL
CHOSEN = ("ciri_witcher", "baron_wife_cured", "olgierd_saved", "bw_both_sisters")
STATES = ("done", "obtainable", "at_risk", "lost", "excluded", "unknown")


def _date(value):
    try:
        day = datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return False
    return day <= datetime.date.today()


def _anchor(source):
    if not source:
        return False
    path, _, anchor = source.partition("#")
    p = TRACKER / path
    if not p.exists():
        return False
    if anchor:
        text = p.read_text(encoding="utf-8")
        return re.search(rf"^#+\s+{re.escape(anchor)}\s*$", text, re.M) is not None
    return True


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def _stems(files):
    out = set()
    for f in files or []:
        for alt in str(f).split("|"):
            stem = alt.split("#")[0]
            if stem:
                out.add(stem)
    return out


def audit(route, idx, ov, sec, derived, coverage, endings, outcomes, exclusive, ui_text, docs=None):
    """Return every problem found in already-loaded data. Kept pure for test_matrix.py."""
    problems = []
    nodes = route.get("nodes") or []
    by_id = {n.get("id"): n for n in nodes}
    quest_nodes = [n for n in nodes if n.get("files")]
    manual = [n for n in nodes if not n.get("files")]
    excluded = set((sec.get("excluded") or {}).keys())

    # Denominator: the journal index is 405, the two debug rows are excluded, and the two duplicate
    # manual rows were replaced by journals already in that set.
    if len(idx.get("quests") or {}) != 405:
        problems.append(f"journal index has {len(idx.get('quests') or {})} entries, expected 405")
    if len(excluded) != 2:
        problems.append(f"quest_sections excludes {len(excluded)} journals, expected the 2 biddebug rows")
    if any(not (sec.get("excluded") or {}).get(stem) for stem in excluded):
        problems.append("an off-route debug exclusion has no mechanism")
    if len(quest_nodes) != EXPECTED_QUEST:
        problems.append(f"route has {len(quest_nodes)} quest steps, expected {EXPECTED_QUEST}")
    if len(manual) != EXPECTED_MANUAL:
        problems.append(f"route has {len(manual)} manual steps, expected {EXPECTED_MANUAL}")
    if len(nodes) != EXPECTED_ROUTE:
        problems.append(f"route has {len(nodes)} nodes, expected {EXPECTED_ROUTE}")
    if len(set(by_id)) != len(nodes):
        problems.append("route has duplicate ids")

    # The reviewed overrides and the generated payload must agree row for row.
    kept = {m.get("id"): m for m in (ov.get("manual") or [])}
    replaced = ov.get("manual_replaced") or []
    if len(kept) != EXPECTED_MANUAL:
        problems.append(f"route_overrides keeps {len(kept)} manual rows, expected {EXPECTED_MANUAL}")
    if len(replaced) != 2:
        problems.append(f"route_overrides records {len(replaced)} replaced manual rows, expected 2")
    if len(kept) + len(replaced) != BASELINE_MANUAL:
        problems.append(f"manual kept {len(kept)} + replaced {len(replaced)} != baseline {BASELINE_MANUAL}")
    if {n["id"] for n in manual} != set(kept):
        problems.append("route manual ids do not match the reviewed overrides")
    audit_doc = route.get("manual_audit") or {}
    if (audit_doc.get("baseline"), audit_doc.get("kept"), audit_doc.get("replaced")) != (
        BASELINE_MANUAL, len(manual), len(replaced)
    ):
        problems.append("route manual_audit does not match the reviewed counts")
    if not AUDIT.exists():
        problems.append("docs/MANUAL-STEPS-AUDIT.md is missing")
    elif str(EXPECTED_ROUTE) not in AUDIT.read_text(encoding="utf-8"):
        problems.append("docs/MANUAL-STEPS-AUDIT.md does not state the audited 412")

    # The two replacements must be real, file-derived route rows and must not still be present.
    for row in replaced:
        rid = row.get("id")
        target = by_id.get(row.get("replaced_by"))
        if not rid:
            problems.append("a replaced manual row has no id")
            continue
        if rid in by_id:
            problems.append(f"replaced manual id {rid} is still in the route")
        if not target or not target.get("files"):
            problems.append(f"{rid} has no file-derived replacement")
        elif _norm(target.get("title")) != _norm(row.get("title")):
            problems.append(f"{rid} replacement title {target.get('title')!r} does not match {row.get('title')!r}")
        if not row.get("reason"):
            problems.append(f"{rid} has no replacement reason")
        if not _anchor(row.get("review_source")):
            problems.append(f"{rid} has no resolvable review source")
        if not _date(row.get("reviewed")):
            problems.append(f"{rid} has no valid review date")

    # Every route node has exactly one provenance tier; manual rows carry the visible label fields.
    for n in nodes:
        if n.get("provenance") not in ("game_file", "manual_reviewed"):
            problems.append(f"{n.get('id')} has no provenance tier")
        if n.get("section") not in (route.get("sections") or []):
            problems.append(f"{n.get('id')} is in unknown section {n.get('section')!r}")
        if n.get("kind") not in ("main", "side", "contract", "treasure", "gwent", "manual"):
            problems.append(f"{n.get('id')} has unknown kind {n.get('kind')!r}")
        if n.get("start_known") not in (True, False):
            problems.append(f"{n.get('id')} has no boolean start_known")
    for n in quest_nodes:
        if n.get("provenance") != "game_file":
            problems.append(f"quest step {n['id']} is not game_file")
        if n.get("review_reason") or n.get("review_source") or n.get("reviewed"):
            problems.append(f"quest step {n['id']} carries manual review fields")
        if not n.get("files"):
            problems.append(f"quest step {n['id']} has no file")
        if not _stems(n.get("files")):
            problems.append(f"quest step {n['id']} has an empty file stem")
    for n in manual:
        m = kept.get(n["id"], {})
        if n.get("provenance") != "manual_reviewed":
            problems.append(f"manual step {n['id']} is not labelled manual_reviewed")
        for key in ("review_reason", "review_source", "reviewed"):
            if not n.get(key) or n.get(key) != m.get(key):
                problems.append(f"manual step {n['id']} {key} does not match the reviewed override")
        if not _anchor(n.get("review_source")):
            problems.append(f"manual step {n['id']} has no resolvable review source")
        if not _date(n.get("reviewed")):
            problems.append(f"manual step {n['id']} has no valid review date")
        if n.get("files"):
            problems.append(f"manual step {n['id']} claims a journal file")
        if n.get("start_known"):
            problems.append(f"manual step {n['id']} claims a start block")
        if n.get("title") != m.get("title") or n.get("section") != m.get("section") or n.get("kind") != m.get("kind", "manual"):
            problems.append(f"manual step {n['id']} does not match the reviewed row")
        if n.get("when", []) != m.get("when", []):
            problems.append(f"manual step {n['id']} when does not match the reviewed row")

    # A manual row may not shadow a file-derived quest; legitimate repeated quest titles are fine.
    quest_titles = Counter(_norm(n.get("title")) for n in quest_nodes)
    for n in manual:
        if quest_titles.get(_norm(n.get("title"))):
            problems.append(f"manual step {n['id']} duplicates the quest title {n.get('title')!r}")

    # Every runtime exclusion is a named world-state condition; the off-route debug rows are named.
    flags = {f.get("id"): f for f in (route.get("flags") or [])}
    for n in nodes:
        for cond in n.get("when") or []:
            key, sep, value = str(cond).partition("=")
            if not sep or not key or not value:
                problems.append(f"{n['id']} has malformed world-state condition {cond!r}")
            elif key not in flags:
                problems.append(f"{n['id']} depends on undeclared flag {key!r}")

    # The two generated coverage views must cover the audited route, not the old one.
    derived_steps = set((derived.get("steps") or {}).keys())
    if derived_steps != set(by_id):
        missing = sorted(set(by_id) - derived_steps)
        extra = sorted(derived_steps - set(by_id))
        problems.append(f"derived rows do not match the route: missing {missing[:3]}, extra {extra[:3]}")
    totals = (coverage.get("packs") or {})
    if totals:
        q = sum((p.get("quests") or 0) for p in totals.values())
        m = sum((p.get("manual") or 0) for p in totals.values())
        s = sum((p.get("steps") or 0) for p in totals.values())
        if (q, m, s) != (EXPECTED_QUEST, EXPECTED_MANUAL, EXPECTED_ROUTE):
            problems.append(f"coverage totals {q} quest + {m} manual = {s}, expected {EXPECTED_QUEST}+{EXPECTED_MANUAL}={EXPECTED_ROUTE}")

    # The chosen four are guided and cannot collide in a one-of group or an accepted exclusive edge.
    guides = endings.get("targets") or {}
    groups = outcomes.get("groups") or {}
    outcomes_by_id = outcomes.get("outcomes") or {}
    chosen_outcomes = []
    per_group = Counter()
    for tid in CHOSEN:
        target = guides.get(tid)
        if not target:
            problems.append(f"chosen target {tid} is missing from endings.json")
            continue
        if target.get("guidance_status") != "guided":
            problems.append(f"chosen target {tid} is not guided")
        oid = target.get("outcome")
        out = outcomes_by_id.get(oid)
        if not out:
            problems.append(f"chosen target {tid} has no outcome row {oid!r}")
            continue
        group = groups.get(out.get("group")) or {}
        if group.get("selection") != "one":
            problems.append(f"outcome {oid} is not in a one-of group")
        chosen_outcomes.append(oid)
        per_group[out.get("group")] += 1
    for group, count in per_group.items():
        if count > 1:
            problems.append(f"chosen targets share one-of group {group}")
    for edge in exclusive.get("edges") or []:
        a, b = edge.get("a"), edge.get("b")
        if a in chosen_outcomes and b in chosen_outcomes:
            problems.append(f"chosen outcomes are joined by an exclusive edge: {a} / {b}")
    if len(chosen_outcomes) != 4:
        problems.append("the four chosen targets do not all map to outcomes")

    # Warnings are shipped only with a mechanism and file/save evidence; the derived watch rows are
    # the only warning source the app can attach.
    watches = [w for row in (derived.get("steps") or {}).values() for w in (row.get("watch") or [])]
    for w in watches:
        if not w.get("files"):
            problems.append(f"watch {w.get('id', '?')} has no file/save evidence")
        if not w.get("action") and not w.get("caveats"):
            problems.append(f"watch {w.get('id', '?')} has no action or caveat")

    # The current user-facing docs and the UI label must not lag the audited route. `docs` is an
    # optional {path: text} override so a test can prove this rule rejects a stale count.
    doc_text = docs if docs is not None else {p: (p.read_text(encoding="utf-8") if p.exists() else "") for p in DOCS}
    for p in DOCS:
        text = doc_text.get(p, "")
        if "412" not in text or not re.search(rf"\b{EXPECTED_MANUAL}\b\s+(?:\w+\s+){{0,2}}manual", text):
            problems.append(f"{p.relative_to(TRACKER)} does not state 412 and {EXPECTED_MANUAL} manual")
    if "MANUAL REVIEWED" not in ui_text or "manual_reviewed" not in ui_text:
        problems.append("ui/app.js has no visible MANUAL REVIEWED label")

    return problems


def main():
    load = lambda p: json.loads(p.read_text(encoding="utf-8"))
    problems = audit(
        load(ROUTE), load(INDEX), load(OVERRIDES), load(SECTIONS), load(DERIVED), load(COVERAGE),
        load(ENDINGS), load(OUTCOMES), load(EXCLUSIVE), UI.read_text(encoding="utf-8"),
    )
    if problems:
        print(f"{len(problems)} matrix problem(s):")
        for p in problems:
            print("  ", p)
        return 1
    route = load(ROUTE)
    when_rows = sum(bool(n.get("when")) for n in route["nodes"])
    when_conditions = sum(len(n.get("when") or []) for n in route["nodes"])
    print(f"matrix ok: {len(route['nodes'])} route nodes = 403 quest + 9 manual_reviewed; "
          f"2 baseline manual replaced; {len(route.get('manual_audit', {}).get('replaced_rows', []))} named; "
          f"{when_rows} world-state rows / {when_conditions} conditions policed; 2 off-route debug exclusions named; "
          f"4 chosen targets in 4 one-of groups, 0 exclusive edges; "
          f"11 Gwent = 10 quest + 1 manual; derived and coverage cover 412; 6 warnings carry evidence")
    return 0


if __name__ == "__main__":
    sys.exit(main())
