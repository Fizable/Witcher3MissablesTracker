"""Write `data/route.json` from the game's own files.

This replaces the 0.1.9 route, which was hand-written from wiki pages. Every quest step is one
`CJournalQuest` journal (405 on this install, minus the two `biddebug*` containers = 403), plus the
9 reviewed manual bookkeeping steps in `data/route_overrides.json`. The 11 baseline manual steps are
audited in `docs/MANUAL-STEPS-AUDIT.md`: two exact duplicates were replaced by the file-derived
journals `q108eve` and `q111imlerith`, so the audited route has 412 nodes. The route is regenerated,
never edited: a correction belongs in the reviewed input file, not in the output.

Inputs:
  tools/quest_index.json      titles, types, order, descriptions, levels, branch/Gwent flags, starts
  data/quest_sections.json    the reviewed type fallback for the 30 untyped main-story entries
  data/route_overrides.json   the 9 kept manual steps and the 2 replacements, opt/when/conditional, flags, Gwent file exceptions
  data/quest_graph.json       reviewed fact prerequisites and loss edges

Output `data/route.json`:
  sections    Main, Secondary, Contracts, Treasure Hunts, Gwent
  nodes       403 quest steps + 9 manual steps = 412
  events      one per reviewed loss edge (the top section groups by these)
  prefs       [] (the one rule it carried is now the statuette cutoff)
  conditional the reviewed conditional step ids
  flags       the four world-state questions the save cannot answer

A step carries `branch` only when the game files prove a fact-setting choice: a one-shot dialogue
row is `dialogue_choice`, never a branch, and no contract step carries a branch. `ending_relevant`
is attached from the reviewed `data/endings.json`; until that file names the step in a target's
`requires` or `guidance` source, it is false and the app shows no ending chip.

  py routegen.py build
  py routegen.py check
"""
import datetime
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stringsdb
from paths import HERE, TRACKER

INDEX = HERE / "quest_index.json"
GRAPH = TRACKER / "data" / "quest_graph.json"
SECTIONS = TRACKER / "data" / "quest_sections.json"
OVERRIDES = TRACKER / "data" / "route_overrides.json"
ENDINGS = TRACKER / "data" / "endings.json"
ROUTE = TRACKER / "data" / "route.json"

SECTION_OF_TYPE = {"Chapter": "Main", "Side": "Secondary", "MonsterHunt": "Contracts", "TreasureHunt": "Treasure Hunts"}
KIND_OF_SECTION = {"Main": "main", "Secondary": "side", "Contracts": "contract", "Treasure Hunts": "treasure", "Gwent": "gwent"}
TAG = re.compile(r"<[^>]+>")
SPACE = re.compile(r"\s+")
BASELINE_MANUAL = 11
AUDIT_DOC = TRACKER / "docs" / "MANUAL-STEPS-AUDIT.md"


def audit_anchor(source):
    """The reviewed source must be a real file and its #anchor a real heading."""
    path, _, anchor = source.partition("#")
    p = TRACKER / path
    if not p.exists():
        return f"review source {path} does not exist"
    if anchor and not re.search(rf"^#+\s+{re.escape(anchor)}\s*$", p.read_text(encoding="utf-8"), re.M):
        return f"review source {source} has no heading {anchor!r}"
    return None


def audit_date(value):
    try:
        day = datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return f"reviewed date {value!r} is not YYYY-MM-DD"
    if day > datetime.date.today():
        return f"reviewed date {value} is in the future"
    return None


def clean(text):
    return SPACE.sub(" ", TAG.sub(" ", text or "")).strip()


