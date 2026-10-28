"""One index of what the game's own files say about each quest.

Built from REDkit's resources plus the editor string database, and cached to `quest_index.json`
(git-ignored, regenerate freely). Read-only.

For each journal file (the name `route.json` uses in `files`, e.g. `q203him`) this collects:

  name / objectives   the quest-log text: the quest's title locId and every objective locId, in
                      quest-log order, with the entry GUID the save records. Both come from the
                      .journal file itself; the text comes from the string database.
  activator           the graph block that adds the quest's journal entry (`CJournalQuestBlock`
                      / `CJournalQuestTrackBlock`), with the file it lives in. None means the game
                      does not name a start in a phase graph: it starts from dialogue or script.
  facts               every fact the quest's own phase files and scenes name, split into
                      `set` (a block that changes the fact) and `test` (a condition that waits on it).
  deactivates         spawnsets/communities its story-phase setters switch off, and the impulses
                      it activates. This is the mechanism behind a cutoff: what one quest turns off.
  choices             dialogue choices from its scenes: the choiceLine locId (resolved to the
                      game's own words), whether it can be taken only once, and the facts the
                      surrounding section waits on.
  dialogue_only       facts its scenes name that no phase block anywhere sets: the choice, not the
                      quest script, decides them.

  py questindex.py build [--all]     build/update the cache (route quests by default, every quest with --all)
  py questindex.py quest <stem>      what the index has for one quest
  py questindex.py choices <stem>    its dialogue choices, with the game's wording
  py questindex.py facts <stem>      its facts, with who sets and who tests them
  py questindex.py text <stem>       the game's own quest-log text
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cr2w
import questgraph
import stringsdb
from paths import HERE, JOURNAL_DIR, QUEST_ROOT, REDKIT_R4

CACHE = HERE / "quest_index.json"

SET_CLASSES = ("ChangingBlock", "FactSet", "SetFact", "CStorySceneActionFact")
TEST_CLASSES = ("Condition", "FlowCondition")


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
           "phases": [], "objectives": [], "descriptions": [], "pins": []}
    if quest is None:
        return out
    out["title_locid"] = locid(quest["index"])
    out["entry_guid"] = guid(quest["index"])

    def children(i, cls=None):
        return [e for e in p["exports"] if e["parentID"] == i and (cls is None or e["className"] == cls)]

    for e in p["exports"]:
        if e["className"] == "CJournalQuestPhase":
            phase = {"guid": guid(e["index"]), "objectives": []}
            for o in children(e["index"], "CJournalQuestObjective"):
                obj = {"guid": guid(o["index"]), "locid": locid(o["index"]), "pins": len(children(o["index"], "CJournalQuestMapPin"))}
                phase["objectives"].append(obj)
                out["objectives"].append(obj)
            out["phases"].append(phase)
    # description entries are not objectives, but the save records them and some quests move their
    # whole status onto one, so keep their GUIDs to recognise them
    out["descriptions"] = [
        {"guid": guid(e["index"]), "name": props.get(e["index"], {}).get("name", "")}
        for e in p["exports"] if e["className"] in ("CJournalQuestDescriptionEntry", "CJournalQuestDescriptionGroup")
    ]
    return out


def journal_index():
    """stem -> journal_struct for every .journal REDkit ships."""
    out = {}
    bad = []
    for jf in sorted(JOURNAL_DIR.glob("*.journal")):
        try:
            out[jf.stem.lower()] = journal_struct(jf)
        except Exception as ex:
            bad.append((jf.name, type(ex).__name__, str(ex)[:80]))
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
    """The folder holding a quest's scenes, from its phase file: <dir>/quest_files/<stem>."""
    cand = Path(phase_path).parent / "quest_files" / Path(phase_path).stem
    if cand.is_dir():
        return cand
    hits = list(Path(phase_path).parent.glob(f"quest_files/{Path(phase_path).stem}*"))
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
                elif c["className"] in ("CActivateSpawnset", "CActivateCommunity", "CActivateSpawnTree"):
                    on.add(ref)
    return sorted(off), sorted(on)


# --------------------------------------------------------------------------- scenes

