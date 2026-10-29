"""Generate `data/branches.json` from the quest index's scene choices.

A **branch** is a choice whose scene section sets a fact: taking it decides a fact, so it is an
outcome branch. A one-shot (`singleUseChoice`) dialogue row is never a branch, and a contract is
never a branch (its dialogue sets bookkeeping facts about the offer/reward, not quest content).
Only route steps are included, so every `branches.json` step exists in `data/route.json`.

Each row keeps the evidence a reviewed target needs:

  id            stable internal id: `<step>__<choice_locid>__<first set fact>`
  step          the route step the branch belongs to
  scene         the scene resource, relative to the REDkit r4data root
  choice_locid  the game's `CStorySceneChoiceLine.choiceLine` locId
  choice_text   the string database's text for that locId, or null when it has none
  sets          the facts taking the choice sets, sorted
  tests         the other facts the choice's own section names, sorted
  one_shot      always false; one-shot rows are excluded
  source        {kind: scene_choice, file, locid}

`choice_text` is stored so a selected target can prove the exact line it shows. It is never part
of the default payload: the app gets it only through the selected-target guidance path.

  py branchgen.py build
  py branchgen.py check
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stringsdb
from paths import HERE, TRACKER
from resources import pack_of_journal

INDEX = HERE / "quest_index.json"
ROUTE = TRACKER / "data" / "route.json"
OUT = TRACKER / "data" / "branches.json"

NOTE = ("Generated from the quest index's scene choices. A choice is a branch only when its "
        "section sets a fact; one-shot dialogue rows and contracts are excluded. choice_text is "
        "stored for the selected-target guidance path and is not part of the default payload.")


def load(path, what):
    if not path.exists():
        raise SystemExit(f"{what} not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"cannot read {what} {path}: {exc}")


def load_inputs():
    """Route, index quests, and the route step -> quest pairs the branch extraction uses."""
    route = load(ROUTE, "route")
    index = load(INDEX, "quest index")
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
    pairs = []
    for node in route.get("nodes") or []:
        if not node.get("files"):
            continue  # a manual bookkeeping step has no scene choices
        stem = by_name.get(node.get("id"))
        if stem is None:
            raise SystemExit(f"route step {node.get('id')!r} has no index quest")
        pairs.append((node, quests[stem]))
    return route, quests, pairs


def _row(step, scene, locid, sets, tests):
    return {
        "id": f"{step}__{locid}__{sets[0]}",
        "step": step,
        "scene": scene,
        "choice_locid": locid,
        "choice_text": None,
        "sets": list(sets),
        "tests": list(tests),
        "one_shot": False,
        "source": {"kind": "scene_choice", "file": scene, "locid": locid},
    }


def extract(route, quests, pairs):
    """The generated document. Pure: no file writes, so `check` can compare against it."""
    rows = {}
    used_ids = {}
    for node, quest in pairs:
        step = node["id"]
        if node.get("section") == "Contracts":
            continue
        for scene in quest.get("scenes") or []:
            file = scene.get("file") or ""
            if not file:
                raise SystemExit(f"{step}: a scene row has no file")
            for choice in scene.get("choices") or []:
                if choice.get("one_shot") or not choice.get("section_sets"):
                    continue
                locid = choice.get("locid")
                if not isinstance(locid, int) or isinstance(locid, bool) or locid <= 0:
                    raise SystemExit(f"{step}: scene {file} has a fact-setting choice with no locId")
                sets = sorted({str(f) for f in choice["section_sets"] if f})
                if not sets:
                    raise SystemExit(f"{step}: scene {file} choice {locid} has no set fact")
                tests = sorted({str(f) for f in (choice.get("section_facts") or []) if f} - set(sets))
                key = (step, file, locid, tuple(sets))
                if key in rows:
                    # the same scene can be reached through more than one phase folder; the
                    # choice is the same branch, and its tests are the union of the occurrences
                    rows[key]["tests"] = sorted(set(rows[key]["tests"]) | set(tests))
                    continue
                row = _row(step, file, locid, sets, tests)
                if row["id"] in used_ids:
                    other = used_ids[row["id"]]
                    raise SystemExit(
                        f"branch id collision {row['id']!r}: {other['step']}/{other['scene']} and "
                        f"{step}/{file} set the same first fact")
                used_ids[row["id"]] = row
                rows[key] = row

    if not rows:
        raise SystemExit("no fact-setting scene choices were found; refusing to write an empty branch graph")

    locids = sorted({row["choice_locid"] for row in rows.values()})
    texts = stringsdb.locs(locids, stringsdb.con())
    for row in rows.values():
        text = texts.get(row["choice_locid"]) or ""
        row["choice_text"] = text if text else None

    by_step = {}
    for row in rows.values():
        by_step.setdefault(row["step"], []).append(row)
    branches = {}
    for node, _quest in pairs:
        step = node["id"]
        if step not in by_step:
            continue
        branches[step] = {
            "step": step,
            "choices": sorted(by_step[step], key=lambda r: (r["scene"], r["choice_locid"], r["id"])),
        }
    return {"version": 1, "note": NOTE, "branches": branches}


def counts(doc, pairs):
    steps_by_pack = Counter()
    rows_by_pack = Counter()
    pack_of_step = {node["id"]: pack_of_journal(quest.get("file")) for node, quest in pairs}
    for step, entry in doc["branches"].items():
        steps_by_pack[pack_of_step[step]] += 1
        rows_by_pack[pack_of_step[step]] += len(entry["choices"])
    return pack_of_step, steps_by_pack, rows_by_pack


def validate(doc, route, quests, pairs):
    problems = []
    if not isinstance(doc, dict):
        return ["file is not a JSON object"]
    if doc.get("version") != 1:
        problems.append("version must be 1")
    branches = doc.get("branches")
    if not isinstance(branches, dict):
        return problems + ["branches must be an object keyed by step"]

    route_nodes = {n.get("id"): n for n in route.get("nodes") or []}
    step_quest = {node["id"]: quest for node, quest in pairs}
    contract_steps = {n.get("id") for n in route.get("nodes") or [] if n.get("section") == "Contracts"}
    route_branch = {n.get("id") for n in route.get("nodes") or [] if n.get("branch")}
    scenes_by_step = {step: {s.get("file") for s in quest.get("scenes") or []}
                      for step, quest in step_quest.items()}
    seen_ids = set()
    rows = 0
    for step, entry in branches.items():
        if step not in route_nodes:
            problems.append(f"{step}: step is not in route.json")
            continue
        if step in contract_steps:
            problems.append(f"{step}: a contract step carries a branch")
        if step not in step_quest:
            problems.append(f"{step}: manual step cannot have scene branches")
            continue
        if not isinstance(entry, dict):
            problems.append(f"{step}: entry is not an object")
            continue
        if entry.get("step") != step:
            problems.append(f"{step}: entry step is {entry.get('step')!r}")
        choices = entry.get("choices")
        if not isinstance(choices, list) or not choices:
            problems.append(f"{step}: choices must be a non-empty list")
            continue
        for i, choice in enumerate(choices):
            where = f"{step}.choices[{i}]"
            if not isinstance(choice, dict):
                problems.append(f"{where}: not an object")
                continue
            rows += 1
            bid = choice.get("id")
            if not isinstance(bid, str) or not bid:
                problems.append(f"{where}: id must be a non-empty string")
            elif bid in seen_ids:
                problems.append(f"{where}: duplicate branch id {bid!r}")
            else:
                seen_ids.add(bid)
            if choice.get("step") != step:
                problems.append(f"{where}: step must equal {step!r}")
            scene = choice.get("scene")
            if not isinstance(scene, str) or not scene:
                problems.append(f"{where}: scene must be a non-empty string")
            elif scene not in scenes_by_step.get(step, set()):
                problems.append(f"{where}: scene {scene!r} is not an index scene of {step}")
            locid = choice.get("choice_locid")
            if not isinstance(locid, int) or isinstance(locid, bool) or locid <= 0:
                problems.append(f"{where}: choice_locid must be a positive integer")
            sets = choice.get("sets")
            if not isinstance(sets, list) or not sets or any(not isinstance(f, str) or not f for f in sets):
                problems.append(f"{where}: sets must be a non-empty list of fact names")
            elif sets != sorted(set(sets)):
                problems.append(f"{where}: sets must be sorted and unique")
            tests = choice.get("tests")
            if not isinstance(tests, list) or any(not isinstance(f, str) or not f for f in tests):
                problems.append(f"{where}: tests must be a list of fact names")
            elif tests != sorted(set(tests)):
                problems.append(f"{where}: tests must be sorted and unique")
            if choice.get("one_shot") is not False:
                problems.append(f"{where}: one_shot must be false")
            text = choice.get("choice_text")
            if text is not None and not isinstance(text, str):
                problems.append(f"{where}: choice_text must be a string or null")
            source = choice.get("source")
            if not isinstance(source, dict):
                problems.append(f"{where}: source must be an object")
            else:
                if set(source) != {"kind", "file", "locid"}:
                    problems.append(f"{where}: source keys must be kind, file, locid")
                if source.get("kind") != "scene_choice":
                    problems.append(f"{where}: source.kind must be scene_choice")
                if source.get("file") != scene:
                    problems.append(f"{where}: source.file must equal scene")
                if source.get("locid") != locid:
                    problems.append(f"{where}: source.locid must equal choice_locid")

    if set(branches) != route_branch:
        missing = sorted(route_branch - set(branches))
        extra = sorted(set(branches) - route_branch)
        if missing:
            problems.append(f"{len(missing)} route step(s) marked branch have no branch row: {missing[:5]}")
        if extra:
            problems.append(f"{len(extra)} branch step(s) are not marked branch in route.json: {extra[:5]}")

    for step in sorted(s for s in step_quest if s.startswith(("q704", "q705"))):
        if not scenes_by_step.get(step):
            problems.append(f"{step}: DLC step has no index scene rows")
    dlc_rows = sum(len(entry.get("choices") or []) for step, entry in branches.items()
                   if step.startswith(("q704", "q705")))
    if dlc_rows == 0:
        problems.append("the q704*/q705* DLC family produced zero branches")

    if rows == 0:
        problems.append("the branch graph is empty")
    return problems


def summarise(doc, pairs):
    pack_of_step, steps_by_pack, rows_by_pack = counts(doc, pairs)
    untranslated = sum(1 for entry in doc["branches"].values()
                       for choice in entry["choices"] if choice.get("choice_text") is None)
    return pack_of_step, steps_by_pack, rows_by_pack, untranslated


def build():
    route, quests, pairs = load_inputs()
    doc = extract(route, quests, pairs)
    problems = validate(doc, route, quests, pairs)
    if problems:
        print(f"{len(problems)} problem(s); refusing to write {OUT.name}:")
        for problem in problems[:30]:
            print("  ", problem)
        return 1
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    _pack, steps, rows, untranslated = summarise(doc, pairs)
    total_rows = sum(rows.values())
    print(f"wrote {OUT.name}: {total_rows} branches on {sum(steps.values())} steps "
          f"({', '.join(f'{p} {rows[p]}/{steps[p]}' for p in ('base', 'ep1', 'bob', 'other_dlc', 'gwent'))}); "
          f"0 contract, 0 one-shot; {untranslated} without choice text")
    return 0


def check():
    route, quests, pairs = load_inputs()
    if not OUT.exists():
        print(f"{OUT.name} not found; run py tools/branchgen.py build")
        return 1
    try:
        actual = json.loads(OUT.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        print(f"cannot read {OUT.name}: {exc}")
        return 1
    expected = extract(route, quests, pairs)
    problems = validate(actual, route, quests, pairs)
    if actual != expected:
        problems.append("file differs from a fresh extraction; run py tools/branchgen.py build")
        if isinstance(actual.get("branches"), dict):
            missing = sorted(set(expected["branches"]) - set(actual["branches"]))
            extra = sorted(set(actual["branches"]) - set(expected["branches"]))
            if missing:
                problems.append(f"steps missing from the file: {missing[:5]}")
            if extra:
                problems.append(f"steps not in the extraction: {extra[:5]}")
            for step in sorted(set(expected["branches"]) & set(actual["branches"])):
                if expected["branches"][step] != actual["branches"][step]:
                    problems.append(f"{step}: branch rows differ from the extraction")
                    break
    if problems:
        print(f"{len(problems)} problem(s):")
        for problem in problems[:30]:
            print("  ", problem)
        return 1
    _pack, steps, rows, untranslated = summarise(actual, pairs)
    print(f"branches ok: {sum(rows.values())} branches on {sum(steps.values())} steps "
          f"({', '.join(f'{p} {rows[p]}/{steps[p]}' for p in ('base', 'ep1', 'bob', 'other_dlc', 'gwent'))}); "
          f"0 contract, 0 one-shot; {untranslated} without choice text")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build":
        sys.exit(build())
    if cmd == "check":
        sys.exit(check())
    print(__doc__)
    sys.exit(2)