def first_sentence(text, limit=120):
    text = clean(text)
    if not text:
        return ""
    m = re.search(r"(?<=[.!?])\s+", text)
    out = text[:m.start() + 1].rstrip() if m else text
    if len(out) > limit:
        cut = out[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-")
        out = cut + "\u2026"
    return out


def bundle_of(q, stem):
    names = q.get("bundle_names") or []
    return names[0] if names else stem


def load():
    idx = json.loads(INDEX.read_text(encoding="utf-8"))
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    sec = json.loads(SECTIONS.read_text(encoding="utf-8"))
    ov = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    return idx, graph, sec, ov


def ending_steps():
    """Route steps the reviewed ending targets name. Ending relevance is never inferred from a
    scene: a step becomes ending-relevant only when `data/endings.json` names it in a target's
    `requires` or `guidance` source. A scene shared through a hub phase must not give every quest
    that reaches it the chip."""
    if not ENDINGS.exists():
        return set()
    doc = json.loads(ENDINGS.read_text(encoding="utf-8"))
    out = set()
    for target in (doc.get("targets") or {}).values():
        for req in target.get("requires") or []:
            step = ((req.get("source") or {}).get("step"))
            if isinstance(step, str) and step:
                out.add(step)
        for row in target.get("guidance") or []:
            step = row.get("step")
            if isinstance(step, str) and step:
                out.add(step)
    return out


def build():
    idx, graph, sec, ov = load()
    con = stringsdb.con()
    quests = idx["quests"]
    covered_ending_steps = ending_steps()
    excluded = set(sec.get("excluded", {}))
    overrides_opt = set(ov.get("opt", []))
    when = ov.get("when", {})
    gwent_files = ov.get("gwent_files", {})
    gwent_exclude = set(ov.get("gwent_exclude", []))
    manual = ov.get("manual", [])

    nodes = []
    seen = set()
    for stem, q in sorted(quests.items()):
        if stem in excluded:
            continue
        bundle = bundle_of(q, stem)
        if bundle in seen:
            raise SystemExit(f"duplicate route id {bundle}: two journals map to it")
        seen.add(bundle)
        title = stringsdb.loc(q.get("name_locid"), con) if q.get("name_locid") else ""
        title = clean(title) or clean(q.get("base_name")) or stem
        # the game's own type, with the reviewed fallback only where it is absent
        if q.get("has_gwent") and bundle not in gwent_exclude:
            section = "Gwent"
        elif q.get("type") in SECTION_OF_TYPE:
            section = SECTION_OF_TYPE[q["type"]]
        else:
            row = (sec.get("untyped") or {}).get(stem)
            if not row:
                raise SystemExit(f"untyped quest {stem} has no reviewed section")
            section = row["section"]
        kind = KIND_OF_SECTION[section]
        files = gwent_files.get(bundle) or [bundle]
        reqs = graph.get("requires", {}).get(bundle, [])
        hard = [r["requires"] for r in reqs]
        hard_facts = {r["requires"]: r["facts"] for r in reqs if r.get("facts")}
        by = [l["id"] for l in graph.get("lost_when", []) if bundle in l["affected"]]
        nodes.append({
            "section": section, "id": bundle, "title": title,
            "lv": str(q["level"]) if q.get("level") is not None else "",
            "files": files, "hard": hard, "hard_facts": hard_facts,
            "by": by, "note": "", "kind": kind,
            "opt": bundle in overrides_opt,
            "when": when.get(bundle, []),
            "order": q.get("order") or 0,
            "desc": first_sentence(q.get("description")),
            "branch": bool(q.get("has_branch")),
            "ending_relevant": bundle in covered_ending_steps,
            "start_known": bundle in graph.get("starts", {}),
            "provenance": "game_file",
        })

    for m in manual:
        if m["id"] in seen:
            raise SystemExit(f"duplicate manual id {m['id']}")
        seen.add(m["id"])
        nodes.append({
            "section": m["section"], "id": m["id"], "title": m["title"], "lv": "",
            "files": [], "hard": [], "hard_facts": {}, "by": [],
            "note": "", "kind": m.get("kind", "manual"), "opt": bool(m.get("opt")),
            "when": m.get("when", []), "order": 0, "desc": "", "branch": False,
            "ending_relevant": False,
            "start_known": False,
            "provenance": m["provenance"],
            "review_reason": m["review_reason"],
            "review_source": m["review_source"],
            "reviewed": m["reviewed"],
        })

    sections = ov.get("sections") or sec["sections"]
    rank = {s: i for i, s in enumerate(sections)}
    nodes.sort(key=lambda n: (rank.get(n["section"], 99), n["lv"] == "", int(n["lv"]) if n["lv"].isdigit() else 0,
                              n["order"], n["title"].lower(), n["id"]))

    events = {}
    for l in graph.get("lost_when", []):
        closers = [c for c in l["closed_by"] if c in seen]
        if not closers:
            continue
        events[l["id"]] = {
            "name": l.get("event_name") or l["id"].replace("_", " "),
            "fires": [[c, ["Done"]] for c in closers],
            "near": [],
            "soft": False,
            "note": f"{l['file']} switches off {l['resource']} (CDeactivateSpawnset).",
            "verified": True,
            "mechanism": "CDeactivateSpawnset",
            "file": l["file"],
            "resource": l["resource"],
        }

    replaced = ov.get("manual_replaced", [])
    route = {
        "sections": sections,
        "nodes": nodes,
        "events": events,
        "prefs": [],
        "conditional": ov.get("conditional", []),
        "flags": ov.get("flags", []),
        "manual_audit": {
            "baseline": BASELINE_MANUAL,
            "kept": len(manual),
            "replaced": len(replaced),
            "source": "docs/MANUAL-STEPS-AUDIT.md",
            "replaced_rows": [
                {k: r.get(k) for k in ("id", "title", "replaced_by", "reason", "review_source", "reviewed")}
                for r in replaced
            ],
        },
    }
    ROUTE.write_text(json.dumps(route, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    counts = Counter(n["section"] for n in nodes)
    print(f"wrote {ROUTE.name}: {len(nodes)} steps ({sum(1 for n in nodes if not n['files'])} manual), "
          f"{dict(counts)}, {len(events)} loss events")
    return route


def check():
    route = json.loads(ROUTE.read_text(encoding="utf-8"))
    idx, graph, sec, ov = load()
    nodes = route["nodes"]
    ids = [n["id"] for n in nodes]
    problems = []
    if len(ids) != len(set(ids)):
        problems.append("duplicate ids")
    quest_steps = [n for n in nodes if n["files"]]
    manual = [n for n in nodes if not n["files"]]
    replaced = ov.get("manual_replaced", [])
    excluded = set(sec.get("excluded", {}))
    if len(quest_steps) != len(idx["quests"]) - len(excluded):
        problems.append(f"quest steps {len(quest_steps)} != journals {len(idx['quests'])} - excluded {len(excluded)}")
    if len(manual) != 9:
        problems.append(f"manual steps {len(manual)} != 9")
    if len(manual) + len(replaced) != BASELINE_MANUAL:
        problems.append(f"manual {len(manual)} + replaced {len(replaced)} != baseline {BASELINE_MANUAL}")
    if len(nodes) != 403 + 9:
        problems.append(f"route nodes {len(nodes)} != 403 quest + 9 manual")
    audit = route.get("manual_audit") or {}
    if audit.get("baseline") != BASELINE_MANUAL or audit.get("kept") != len(manual) or audit.get("replaced") != len(replaced):
        problems.append("route manual_audit does not match the reviewed overrides")
    by_id = {n["id"]: n for n in nodes}
    for r in replaced:
        if r["id"] in by_id:
            problems.append(f"replaced manual id {r['id']} is still in the route")
        target = by_id.get(r.get("replaced_by"))
        if not target or not target.get("files"):
            problems.append(f"replaced manual id {r['id']} has no file-derived replacement")
        for key in ("reason", "review_source", "reviewed"):
            if not r.get(key):
                problems.append(f"replaced manual id {r['id']} lacks {key}")
        for e in ([audit_anchor(r.get("review_source", ""))] if r.get("review_source") else []):
            if e:
                problems.append(f"replaced {r['id']}: {e}")
        e = audit_date(r.get("reviewed")) if r.get("reviewed") else None
        if e:
            problems.append(f"replaced {r['id']}: {e}")
    for n in nodes:
        if n.get("provenance") not in ("game_file", "manual_reviewed"):
            problems.append(f"{n['id']} has no provenance tier")
    for n in quest_steps:
        if n.get("provenance") != "game_file" or n.get("review_reason") or n.get("review_source") or n.get("reviewed"):
            problems.append(f"game-file step {n['id']} carries manual review fields")
    for n in manual:
        if n.get("provenance") != "manual_reviewed":
            problems.append(f"manual step {n['id']} is not labelled manual_reviewed")
        if not n.get("review_reason"):
            problems.append(f"manual step {n['id']} has no review reason")
        if not n.get("review_source"):
            problems.append(f"manual step {n['id']} has no review source")
        else:
            e = audit_anchor(n["review_source"])
            if e:
                problems.append(f"manual step {n['id']}: {e}")
        e = audit_date(n.get("reviewed")) if n.get("reviewed") else None
        if e:
            problems.append(f"manual step {n['id']}: {e}")
    # a manual row may not shadow a file-derived quest: that is exactly the duplicate this audit
    # removed. Legitimate repeated quest titles (the three Wine Wars endings) are not flagged.
    quest_titles = Counter(re.sub(r"[^a-z0-9]", "", n["title"].lower()) for n in quest_steps)
    for n in manual:
        title = re.sub(r"[^a-z0-9]", "", n["title"].lower())
        if title and quest_titles.get(title):
            problems.append(f"manual step {n['id']} duplicates the file-derived title {n['title']!r}")
    if route["sections"] != ["Main", "Secondary", "Contracts", "Treasure Hunts", "Gwent"]:
        problems.append(f"sections {route['sections']}")
    for n in nodes:
        if n["section"] not in route["sections"]:
            problems.append(f"{n['id']} has unknown section {n['section']}")
        if n["section"] == "Contracts" and n.get("branch"):
            problems.append(f"contract {n['id']} carries a branch tag")
        if n.get("ending_relevant") and not n.get("branch"):
            problems.append(f"{n['id']} is ending-relevant without a branch")
        for f in n["files"]:
            stem = f.split("|")[0].split("#")[0].lower()
            if stem not in idx["quests"] and not any(stem in (q.get("bundle_names") or []) for q in idx["quests"].values()):
                problems.append(f"{n['id']} reads unknown journal {stem}")
        for h in n["hard"]:
            if h not in set(ids):
                problems.append(f"{n['id']} requires unknown step {h}")
    gwent = [n for n in nodes if n["section"] == "Gwent"]
    if len(gwent) != 11:
        problems.append(f"Gwent steps {len(gwent)} != 11 (10 quest + 1 manual)")
    for name in route["sections"]:
        if not any(n["section"] == name for n in nodes):
            problems.append(f"section {name} is empty")
    # the reviewed route inputs have to survive generation: optional, conditional, world-state flags
    expected_opt = len(ov.get("opt") or []) + sum(1 for m in ov.get("manual", []) if m.get("opt"))
    if sum(1 for n in nodes if n.get("opt")) != expected_opt:
        problems.append(f"optional steps {sum(1 for n in nodes if n.get('opt'))} != {expected_opt} in the reviewed inputs")
    if sum(1 for n in nodes if n.get("when")) != len(ov.get("when") or {}):
        problems.append("when-conditioned steps do not match data/route_overrides.json")
    if set(route.get("conditional") or []) != set(ov.get("conditional") or []):
        problems.append("conditional steps do not match data/route_overrides.json")
    if {f.get("id") for f in route.get("flags") or []} != {f.get("id") for f in ov.get("flags") or []}:
        problems.append("world-state flags do not match data/route_overrides.json")
    if route.get("prefs"):
        problems.append("prefs is not empty; 0.2 keeps no hand-written recommendation")
    if len(route.get("events") or {}) != len(graph.get("lost_when") or []):
        problems.append(f"events {len(route.get('events') or {})} != {len(graph.get('lost_when') or [])} reviewed loss edges")
    untyped = [s for s, q in idx["quests"].items() if q.get("type") is None and s not in excluded]
    for s in untyped:
        if s not in (sec.get("untyped") or {}):
            problems.append(f"untyped {s} has no reviewed section")
    if problems:
        print(f"{len(problems)} problem(s):")
        for p in problems[:30]:
            print("  ", p)
        return 1
    print(f"route ok: {len(quest_steps)} quest + {len(manual)} manual = {len(nodes)} steps; "
          f"{len(replaced)} baseline manual replaced; {len(gwent)} Gwent; {sum(1 for n in nodes if n['lv'])} levelled; "
          f"{sum(1 for n in nodes if n['branch'])} with a branch; "
          f"{sum(1 for n in nodes if n.get('opt'))} optional; {sum(1 for n in nodes if n.get('when'))} when; "
          f"{len(route.get('conditional') or [])} conditional; {len(route.get('flags') or [])} flags; "
          f"{len(graph['lost_when'])} loss edges")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        sys.exit(check())
    build()
