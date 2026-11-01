"""One index of what the game's own files say about each quest.

Built from REDkit's resources plus the editor string database, and cached to `quest_index.json`
(git-ignored, regenerate freely). Read-only.

For each journal file (the name `route.json` uses in `files`, e.g. `q203him`) this collects:

  name / objectives   the quest-log text: the quest's title locId and every objective locId, in
                      quest-log order, with the entry GUID the save records. Both come from the
                      .journal file itself; the text comes from the string database.
  type / order        `CJournalQuest.type` (Chapter, Side, MonsterHunt, TreasureHunt) and the
                      journal's own sort key. The type is absent for 32 entries; the order is not a
                      story sequence and is used only as a tie-break.
  description         the lowest-order `CJournalQuestDescriptionEntry` in the file: the quest's
                      pre-quest summary, resolved through the string database.
  level               the suggested level, joined from the six `quest_levels.csv` files by the
                      journal entry's `baseName`.
  has_branch          a scene choice whose section sets a fact: taking it decides a fact, so it is
                      an outcome branch. A one-shot dialogue row is never a branch.
  has_dialogue_choice a one-shot (`singleUseChoice`) dialogue row. The choice text is indexed for
                      the audit tools but never shipped to the app.
  branch_facts        the facts those branches set, with the scene that sets them (see `choices`).
  has_gwent           the quest's own objective text is about playing cards.
  activator           the graph block that adds the quest's journal entry (`CJournalQuestBlock`
                      / `CJournalQuestTrackBlock`), with the file it lives in. None means the game
                      does not name a start in a phase graph: it starts from dialogue or script.
  facts               every fact the quest's own phase files and scenes name, split into
                      `set` (a block that changes the fact) and `test` (a condition that waits on it).
  deactivates         spawnsets/communities its story-phase setters switch off, and the impulses
                      it activates. This is the mechanism behind a cutoff: what one quest turns off.
  choices             dialogue choices from its scenes: the choiceLine locId (resolved to the
                      game's own words), whether it can be taken only once, the facts the
                      surrounding section waits on, and the facts taking it sets.
  dialogue_only       facts its scenes name that no phase block anywhere sets: the choice, not the
                      quest script, decides them.

  py questindex.py build [--all]     build/update the cache (route quests by default, every quest with --all)
  py questindex.py quest <stem>      what the index has for one quest
  py questindex.py choices <stem>    its dialogue choices, with the game's wording
  py questindex.py facts <stem>      its facts, with who sets and who tests them
  py questindex.py text <stem>       the game's own quest-log text
  py questindex.py check             the section_sets fixture (Whispering Hillock spirit choice)
"""
import json
import re
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cr2w
import questgraph
import stringsdb
from paths import HERE, REDKIT_R4
from resources import (is_dlc_journal, is_dlc_path,
                       journal_files as quest_journal_files,
                       phase_files as quest_phase_files)

CACHE = HERE / "quest_index.json"

SET_CLASSES = ("ChangingBlock", "FactSet", "SetFact", "CStorySceneActionFact")
TEST_CLASSES = ("Condition", "FlowCondition")

# A scene changes a fact through a `CStorySceneScript` that runs a named function; the game's own
# comment on an `AddFact_S` script names the fact it adds (`add q105_what_happened`,
# `mh102_tavern_man_met +1`). There is no factId property to read, so the comment is the evidence,
# and anything that does not read back as a fact identifier is refused rather than guessed.
SCENE_SET_FUNCS = ("AddFact_S", "SetFact_S")
SCENE_ADD = re.compile(r"^\s*(?:add|set)\s+", re.I)
SCENE_COUNT = re.compile(r"\s*(?:\+=|-=|\+|-)\s*\d+\s*$|\s+\d+\s*$")
FACT_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,}$")

# Contract dialogue sets its own bookkeeping facts (the offer was declined, the reward refused, the
# job taken). That rearranges the contract conversation; it is not a quest-content branch, and no
# contract step carries the branch chip. The rows stay `has_dialogue_choice` bookkeeping.
NO_BRANCH_TYPES = ("MonsterHunt",)