def scene_choices(path, conn=None):
    """The dialogue choices of one scene: locId, the facts its section waits on, one-shot flag."""
    try:
        p = cr2w.parse(path)
    except Exception:
        return []
    ex = {e["index"]: e for e in p["exports"]}
    props = {}
    for e in p["exports"]:
        props[e["index"]] = {v["name"]: v["value"] for v in cr2w.props(p, e)}

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
            stack.extend(c["index"] for c in p["exports"] if c["parentID"] == i)
        return sorted(out)

    out = []
    for e in p["exports"]:
        if e["className"] != "CStorySceneChoiceLine":
            continue
        cl = props[e["index"]].get("choiceLine")
        locid = cl.get("locId") if isinstance(cl, dict) else None
        # the choice line sits under CStorySceneChoice under CStorySceneSection
        sec, i = None, e["parentID"]
        for _ in range(6):
            if not i or i not in ex:
                break
            if ex[i]["className"] == "CStorySceneSection":
                sec = i
                break
            i = ex[i]["parentID"]
        out.append({
            "locid": locid,
            "one_shot": bool(props[e["index"]].get("singleUseChoice")),
            "section_facts": facts_under(sec) if sec else [],
        })
    return out


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
    """The quests the tracker talks about: every step in route.json (plus the feed's quests)."""
    from paths import ROUTE
    route = json.loads(ROUTE.read_text(encoding="utf-8"))
    stems = set()
    for n in route.get("nodes", []):
        for f in n.get("files", []):
            for part in re.split(r"[|#]", f):
                if part:
                    stems.add(part.lower())
    feed = ROUTE.parent / "feed.json"
    if feed.exists():
        for item in json.loads(feed.read_text(encoding="utf-8")).get("items", []):
            q = (item.get("quest") or "").strip().lower()
            if q:
                stems.add(re.sub(r"[^a-z0-9]", "", q))
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
                                 "phases": j["phases"], "descriptions": j["descriptions"]}

    # Which REDkit journal files each phase file is about. The file names differ between the
    # bundles and REDkit, so a phase file is attributed to a quest when it names that quest's
    # journal resource - the same rule the graph walk uses.
    covered = defaultdict(list)
    deacts = defaultdict(list)
    aggregate = []
    for ph in sorted(QUEST_ROOT.rglob("*.w2phase")):
        try:
            b = ph.read_bytes()
        except OSError:
            continue
        stems = {m.group(1).decode().lower() for m in JOURNAL_MENTION.finditer(b)} & set(journals)
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
             "objectives": j.get("objectives", []), "phases": [], "scenes": [], "switches": deacts.get(stem, [])}
        for ph in sorted(set(covered.get(stem, []))):
            try:
                f = phase_facts(ph)
            except Exception:
                continue
            q["phases"].append({"file": rel(ph), "set": f["set"], "test": f["test"], "ref": f["ref"],
                                "global": is_global(rel(ph)) or rel(ph) in aggregate})
        folders = [quest_folder(ph) for ph in sorted(set(covered.get(stem, []))) if not is_global(rel(ph))]
        for folder in [f for f in folders if f]:
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
    for ph in sorted(QUEST_ROOT.rglob("*.w2phase")):
        try:
            b = ph.read_bytes()
        except OSError:
            continue
        # a quest name only counts when the file names that quest's own journal resource, so
        # 'mine' does not match every file that happens to contain the word
        here = sorted({m.group(1).decode().lower() for m in JOURNAL_MENTION.finditer(b)} & stems)
        if not here:
            continue
        try:
            g = questgraph.G(ph)
        except Exception:
            continue
        for stem in here:
            try:
                for blk in g.blocks_for(stem):
                    # `guids` is the journal path's GUID chain: it tells a block that adds the quest
                    # itself from one that adds an objective of it (see tools/prereqs.py)
                    idx["quests"][stem]["activators"].append(
                        {"file": rel(ph), "block": blk["index"], "class": blk["class"],
                         "resource": blk["resource"], "label": blk["label"],
                         "guids": [g.lower() for g in blk.get("guids", [])]})
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
        CACHE.write_text(json.dumps(idx, sort_keys=True, indent=1), encoding="utf-8")
        print(f"wrote {CACHE.name}: {len(idx['quests'])} quests, {len(idx['journals'])} journal files, "
              f"{len(idx['unreadable_journals'])} journals unreadable")
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
                        print(f"  {'[one-shot] ' if ch['one_shot'] else ''}{sc['file']}\n      {text!r}  facts={ch['section_facts']}")
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
