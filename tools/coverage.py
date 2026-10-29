"""Generate `data/coverage.json`: what each pack actually has in the route and the index.

The table is the honest replacement for silence. It answers "is a pack modelled?" from the
generated data, not from prose:

  quests          route quest steps whose journal lives in that pack
  manual          manual bookkeeping steps (base by section; the Gwent step is `gwent`)
  steps           quests + manual
  with_phases     route quests that have at least one phase file in the index
  with_scenes     route quests that have at least one scene row in the index
  with_branches   route quests with at least one fact-setting scene choice in branches.json
  with_cards      cards in that pack, or null while the card index has not measured them
  with_cutoffs    route steps named by a reviewed cutoff `affects` row

Packs are `base`, `ep1`, `bob`, `other_dlc`, and `gwent`. The first four partition the 403 route
quests by journal location; `gwent` is the card content pack and has no quest files of its own, so
its 0 quests are the ones counted in base/bob above. The 9 kept manual steps follow their route
section: the Gwent bookkeeping step is `gwent`, every other manual step is `base`. That keeps the
totals at 403 quests + 9 manual = 412 steps. The two replaced manual rows are in the journal quests
now and are not counted again.

`with_cards` is preserved from the existing file on build. Part 2 owns that column once the card
index exists; `build` must not overwrite measured card counts with null. A null is "not measured",
never zero. `check` accepts null or a non-negative integer and reports which state it saw.

  py coverage.py build
  py coverage.py check
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import HERE, TRACKER
from resources import PACKS, pack_of_journal

ROUTE = TRACKER / "data" / "route.json"
INDEX = HERE / "quest_index.json"
BRANCHES = TRACKER / "data" / "branches.json"
CUTOFFS = TRACKER / "data" / "cutoffs.json"
OUT = TRACKER / "data" / "coverage.json"

ROW_KEYS = ("quests", "manual", "steps", "with_phases", "with_scenes", "with_branches",
            "with_cards", "with_cutoffs")
NOTE = ("Generated from data/route.json, tools/quest_index.json, data/branches.json and "
        "data/cutoffs.json. with_cards is null until the card index measures it; a null is not "
        "zero. Manual steps follow their route section (the Gwent step is gwent, the rest base).")


def load(path, what):
    if not path.exists():
        raise SystemExit(f"{what} not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"cannot read {what} {path}: {exc}")


def load_inputs():
    route = load(ROUTE, "route")
    index = load(INDEX, "quest index")
    branches = load(BRANCHES, "branch graph")
    cutoffs = load(CUTOFFS, "reviewed cutoffs")
    quests = index.get("quests")
    if not isinstance(quests, dict) or not quests:
        raise SystemExit("quest index has no quests")
    by_name = {}
    for stem, quest in quests.items():
        for name in [stem, *(quest.get("bundle_names") or [])]:
            hit = by_name.get(name)
            if hit is not None and hit != stem:
                raise SystemExit(f"index name {name!r} maps to both {hit!r} and {stem!r}")
            by_name[name] = stem

    step_pack = {}
    quest_by_step = {}
    for node in route.get("nodes") or []:
        step = node.get("id")
        if not isinstance(step, str) or not step:
            raise SystemExit("route has a node without an id")
        if node.get("files"):
            stem = by_name.get(step)
            if stem is None:
                raise SystemExit(f"route step {step!r} has no index quest")
            quest = quests[stem]
            pack = pack_of_journal(quest.get("file"))
            if pack not in PACKS:
                raise SystemExit(f"{step}: journal {quest.get('file')!r} has no coverage pack")
            quest_by_step[step] = quest
        else:
            # a manual step has no journal; its route section is the only attribution it has
            pack = "gwent" if node.get("section") == "Gwent" else "base"
        step_pack[step] = pack
    return route, quests, branches, cutoffs, step_pack, quest_by_step


def existing_cards():
    """The measured card counts already in coverage.json, if any; null means not measured."""
    cards = {pack: None for pack in PACKS}
    if not OUT.exists():
        return cards
    doc = load(OUT, "coverage")
    packs = doc.get("packs") if isinstance(doc, dict) else None
    if not isinstance(packs, dict):
        raise SystemExit(f"{OUT.name}: packs must be an object")
    for pack in PACKS:
        row = packs.get(pack)
        value = row.get("with_cards") if isinstance(row, dict) else None
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise SystemExit(f"{OUT.name}: packs.{pack}.with_cards must be null or a non-negative integer")
        cards[pack] = value
    return cards


def expected(step_pack, quest_by_step, branches, cutoffs, cards):
    rows = {pack: {"quests": 0, "manual": 0, "steps": 0, "with_phases": 0, "with_scenes": 0,
                   "with_branches": 0, "with_cards": cards[pack], "with_cutoffs": 0}
            for pack in PACKS}

    for step, pack in step_pack.items():
        rows[pack]["steps"] += 1
        quest = quest_by_step.get(step)
        if quest is None:
            rows[pack]["manual"] += 1
            continue
        rows[pack]["quests"] += 1
        rows[pack]["with_phases"] += 1 if quest.get("phases") else 0
        rows[pack]["with_scenes"] += 1 if quest.get("scenes") else 0

    branch_steps = set((branches.get("branches") or {}).keys())
    for step in branch_steps:
        if step not in step_pack:
            raise SystemExit(f"branches.json step {step!r} is not a route step")
        if step not in quest_by_step:
            raise SystemExit(f"branches.json step {step!r} is a manual step")
        rows[step_pack[step]]["with_branches"] += 1

    affected = set()
    for kind in ("items", "windows"):
        for row in cutoffs.get(kind) or []:
            for step in row.get("affects") or []:
                if step not in step_pack:
                    raise SystemExit(f"cutoff {row.get('id')!r} affects unknown route step {step!r}")
                affected.add(step)
    for step in affected:
        rows[step_pack[step]]["with_cutoffs"] += 1

    return {"version": 1, "note": NOTE, "packs": {pack: rows[pack] for pack in PACKS}}


def validate(doc, expected_doc, route, branches, step_pack, quest_by_step):
    problems = []
    if not isinstance(doc, dict):
        return ["file is not a JSON object"]
    if doc.get("version") != 1:
        problems.append("version must be 1")
    if not isinstance(doc.get("note"), str):
        problems.append("note must be a string")
    packs = doc.get("packs")
    if not isinstance(packs, dict):
        return problems + ["packs must be an object keyed by pack"]
    if set(packs) != set(PACKS):
        problems.append(f"packs must be exactly {', '.join(PACKS)}; found {', '.join(sorted(packs))}")
    for pack in PACKS:
        row = packs.get(pack)
        if not isinstance(row, dict):
            problems.append(f"packs.{pack} must be an object")
            continue
        if set(row) != set(ROW_KEYS):
            problems.append(f"packs.{pack} keys must be exactly {', '.join(ROW_KEYS)}")
            continue
        for key in ROW_KEYS:
            value = row[key]
            if key == "with_cards":
                if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                    problems.append(f"packs.{pack}.with_cards must be null or a non-negative integer")
            elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
                problems.append(f"packs.{pack}.{key} must be a non-negative integer")
        if row.get("steps") != row.get("quests", 0) + row.get("manual", 0):
            problems.append(f"packs.{pack}: steps must equal quests + manual")

    if not problems:
        for pack in PACKS:
            for key in ROW_KEYS:
                if key == "with_cards":
                    continue
                if packs[pack][key] != expected_doc["packs"][pack][key]:
                    problems.append(
                        f"packs.{pack}.{key} is {packs[pack][key]}, expected "
                        f"{expected_doc['packs'][pack][key]} from the index/route/cutoffs")
        totals = {key: sum(packs[pack][key] for pack in PACKS) for key in ROW_KEYS if key != "with_cards"}
        if totals["quests"] != 403:
            problems.append(f"pack quests sum to {totals['quests']}, expected 403 route quests")
        if totals["manual"] != 9:
            problems.append(f"pack manual steps sum to {totals['manual']}, expected 9")
        if totals["steps"] != 412:
            problems.append(f"pack steps sum to {totals['steps']}, expected 412 route steps")
        if packs["base"]["quests"] != 281 or packs["base"]["manual"] != 8:
            problems.append("base pack no longer holds 281 route quests + 8 manual steps")

    branch_steps = set((branches.get("branches") or {}).keys())
    route_branch = {n.get("id") for n in route.get("nodes") or [] if n.get("branch")}
    if branch_steps != route_branch:
        problems.append("branches.json steps do not match route.json's branch flags")

    dlc_steps = sorted(step for step in quest_by_step if step.startswith(("q704", "q705")))
    if len(dlc_steps) != 10:
        problems.append(f"expected 10 q704*/q705* route steps, found {len(dlc_steps)}")
    for step in dlc_steps:
        if not quest_by_step[step].get("scenes"):
            problems.append(f"{step}: DLC step has no scene rows")
    dlc_rows = sum(len(entry.get("choices") or []) for step, entry in
                   (branches.get("branches") or {}).items() if step in dlc_steps)
    if dlc_rows == 0:
        problems.append("the q704*/q705* DLC family produced zero branches")
    return problems


def _report(doc, step_pack, quest_by_step, branches):
    packs = doc["packs"]
    totals = {key: sum(packs[pack][key] for pack in PACKS) for key in ROW_KEYS if key != "with_cards"}
    cards = [packs[pack]["with_cards"] for pack in PACKS]
    if all(value is None for value in cards):
        card_text = "cards not measured"
    elif any(value is None for value in cards):
        card_text = "cards partially measured: " + ", ".join(
            f"{pack} {packs[pack]['with_cards']}" if packs[pack]["with_cards"] is not None
            else f"{pack} unknown" for pack in PACKS)
    else:
        card_text = "cards " + ", ".join(f"{pack} {packs[pack]['with_cards']}" for pack in PACKS)
    dlc_steps = sorted(step for step in quest_by_step if step.startswith(("q704", "q705")))
    dlc_scene_rows = sum(len(quest_by_step[step].get("scenes") or []) for step in dlc_steps)
    dlc_rows = sum(len(entry.get("choices") or []) for step, entry in
                   (branches.get("branches") or {}).items() if step in dlc_steps)
    print(f"{len(PACKS)} packs; {totals['quests']} quests + {totals['manual']} manual = "
          f"{totals['steps']} steps; phases {totals['with_phases']}, scenes {totals['with_scenes']}, "
          f"branches {totals['with_branches']}, cutoffs {totals['with_cutoffs']}; {card_text}; "
          f"q704*/q705* {len(dlc_steps)} steps, {dlc_scene_rows} scene rows, {dlc_rows} branches")


def build():
    route, quests, branches, cutoffs, step_pack, quest_by_step = load_inputs()
    cards = existing_cards()
    doc = expected(step_pack, quest_by_step, branches, cutoffs, cards)
    problems = validate(doc, doc, route, branches, step_pack, quest_by_step)
    if problems:
        print(f"{len(problems)} problem(s); refusing to write {OUT.name}:")
        for problem in problems[:30]:
            print("  ", problem)
        return 1
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.name}:", end=" ")
    _report(doc, step_pack, quest_by_step, branches)
    return 0


def check():
    route, quests, branches, cutoffs, step_pack, quest_by_step = load_inputs()
    if not OUT.exists():
        print(f"{OUT.name} not found; run py tools/coverage.py build")
        return 1
    try:
        actual = json.loads(OUT.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        print(f"cannot read {OUT.name}: {exc}")
        return 1
    cards = existing_cards()
    expected_doc = expected(step_pack, quest_by_step, branches, cutoffs, cards)
    problems = validate(actual, expected_doc, route, branches, step_pack, quest_by_step)
    if actual != expected_doc:
        problems.append("file differs from a fresh extraction; run py tools/coverage.py build")
    if problems:
        print(f"{len(problems)} problem(s):")
        for problem in problems[:30]:
            print("  ", problem)
        return 1
    print("coverage ok:", end=" ")
    _report(actual, step_pack, quest_by_step, branches)
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build":
        sys.exit(build())
    if cmd == "check":
        sys.exit(check())
    print(__doc__)
    sys.exit(2)