# The fixture for the section_sets probe: the Whispering Hillock spirit choice. Destroying or
# releasing the spirit leads to sections 195/197, each followed by the `q105_show_lights_cutear`
# script; before the linked-block walk every row in this scene read `section_sets: []`.
FIXTURE_SCENE = Path("quests/part_1/quest_files/q105_witches/scenes/q105_09a_burrows_soltis_problem.w2scene")
FIXTURE_SETS = {416131: "q105_what_happened", 416133: "q105_from_when",
                380671: "q105_show_lights_cutear", 380673: "q105_show_lights_cutear",
                380675: "q105_show_lights_cutear"}


def chunk_array(value):
    """A CR2W array of export indices: raw little-endian `<count><index>...` u32s."""
    if not isinstance(value, dict) or "raw_hex" not in value:
        return []
    try:
        raw = bytes.fromhex(value["raw_hex"])
    except ValueError:
        return []
    if len(raw) < 4:
        return []
    n = struct.unpack_from("<I", raw, 0)[0]
    if 4 + 4 * n != len(raw):
        return []
    return [struct.unpack_from("<I", raw, 4 + 4 * i)[0] for i in range(n)]


def scene_script_fact(pr):
    """The fact an `AddFact_S` scene script sets, read from the game's own comment, or None."""
    if pr.get("functionName") not in SCENE_SET_FUNCS:
        return None
    comment = pr.get("comment")
    if not isinstance(comment, str):
        return None
    name = SCENE_COUNT.sub("", SCENE_ADD.sub("", comment)).strip()
    return name if FACT_NAME.match(name) else None


def rel(p):
    try:
        return str(Path(p).relative_to(REDKIT_R4))
    except ValueError:
        return str(p)


def normal(s):
    """'q206_berserkers' and 'q206berserkers' are the same quest."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


# --------------------------------------------------------------------------- journal files
def journal_struct(jf):
    """The quest log definition: title locId, the quest entry GUID, phases and their objectives."""
    p = cr2w.parse(jf)
    ex = {e["index"]: e for e in p["exports"]}
    props = {}
    for e in p["exports"]:
        props[e["index"]] = {v["name"]: v["value"] for v in cr2w.props(p, e)}

    def guid(i):
        g = props.get(i, {}).get("guid")
        return g.get("raw_hex") if isinstance(g, dict) else None

    def locid(i):
        t = props.get(i, {}).get("title")
        return t.get("locId") if isinstance(t, dict) else None

    quest = next((e for e in p["exports"] if e["className"] == "CJournalQuest"), None)
    out = {"stem": jf.stem.lower(), "file": rel(jf), "title_locid": None, "entry_guid": None,
           "type": None, "order": None, "base_name": "", "content_type": "", "has_quest": False,
           "description_locid": None, "phases": [], "objectives": [], "descriptions": [], "pins": []}
    if quest is None:
        return out
    out["has_quest"] = True
    out["title_locid"] = locid(quest["index"])
    out["entry_guid"] = guid(quest["index"])
    qp = props.get(quest["index"], {})
    out["type"] = qp.get("type") if isinstance(qp.get("type"), str) else None
    out["order"] = qp.get("order") if isinstance(qp.get("order"), int) else None
    out["base_name"] = qp.get("baseName") if isinstance(qp.get("baseName"), str) else ""
    out["content_type"] = qp.get("contentType") if isinstance(qp.get("contentType"), str) else ""

    def children(i, cls=None):
        return [e for e in p["exports"] if e["parentID"] == i and (cls is None or e["className"] == cls)]

    for e in p["exports"]:
        if e["className"] == "CJournalQuestPhase":
            phase = {"guid": guid(e["index"]), "name": props.get(e["index"], {}).get("baseName", ""), "objectives": []}
            for o in children(e["index"], "CJournalQuestObjective"):
                # the game sorts objectives by this key, not by export order; keep it so the
                # consumers can show the list in the order the game shows it
                ord_ = props.get(o["index"], {}).get("order")
                obj = {"guid": guid(o["index"]), "name": props.get(o["index"], {}).get("baseName", ""),
                       "locid": locid(o["index"]), "pins": len(children(o["index"], "CJournalQuestMapPin")),
                       "order": ord_ if isinstance(ord_, int) else None}
                phase["objectives"].append(obj)
                out["objectives"].append(obj)
            out["phases"].append(phase)
    # description entries are not objectives, but the save records them and some quests move their
    # whole status onto one, so keep their GUIDs to recognise them
    def desc_locid(i):
        d = props.get(i, {}).get("description")
        return d.get("locId") if isinstance(d, dict) else (d if isinstance(d, int) else None)

    out["descriptions"] = [
        {"guid": guid(e["index"]), "name": props.get(e["index"], {}).get("baseName", ""),
         "order": props.get(e["index"], {}).get("order") if isinstance(props.get(e["index"], {}).get("order"), int) else None,
         "locid": desc_locid(e["index"])}
        for e in p["exports"] if e["className"] in ("CJournalQuestDescriptionEntry", "CJournalQuestDescriptionGroup")
    ]
    rows = [d for d in out["descriptions"] if d.get("locid")]
    out["description_locid"] = min(rows, key=lambda d: (d.get("order") if d.get("order") is not None else 2**31, d["guid"]))["locid"] if rows else None
    return out


def journal_index():
    """stem -> journal_struct for every CJournalQuest journal REDkit ships (base + DLC)."""
    out = {}
    bad = []
    for jf in quest_journal_files():
        try:
            j = journal_struct(jf)
        except Exception as ex:
            bad.append((jf.name, type(ex).__name__, str(ex)[:80]))
            continue
        if not j["has_quest"]:
            continue  # a journal container without a quest entry (combat, generic lists, ...)
        stem = jf.stem.lower()
        if stem in out:
            # two DLCs should not ship the same stem; keep the first and report the collision
            bad.append((jf.name, "DuplicateStem", out[stem]["file"]))
            continue
        out[stem] = j
    return out, bad


def guid_raw(dashed):
    """'B5130AE1-468A2171-...' -> the raw 16 bytes as hex, the form the resources and saves use."""
    return b"".join(int(p, 16).to_bytes(4, "little") for p in dashed.split("-")).hex()


def bundle_journals():
    """The journal files inside the player's game bundles (the names the tracker and route use):
    short name -> {'file', 'ids': [[entry name, guid]]}, from the same scan the app itself runs."""
    from paths import QDB
    if not QDB.exists():
        return {}
    db = json.loads(QDB.read_text(encoding="utf-8"))
    out = {}
    for key, val in db.items():
        short = Path(key).name.replace(".journal", "").lower()
        if not short:
            continue
        out[short] = {"file": val.get("file", ""), "ids": val.get("ids", [])}
    return out


def aliases(journals, bundled):
    """bundled journal name -> REDkit journal name.

    The two layers do not agree on file names (the bundles call the statuette quest
    `mq3012noblestatuette`, REDkit calls it `mq3012_jade_statuettes`), so they are joined by the
    entry GUID the files themselves carry - which is also the GUID the save records - with a
    name match as a fallback. Without this join, a route step looks like it has no game-file
    evidence when in fact the files are there under another name.
    """
    by_guid = {j["entry_guid"]: stem for stem, j in journals.items() if j.get("entry_guid")}
    by_norm = {}
    for stem in journals:
        by_norm.setdefault(normal(stem), stem)
    out, how = {}, {}
    for short, val in bundled.items():
        guid = next((g for _n, g in val["ids"] if g), None)
        hit = by_guid.get(guid_raw(guid)) if guid and "-" in guid else by_guid.get((guid or "").lower())
        if hit:
            out[short], how[short] = hit, "guid"
        else:
            hit = by_norm.get(normal(short))
            if hit:
                out[short], how[short] = hit, "name"
    return out, how


# --------------------------------------------------------------------------- phase files

def quest_folder(phase_path):
    """The folder holding a quest's scenes, from its phase file.

    A DLC phase either sits beside `quest_files/<quest>` or inside a `<quest>/phases` subtree.
    For DLC, climb to the nearest `quest_files` directory first: the first component below it is
    the quest folder. That attaches the nested q704 phases. The base game keeps its previous
    rule so the base index does not change in the same step.
    """
    p = Path(phase_path)
    if is_dlc_path(p):
        for parent in p.parents:
            if parent.name.lower() != "quest_files":
                continue
            rel = p.relative_to(parent)
            if len(rel.parts) >= 2 and rel.parts[0].lower() not in ("phases", "scenes"):
                cand = parent / rel.parts[0]
                if cand.is_dir():
                    return cand
            break
    cand = p.parent / "quest_files" / p.stem
    if cand.is_dir():
        return cand
    hits = list(p.parent.glob(f"quest_files/{p.stem}*"))
    return hits[0] if hits else None


def phase_facts(path):
    """{'set': [...], 'test': [...], 'ref': [...]} for one phase or scene file, with the block class."""
    p = cr2w.parse(path)
    sets, tests, refs = [], [], []
    for e, ps in cr2w.all_props(p):
        cls = e["className"]
        for v in ps:
            if v["name"].lower() in ("factid", "fact", "factname", "fact_id") and isinstance(v["value"], str) and v["value"]:
                fact = v["value"]
                if any(x in cls for x in SET_CLASSES):
                    sets.append((fact, cls))
                elif any(x in cls for x in TEST_CLASSES):
                    tests.append((fact, cls))
                else:
                    refs.append((fact, cls))
    return {"set": sets, "test": tests, "ref": refs}


def switches(path):
    """What one phase switches on and off: deactivated spawnsets/communities, activated impulses."""
    p = cr2w.parse(path)
    kids = defaultdict(list)
    for c in p["exports"]:
        kids[c["parentID"]].append(c)
    off, on = set(), set()
    for e in p["exports"]:
        if e["className"] not in ("CQuestStoryPhaseSetterBlock", "CQuestPhaseSetterBlock", "CQuestStorySceneBlock"):
            continue
        for c in kids.get(e["index"], []):
            for v in cr2w.props(p, c):
                val = v["value"]
                ref = val.get("ref_import") if isinstance(val, dict) else None
                if not ref:
                    continue
                if c["className"] == "CDeactivateSpawnset":
                    off.add(ref)
                elif c["className"] in ("CActivateSpawnset", "CActivateCommunity", "CActivateSpawnTree",
                                         "CActivateStoryPhase", "CActivateStoryScene"):
                    on.add(ref)
    return sorted(off), sorted(on)


# --------------------------------------------------------------------------- scenes

def scene_choices(path):
    """The dialogue choices of one scene: locId, the facts its section names, the facts taking it
    sets, and the one-shot flag.

    `section_sets` is what the choice's own branch sets. The settle blocks are not children of the
    section: a `CStorySceneScript` block lists in `linkedElements` the sections it runs after, and
    a section's `nextLinkElement` carries the branch on to the next block, so the branch is a walk
    through those links. The walk stops at the next choice section, because the choices in it own
    the facts that follow. `section_facts` stays the facts named anywhere in the section's own
    subtree (the conditions a choice waits on).
    """
    try:
        p = cr2w.parse(path)
    except Exception:
        return []
    ex = {e["index"]: e for e in p["exports"]}
    props = {}
    kids = defaultdict(list)
    for e in p["exports"]:
        props[e["index"]] = {v["name"]: v["value"] for v in cr2w.props(p, e)}
        kids[e["parentID"]].append(e["index"])

    def ref(i, name):
        v = props.get(i, {}).get(name)
        return v.get("ref_chunk") if isinstance(v, dict) else None

    def section_of(i, limit=12):
        """The CStorySceneSection an element belongs to, from its parent chain."""
        for _ in range(limit):
            if not i or i not in ex:
                return None
            if ex[i]["className"] == "CStorySceneSection":
                return i
            i = ex[i]["parentID"]
        return None

    def facts_under(root):
        """facts named by any export in the subtree below root"""
        out = set()
        stack = [root]
        seen = set()
        while stack:
            i = stack.pop()
            if i in seen:
                continue
            seen.add(i)
            for name, val in props.get(i, {}).items():
                if name.lower() in ("factid", "fact", "factname") and isinstance(val, str) and val:
                    out.add(val)
            stack.extend(kids.get(i, []))
        return sorted(out)

    # every block in the scene that changes a fact, with the facts it names
    setters = {}
    for i in ex:
        found = set()
        for name, val in props.get(i, {}).items():
            if (name.lower() in ("factid", "fact", "factname", "fact_id") and isinstance(val, str)
                    and val and any(x in ex[i]["className"] for x in SET_CLASSES)):
                found.add(val)
        fact = scene_script_fact(props.get(i, {}))
        if fact:
            found.add(fact)
        if found:
            setters[i] = sorted(found)

    def section_sets(sec):
        """facts a section sets: its own subtree setters and the script blocks that follow it"""
        out = set()
        stack = [sec]
        seen = set()
        while stack:
            i = stack.pop()
            if i in seen:
                continue
            seen.add(i)
            if i in setters and ex[i]["className"] != "CStorySceneScript":
                out.update(setters[i])
            stack.extend(kids.get(i, []))
        for i, facts in setters.items():
            if ex[i]["className"] != "CStorySceneScript":
                continue
            if any(section_of(t) == sec for t in chunk_array(props[i].get("linkedElements"))):
                out.update(facts)
        return out

    memo = {}

    def sets_of(sec):
        if sec not in memo:
            memo[sec] = section_sets(sec)
        return memo[sec]

    def branch_sets(line):
        """facts set by taking this choice, following the scene's own links"""
        found = set()
        cur = ref(line, "nextLinkElement")
        seen = set()
        for _ in range(60):
            if not cur or cur not in ex or cur in seen:
                break
            seen.add(cur)
            cls = ex[cur]["className"]
            if cls in ("CStorySceneSection", "CStorySceneCutsceneSection"):
                found.update(sets_of(cur))
                if ref(cur, "choice"):
                    break  # the choices in that section own what follows them
            elif cur in setters:
                found.update(setters[cur])
            cur = ref(cur, "nextLinkElement")
        return sorted(found)

    out = []
    for e in p["exports"]:
        if e["className"] != "CStorySceneChoiceLine":
            continue
        cl = props[e["index"]].get("choiceLine")
        locid = cl.get("locId") if isinstance(cl, dict) else None
        # the choice line sits under CStorySceneChoice under CStorySceneSection
        sec = section_of(e["index"])
        out.append({
            "locid": locid,
            "one_shot": bool(props[e["index"]].get("singleUseChoice")),
            "section_facts": facts_under(sec) if sec else [],
            "section_sets": branch_sets(e["index"]),
        })
    return out


def section_probe_check(verbose=True):
    """Regression gate for `section_sets` on the Whispering Hillock spirit-choice scene.

    The destroy/release choice leads to sections 195/197, both followed by the `show lights`
    script, and the other two choices lead to sections 47/522, followed by `add ...` scripts. A
    probe that only walks parentID children returns [] for all of them, so this fails the build.
    """
    rows = {r["locid"]: r for r in scene_choices(REDKIT_R4 / FIXTURE_SCENE)}
    problems = []
    for locid, fact in FIXTURE_SETS.items():
        row = rows.get(locid)
        if row is None:
            problems.append(f"choice {locid} is not in the fixture scene")
        elif fact not in row["section_sets"]:
            problems.append(f"choice {locid} does not set {fact}: {row['section_sets']}")
    one_shot = [r["locid"] for r in rows.values() if r["one_shot"]]
    problems.extend(f"one-shot row {locid} read as a branch" for locid in one_shot)
    if problems:
        raise SystemExit("section_sets probe failed: " + "; ".join(problems))
    if verbose:
        print(f"  section_sets fixture ok: {len(FIXTURE_SETS)} choices in the Whispering Hillock "
              f"spirit scene set a fact", flush=True)


def scene_lines(path):
    """Scene line locIds, so the game's wording of a scene is reachable (used to quote a warning)."""
    try:
        p = cr2w.parse(path)
    except Exception:
        return []
    out = []
    for e, ps in cr2w.all_props(p):
        if e["className"] == "CStorySceneLine":
            for v in ps:
                if v["name"] == "line" and isinstance(v["value"], dict) and "locId" in v["value"]:
                    out.append(v["value"]["locId"])
    return out


# --------------------------------------------------------------------------- build

def interesting_stems():
    """The quests the tracker talks about: every step in route.json."""
    from paths import ROUTE
    route = json.loads(ROUTE.read_text(encoding="utf-8"))
    stems = set()
    for n in route.get("nodes", []):
        for f in n.get("files", []):
            for part in re.split(r"[|#]", f):
                if part:
                    stems.add(part.lower())
    return stems


JOURNAL_MENTION = re.compile(rb"([a-z0-9_]+)\.journal", re.I)

# Phase files that belong to the build rather than to one quest: they mention many quests, so they
# must not count as anybody's "own" file when asking what a quest needs. They are still used for
# the journal-activation walk, where being global is the point.
GLOBAL_HINTS = ("bugfixing_phase", "additional_game_elements", "witcher3_structure", "books_read",
                "character_journal_entries", "ff_all_hubs", "videos_scenes", "dev_", 
                "cutscenes", "dlc_disabled")


def is_global(path_like):
    low = str(path_like).lower().replace("/", "\\")
    return any(h in low for h in GLOBAL_HINTS)


GWENT_TEXT = re.compile(r"gwent|unique card|play cards", re.I)


def level_map():
    """normalised quest name -> suggested level, from every quest_levels.csv the install ships."""
    out = {}
    for p in sorted(REDKIT_R4.rglob("quest_levels.csv")):
        with p.open(encoding="utf-8-sig") as fh:
            next(fh, None)
            for line in fh:
                if ";" not in line:
                    continue
                name, _sep, lv = line.strip().partition(";")
                lv = lv.strip()
                if name and lv.isdigit():
                    out.setdefault(normal(name), int(lv))
    return out


def add_texts(idx, verbose=True):
    """Resolve type fallbacks, descriptions, levels, Gwent, branch and dialogue-choice flags."""
    con = stringsdb.con()
    levels = level_map()
    desc_ids = {s: j["description_locid"] for s, j in idx["journals"].items() if j.get("description_locid")}
    desc_text = stringsdb.locs(desc_ids.values(), con)
    obj_locs = {}
    for s, j in idx["journals"].items():
        for o in j.get("objectives", []):
            if o.get("locid"):
                obj_locs.setdefault(s, []).append(o["locid"])
    gwent = set()
    for s, locids in obj_locs.items():
        m = stringsdb.locs(locids, con)
        if any(GWENT_TEXT.search(t or "") for t in m.values()):
            gwent.add(s)
    levelled = 0
    for stem, q in idx["quests"].items():
        j = idx["journals"].get(stem, {})
        q["type"] = j.get("type")
        q["order"] = j.get("order")
        q["base_name"] = j.get("base_name", "")
        q["content_type"] = j.get("content_type", "")
        q["description_locid"] = j.get("description_locid")
        q["description"] = (desc_text.get(j["description_locid"]) or "") if j.get("description_locid") else ""
        q["level"] = levels.get(normal(q["base_name"])) if q["base_name"] else None
        if q["level"] is not None:
            levelled += 1
        q["has_gwent"] = stem in gwent
        rows = [ch for sc in q.get("scenes", []) for ch in sc.get("choices", [])]
        q["has_dialogue_choice"] = any(ch.get("one_shot") for ch in rows)
        # a one-shot row is dialogue, never an outcome branch; a branch must actually set a fact
        q["branch_facts"] = sorted({f for ch in rows if not ch.get("one_shot")
                                    for f in ch.get("section_sets", [])})
        q["has_branch"] = bool(q["branch_facts"]) and q["type"] not in NO_BRANCH_TYPES
    idx["levels"] = {"rows": len(levels), "matched": levelled, "total": len(idx["quests"]),
                     "gwent": sorted(gwent),
                     "branch": sorted(s for s, q in idx["quests"].items() if q["has_branch"]),
                     "dialogue_choice": sorted(s for s, q in idx["quests"].items() if q["has_dialogue_choice"])}
    if verbose:
        print(f"  levels: {levelled}/{len(idx['quests'])} matched, gwent {len(gwent)}, "
              f"branch {len(idx['levels']['branch'])}, "
              f"dialogue choice {len(idx['levels']['dialogue_choice'])}", flush=True)


def build(every=False, verbose=True):
    """Index every quest the tracker talks about (or all of them with `every=True`)."""
    journals, bad_journals = journal_index()
    bundled = bundle_journals()
    alias, how = aliases(journals, bundled)
    want = set(journals) if every else interesting_stems()
    idx = {"note": "built from REDkit resources + the editor string database; read-only",
           "journals": {}, "quests": {}, "unreadable_journals": bad_journals,
           "alias": alias, "alias_how": how}

    for stem, j in journals.items():
        idx["journals"][stem] = {"file": j["file"], "title_locid": j["title_locid"],
                                 "entry_guid": j["entry_guid"], "objectives": j["objectives"],
                                 "phases": j["phases"], "descriptions": j["descriptions"],
                                 "type": j["type"], "order": j["order"], "base_name": j["base_name"],
                                 "content_type": j["content_type"], "has_quest": True,
                                 "description_locid": j["description_locid"]}

    # Which REDkit journal files each phase file is about. The file names differ between the
    # bundles and REDkit, so a phase file is attributed to a quest when it names that quest's
    # journal resource - the same rule the graph walk uses.
    covered = defaultdict(list)
    deacts = defaultdict(list)
    aggregate = []
    for ph in quest_phase_files():
        try:
            b = ph.read_bytes()
        except OSError:
            continue
        stems = {m.group(1).decode().lower() for m in JOURNAL_MENTION.finditer(b)} & set(journals)
        if is_dlc_path(ph):
            # a DLC phase must not add rows to a base quest: the base index stays as it was
            stems = {s for s in stems if is_dlc_journal(journals.get(s, {}).get("file"))}
        # a phase file that names more than a handful of quests is one of the build's aggregate
        # files (part_1_sidequests, bugfixing_phase...), not a quest's own file: its deactivations
        # are phase transitions in the story, not a cutoff caused by one quest
        agg = len(stems) > 6 or is_global(rel(ph))
        if agg:
            aggregate.append(rel(ph))
        for stem in stems:
            covered[stem].append(ph)
        if stems and not agg:
            try:
                off, on = switches(ph)
            except Exception:
                off, on = [], []
            for stem in stems:
                deacts[stem].append({"file": rel(ph), "deactivates": off, "activates": on})

    # the quests to index: everything the route names, whether or not it has a phase of its own
    redkit_want = set()
    for stem in want:
        redkit_want.add(alias.get(stem, stem))
        redkit_want.add(stem)
    for stem in sorted(redkit_want):
        if stem not in journals and stem not in covered:
            continue
        j = journals.get(stem, {})
        q = {"stem": stem, "bundle_names": sorted(k for k, v in alias.items() if v == stem),
             "file": j.get("file"), "name_locid": j.get("title_locid"), "entry_guid": j.get("entry_guid"),
             "type": j.get("type"), "order": j.get("order"), "base_name": j.get("base_name", ""),
             "content_type": j.get("content_type", ""), "description_locid": j.get("description_locid"),
             "objectives": j.get("objectives", []), "phases": [], "scenes": [], "switches": deacts.get(stem, [])}
        for ph in sorted(set(covered.get(stem, []))):
            try:
                f = phase_facts(ph)
            except Exception:
                continue
            q["phases"].append({"file": rel(ph), "set": f["set"], "test": f["test"], "ref": f["ref"],
                                "global": is_global(rel(ph)) or rel(ph) in aggregate})
        folders = {quest_folder(ph) for ph in sorted(set(covered.get(stem, [])))
                   if not is_global(rel(ph))}
        for folder in sorted(f for f in folders if f):
            for sc in sorted(folder.rglob("*.w2scene")):
                try:
                    f = phase_facts(sc)
                except Exception:
                    continue
                q["scenes"].append({"file": rel(sc), "set": f["set"], "test": f["test"], "ref": f["ref"],
                                    "choices": scene_choices(sc)})
        idx["quests"][stem] = q
        if verbose and (q["phases"] or q["scenes"]):
            print(f"  {stem:32s} {len(q['phases'])} phase file(s), {len(q['scenes'])} scene(s)", flush=True)

    # a fact no phase block anywhere sets can only be decided by dialogue
    all_sets = set()
    for q in idx["quests"].values():
        for ph in q["phases"]:
            all_sets.update(f for f, _c in ph["set"])
    for q in idx["quests"].values():
        q["dialogue_only"] = sorted({f for sc in q["scenes"] for f, _c in sc["set"] if f not in all_sets})
    add_texts(idx, verbose=verbose)
    section_probe_check(verbose=verbose)
    idx["phaseless"] = sorted(s for s in want if not idx["quests"].get(alias.get(s, s), {}).get("phases"))
    idx["aggregate_phase_files"] = sorted(set(aggregate))
    return idx


def set_activators(idx, verbose=True):
    """Add `activators`: the graph blocks that add a journal entry.

    One pass over the phase files (reading and parsing each at most once), not one pass per quest.
    """
    stems = set(idx["quests"])
    for q in idx["quests"].values():
        q["activators"] = []
        q["failures"] = []
    for ph in quest_phase_files():
        try:
            b = ph.read_bytes()
        except OSError:
            continue
        # a quest name only counts when the file names that quest's own journal resource, so
        # 'mine' does not match every file that happens to contain the word
        here = sorted({m.group(1).decode().lower() for m in JOURNAL_MENTION.finditer(b)} & stems)
        if is_dlc_path(ph):
            here = [s for s in here
                    if is_dlc_journal(idx["journals"].get(s, {}).get("file"))]
        if not here:
            continue
        try:
            g = questgraph.G(ph)
        except Exception:
            continue
        for stem in here:
            try:
                blocks = g.blocks_for(stem)
                fails = {f["block"] for f in g.failure_sockets(blocks)}
                for blk in blocks:
                    # `guids` is the journal path's GUID chain: it tells a block that adds the quest
                    # itself from one that adds an objective of it (see tools/prereqs.py)
                    idx["quests"][stem]["activators"].append(
                        {"file": rel(ph), "block": blk["index"], "class": blk["class"],
                         "resource": blk["resource"], "label": blk["label"],
                         "guids": [g.lower() for g in blk.get("guids", [])]})
                    if blk["index"] in fails:
                        # a journal block with a `Failure` output: the quest's own graph says it can end here
                        idx["quests"][stem]["failures"].append(
                            {"file": rel(ph), "block": blk["index"], "class": blk["class"],
                             "resource": blk["resource"], "label": blk["label"]})
            except Exception:
                continue
        if verbose and here:
            print(f"  activators: {rel(ph)} -> {', '.join(here)}", flush=True)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "build":
        every = "--all" in sys.argv
        idx = build(every=every)
        set_activators(idx)
        CACHE.write_text(json.dumps(idx, sort_keys=True, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {CACHE.name}: {len(idx['quests'])} quests, {len(idx['journals'])} journal files, "
              f"{len(idx['unreadable_journals'])} journals unreadable")
    elif cmd == "check":
        section_probe_check()
    else:
        idx = json.loads(CACHE.read_text(encoding="utf-8"))
        stem = sys.argv[2].lower() if len(sys.argv) > 2 else ""
        q = idx["quests"].get(stem)
        if not q:
            print("not in the index:", stem)
            return
        c = stringsdb.con()
        if cmd == "quest":
            print(json.dumps(q, indent=1)[:4000])
        elif cmd == "choices":
            for sc in q["scenes"]:
                for ch in sc["choices"]:
                    text = stringsdb.loc(ch["locid"], c) if ch["locid"] else ""
                    if text:
                        print(f"  {'[one-shot] ' if ch['one_shot'] else ''}{sc['file']}\n      {text!r}  "
                              f"facts={ch['section_facts']} sets={ch['section_sets']}")
        elif cmd == "facts":
            for ph in q["phases"]:
                print(f"  {ph['file']}")
                for f, cls in ph["set"]:
                    print(f"     SET  {f:44s} {cls}")
                for f, cls in ph["test"]:
                    print(f"     TEST {f:44s} {cls}")
        elif cmd == "text":
            for o in q.get("objectives", []):
                print(f"  {stringsdb.loc(o['locid'], c) if o['locid'] else ''}")


if __name__ == "__main__":
    main()
