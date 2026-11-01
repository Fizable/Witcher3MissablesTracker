"""Stage `views`: the plain-text files an LLM (or a person) reads first.

Reads the finished tables of the other stages and writes, under common.OUT (the folder that holds w3db.sqlite):

  README.md               entry point: what this is, the table list, evidence strength, example queries, row counts
  INDEX.md                every quest, grouped by pack and type, with how many quests can fail it and how many it fails
  MISSABLE.md             quests that another quest can fail: the trigger, and the decisive fact or journal status
  quests/<stem>.md        one dossier per quest (quests/ is deleted and recreated on every run)
  quests.jsonl            the same dossiers as one JSON object per line
  facts.jsonl             one object per fact: who sets it and who tests it
  choices.jsonl           dialogue choices that lead to a quest effect
  CARDS.md, cards.jsonl   Gwent cards, only when the items tables exist

The connection may be read-only. The only table written is views_manifest; when that write fails
(read-only database, or the table is missing) the error is reported and the files are still written.
Files are UTF-8 with LF newlines.
"""
import json
import re
import shutil
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SCHEMA = """
CREATE TABLE IF NOT EXISTS views_manifest (path TEXT, kind TEXT, n INTEGER);
"""

# relation kinds that mean "this quest can be lost" (B is the quest that is lost): doing A loses B
CUT_KINDS = ("fails", "fail_when_fact", "fail_when_journal")
# B fails when A's condition is FALSE: skipping A loses B, doing A does not. Shown apart from CUT_KINDS.
UNLESS_KINDS = ("fail_unless_fact", "fail_unless_journal")
# an objective of B is marked failed by A; B itself goes on. Shown apart, never counted as a loss.
OBJECTIVE_KIND = "fails_objective"
# relation kinds that mean "this quest has an effect on another quest" (A is the actor)
LOSS_KINDS = CUT_KINDS + ("completes",)
# hops up to which a fail_when_fact link counts as strong evidence
STRONG_HOPS = 6

COMPARE = {"CF_Equal": "=", "CF_NotEqual": "!=", "CF_Greater": ">", "CF_GreaterEqual": ">=",
           "CF_Less": "<", "CF_LessEqual": "<=", "CF_Clamp": "clamp"}
PACK_TITLE = {"base": "Base game (base)", "ep1": "Hearts of Stone (ep1)", "bob": "Blood and Wine (bob)"}
TYPE_ORDER = ["Chapter", "Side", "MonsterHunt", "TreasureHunt"]

TABLE_NOTES = {
    "files": "every file read from the REDkit folder, with its pack (base, ep1, bob, dlcN) and whether it could be read",
    "meta": "build bookkeeping: when each stage last finished",
    "strings": "the game's English text by locId, with the owning resource and property; key is the STRING_KEY used by XML",
    "graph_nodes": "every node of every quest graph (.w2phase and .w2quest files); props_json holds its properties",
    "graph_sockets": "named input and output sockets of the graph nodes",
    "graph_edges": "wires between graph nodes: which block's output socket feeds which block's input socket",
    "graph_refs": "references from a graph node to another resource (phase, scene, community, and so on)",
    "graph_journal_refs": "journal entry references made by graph nodes, with the guid chain up to the quest",
    "journal_entries": "every entry of every journal file (quests, phases, objectives, description entries, map pins)",
    "journal_quests": "one row per journal file under journal/quests (category 'quest', 403 rows) plus other journal folders",
    "journal_objectives": "objectives of each quest, with their phase, order and whether they are mandatory",
    "scene_nodes": "every node of every dialogue scene (.w2scene)",
    "scene_links": "links between scene nodes: next, linked, choice, branch",
    "scene_lines": "spoken dialogue lines of scenes: speaker and locId",
    "scene_choices": "dialogue choice lines of scenes: locId, order, the facts the choice sets and the outputs it reaches",
    "scene_outputs": "named outputs of scenes",
    "scene_inputs": "named inputs of scenes",
    "items": "item definitions from the item XML files (only when the items stage ran)",
    "item_tags": "tags of each item",
    "loot_tables": "loot table definitions",
    "loot_entries": "what each loot table can drop: item name, quantity range, chance as written",
    "rewards": "reward definitions: experience, gold and the rest of the reward block",
    "reward_items": "items inside each reward",
    "gwent_cards": "Gwent card definitions: card index, title key, faction, power, type",
    "gwent_decks": "Gwent deck definitions, with the leader card index when it resolves",
    "gwent_deck_cards": "cards in each Gwent deck, with copy counts",
    "card_sources": "where each Gwent card is obtained, from the reviewed tools/card_sources.json",
    "saves": "one row per save file in the saves folder: playthrough, order, number of quests marked JS_Success",
    "playthroughs": "one row per playthrough (a chain of saves that continue each other)",
    "journal_transitions": "for each save and the save it continues: each journal guid whose status changed, from and to",
    "fact_transitions": "for each save and the save it continues: each fact whose value changed, from and to",
    "phase_tree": "which phase file includes which other phase file",
    "file_quest": "which quest each quest file belongs to, and how that was decided (journal blocks or parent file)",
    "journal_ops": "every journal block in a quest graph (activate, success, failure, track, ...) and the entry it touches",
    "journal_tests": "every condition in a quest graph that tests a journal entry's status",
    "fact_ops": "every fact a quest file sets, adds, removes or tests, and every fact a dialogue choice sets",
    "spawnset_ops": "every community (NPC group) a quest file switches off or on",
    "fail_triggers": "for each wired Failure input: the conditions upstream of it, with the number of graph hops",
    "choice_effects": "what each dialogue choice leads to in the quest graph: facts set, journal entries activated, succeeded, failed",
    "quest_relations": "quest to quest effects with evidence: fails, fail_when_fact, fail_when_journal, fail_unless_fact, fail_unless_journal, fails_objective, completes, starts_or_advances, fact_test, fact_forbid, journal_test, removes_community",
    "views_manifest": "every file the views stage wrote (path, kind, row count)",
    "sqlite_stat1": "SQLite planner statistics, written by PRAGMA optimize",
}

EXAMPLES = [
    ("What quests does a quest fail, and through which kind of link?",
     """SELECT r.kind, COALESCE(s.text, b.stem) AS quest, b.stem, r.n
FROM quest_relations r
JOIN journal_quests a ON a.guid = r.a_guid
JOIN journal_quests b ON b.guid = r.b_guid
LEFT JOIN strings s ON s.loc_id = b.title_loc_id
WHERE a.stem = 'q402ciri' AND r.kind IN ('fails', 'fail_when_fact', 'fail_when_journal')
ORDER BY r.kind, b.stem;"""),
    ("What fails a quest (the reverse direction)?",
     """SELECT r.kind, COALESCE(s.text, a.stem) AS failing_quest, a.stem, r.n
FROM quest_relations r
JOIN journal_quests a ON a.guid = r.a_guid
JOIN journal_quests b ON b.guid = r.b_guid
LEFT JOIN strings s ON s.loc_id = a.title_loc_id
WHERE b.stem = 'sq106killbill' AND r.kind IN ('fails', 'fail_when_fact', 'fail_when_journal')
ORDER BY r.kind, a.stem;"""),
    ("Which quests set a fact, and which quests test it?",
     """SELECT role, op, quest, file_id, COUNT(*) AS n
FROM (
    SELECT 'set' AS role, f.op, COALESCE(s.text, j.stem, '(no quest)') AS quest, f.file_id
    FROM fact_ops f
    LEFT JOIN journal_quests j ON j.guid = f.owner_quest
    LEFT JOIN strings s ON s.loc_id = j.title_loc_id
    WHERE f.fact = 'q109_keira_defeated' AND f.op IN ('set', 'add', 'remove')
    UNION ALL
    SELECT 'test', f.op, COALESCE(s.text, j.stem, '(no quest)'), f.file_id
    FROM fact_ops f
    LEFT JOIN journal_quests j ON j.guid = f.owner_quest
    LEFT JOIN strings s ON s.loc_id = j.title_loc_id
    WHERE f.fact = 'q109_keira_defeated' AND f.op IN ('test', 'forbid')
)
GROUP BY role, op, quest, file_id
ORDER BY role, quest;"""),
    ("What does a dialogue choice (by its English text) lead to?",
     """SELECT s.text AS choice, ce.scene, ce.output, ce.effect, ce.target, ce.value,
       COALESCE(j.stem, '') AS quest
FROM choice_effects ce
JOIN strings s ON s.loc_id = ce.choice_loc_id
LEFT JOIN journal_quests j ON j.guid = ce.quest_guid
WHERE s.text LIKE '%Show me what you%'
ORDER BY ce.hops, ce.effect
LIMIT 50;"""),
    ("Which statuses of a quest were seen in the saves?",
     """SELECT t.to_status, COUNT(*) AS transitions, MIN(sv.file) AS first_save, MAX(sv.file) AS last_save
FROM journal_transitions t
JOIN journal_quests j ON j.guid = t.guid
JOIN saves sv ON sv.save_id = t.to_save
WHERE j.stem = 'q402ciri'
GROUP BY t.to_status
ORDER BY t.to_status;"""),
    ("What are the objectives of a quest, in order?",
     """SELECT o.ord, COALESCE(s.text, o.base_name) AS objective, o.is_mandatory,
       (SELECT MIN(e.ord) FROM journal_entries e
        WHERE e.guid = o.phase_guid AND e.class = 'CJournalQuestPhase') AS phase_ord
FROM journal_objectives o
JOIN journal_quests j ON j.guid = o.quest_guid
LEFT JOIN strings s ON s.loc_id = o.title_loc_id
WHERE j.stem = 'q402ciri'
ORDER BY phase_ord, o.ord;"""),
    ("Which facts make a quest's Failure input fire?",
     """SELECT ft.hops, json_extract(ft.detail, '$.fact') AS fact,
       json_extract(ft.detail, '$.status') AS status,
       json_extract(ft.detail, '$.value') AS value, f.path
FROM fail_triggers ft
JOIN journal_quests j ON j.guid = ft.quest_guid
JOIN files f ON f.file_id = ft.file_id
WHERE j.stem = 'q402ciri'
ORDER BY ft.hops
LIMIT 50;"""),
    ("Which NPC groups (communities) does a quest switch off?",
     """SELECT s.op, s.community, f.path
FROM spawnset_ops s
JOIN journal_quests j ON j.guid = s.owner_quest
JOIN files f ON f.file_id = s.file_id
WHERE j.stem = 'q402ciri' AND s.op = 'off'
ORDER BY s.community;"""),
    ("Which quests can be failed by the most other quests?",
     """SELECT COALESCE(s.text, b.stem) AS quest, COUNT(DISTINCT r.a_guid) AS can_be_failed_by
FROM quest_relations r
JOIN journal_quests b ON b.guid = r.b_guid
LEFT JOIN strings s ON s.loc_id = b.title_loc_id
WHERE r.kind IN ('fails', 'fail_when_fact', 'fail_when_journal')
GROUP BY b.guid
ORDER BY can_be_failed_by DESC
LIMIT 10;"""),
    ("Which files does a quest own, and how was that decided?",
     """SELECT f.path, fq.how, fq.votes
FROM file_quest fq
JOIN journal_quests j ON j.guid = fq.quest_guid
JOIN files f ON f.file_id = fq.file_id
WHERE j.stem = 'q402ciri'
ORDER BY f.path;"""),
]


# ---------------------------------------------------------------- helpers

def _clean_paragraphs(raw):
    """Game text to plain paragraphs: <br> becomes a paragraph break, other tags are dropped."""
    if not raw:
        return []
    s = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    s = re.sub(r"<[^>]+>", "", s)
    return [" ".join(p.split()) for p in s.split("\n") if p.strip()]


def _safe(stem):
    return re.sub(r"[^a-z0-9_.-]", "_", stem.lower())


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _jsonl(path, rows):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _rel(out, p):
    return Path(p).relative_to(out).as_posix()


def _s(v):
    return "" if v is None else str(v)


# ---------------------------------------------------------------- loading

class Data:
    """Everything the views read, loaded once into dictionaries."""


def _load(con):
    q = con.execute
    d = Data()
    d.tables = {r[0] for r in q("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")}
    d.text = {loc: t for loc, t in q("SELECT loc_id, text FROM strings WHERE text IS NOT NULL AND text != ''")}
    d.key_text = {}
    for key, loc in q("SELECT key, loc_id FROM strings WHERE key IS NOT NULL ORDER BY loc_id"):
        if key not in d.key_text and loc in d.text:
            d.key_text[key] = d.text[loc]
    d.files = {fid: {"path": p, "kind": k, "pack": pk}
               for fid, p, k, pk in q("SELECT file_id, path, kind, pack FROM files")}
    d.quests = {}
    for guid, fid, stem, tloc, typ in q("SELECT guid, file_id, stem, title_loc_id, type FROM journal_quests "
                                        "WHERE category = 'quest'"):
        d.quests[guid] = {"guid": guid, "file_id": fid, "stem": stem, "title_loc": tloc, "type": typ}

    # journal entries: names, descriptions, phase order
    d.entries = {}
    d.desc_by_root = defaultdict(list)
    d.phase_ord = {}
    for guid, cls, root, base, ordv, tloc, dloc in q(
            "SELECT guid, class, root_guid, base_name, ord, title_loc_id, desc_loc_id FROM journal_entries "
            "WHERE guid IS NOT NULL"):
        if guid not in d.entries:
            d.entries[guid] = {"class": cls, "base_name": base, "title_loc": tloc}
        if cls == "CJournalQuestDescriptionEntry" and root:
            d.desc_by_root[root].append((ordv if ordv is not None else 0, dloc, tloc))
        if cls == "CJournalQuestPhase" and guid not in d.phase_ord:
            d.phase_ord[guid] = ordv if ordv is not None else 0

    d.objectives = defaultdict(list)
    for qg, pg, base, tloc, ordv, mand, counter in q(
            "SELECT quest_guid, phase_guid, base_name, title_loc_id, ord, is_mandatory, counter "
            "FROM journal_objectives"):
        d.objectives[qg].append({"phase": pg, "base": base, "title_loc": tloc, "ord": ordv,
                                 "mandatory": mand, "counter": counter})

    d.files_by_quest = defaultdict(list)
    d.quest_of_file = {}
    for fid, qg, how, votes in q("SELECT file_id, quest_guid, how, votes FROM file_quest"):
        d.files_by_quest[qg].append((fid, how, votes))
        d.quest_of_file[fid] = qg

    d.rels_out = defaultdict(list)
    d.rels_in = defaultdict(list)
    for a, b, kind, n, evj in q("SELECT a_guid, b_guid, kind, n, evidence FROM quest_relations"):
        rec = {"a": a, "b": b, "kind": kind, "n": n, "ev": json.loads(evj or "[]")}
        d.rels_out[a].append(rec)
        d.rels_in[b].append(rec)

    d.facts_by_owner = defaultdict(list)     # owner quest -> set/add/remove rows
    d.tests_by_owner = defaultdict(list)     # owner quest -> test/forbid rows
    d.writers_by_fact = defaultdict(list)    # fact -> set/add rows (any owner)
    d.testers_by_fact = defaultdict(list)    # fact -> test/forbid rows (any owner)
    d.fact_rows = defaultdict(list)          # fact -> every row
    for fact, op, val, cmp_, fid, owner, source, loc in q(
            "SELECT fact, op, value, compare, file_id, owner_quest, source, choice_loc_id FROM fact_ops "
            "WHERE fact IS NOT NULL"):
        row = {"fact": fact, "op": op, "value": val, "compare": cmp_, "file_id": fid, "owner": owner,
               "source": source, "loc": loc}
        d.fact_rows[fact].append(row)
        if op in ("set", "add", "remove"):
            if owner:
                d.facts_by_owner[owner].append(row)
            if op in ("set", "add"):
                d.writers_by_fact[fact].append(row)
        elif op in ("test", "forbid"):
            if owner:
                d.tests_by_owner[owner].append(row)
            d.testers_by_fact[fact].append(row)

    d.scenes_by_file = defaultdict(set)
    for fid, ref in q("SELECT file_id, ref_path FROM graph_refs WHERE prop = 'scene'"):
        d.scenes_by_file[fid].add(ref)

    d.choices_by_scene = defaultdict(list)
    if "scene_choices" in d.tables:
        for path, loc, ordv, outs in q("SELECT f.path, c.loc_id, c.ord, c.leads_to_outputs FROM scene_choices c "
                                       "JOIN files f ON f.file_id = c.file_id"):
            d.choices_by_scene[path].append({"loc": loc, "ord": ordv or 0, "outputs": json.loads(outs or "[]")})
        for lst in d.choices_by_scene.values():
            lst.sort(key=lambda c: c["ord"])

    d.effects_by_choice = defaultdict(list)  # (scene, loc) -> effect rows
    d.effects_by_choice_output = defaultdict(list)
    if "choice_effects" in d.tables:
        for scene, loc, out, eff, target, val, qg, hops in q(
                "SELECT scene, choice_loc_id, output, effect, target, value, quest_guid, hops FROM choice_effects"):
            row = {"scene": scene, "loc": loc, "output": out, "effect": eff, "target": target,
                   "value": val, "quest": qg, "hops": hops}
            d.effects_by_choice[(scene, loc)].append(row)
            d.effects_by_choice_output[(scene, loc, out)].append(row)

    d.transitions = defaultdict(lambda: {"status": Counter(), "failed_files": set()})
    for guid, to_status, sfile in q("SELECT t.guid, t.to_status, s.file FROM journal_transitions t "
                                    "LEFT JOIN saves s ON s.save_id = t.to_save"):
        rec = d.transitions[guid]
        rec["status"][to_status] += 1
        if to_status == "JS_Failed" and sfile:
            rec["failed_files"].add(sfile)

    d.reward_names = defaultdict(list)  # file_id -> reward names referenced by CQuestRewardBlock
    d.gwent_decks = defaultdict(list)   # file_id -> (deck, difficulty) of CGwintMinigame
    for fid, cls, props in q("SELECT file_id, class, props_json FROM graph_nodes "
                             "WHERE class IN ('CQuestRewardBlock', 'CGwintMinigame')"):
        try:
            ps = json.loads(props or "{}")
        except ValueError:
            ps = {}
        if cls == "CQuestRewardBlock" and ps.get("rewardName"):
            d.reward_names[fid].append(ps["rewardName"])
        elif cls == "CGwintMinigame" and ps.get("deckName"):
            d.gwent_decks[fid].append((ps["deckName"], ps.get("difficulty")))

    d.has_rewards = {"rewards", "reward_items"} <= d.tables
    d.rewards = {}
    d.reward_items = defaultdict(list)
    if d.has_rewards:
        for name, exp, gold in q("SELECT name, experience, gold FROM rewards"):
            d.rewards.setdefault(name, {"experience": exp, "gold": gold})
        for rname, iname, amount in q("SELECT reward_name, item_name, amount FROM reward_items"):
            d.reward_items[rname].append((iname, amount))
    return d


# ---------------------------------------------------------------- naming

def _title(d, g):
    qd = d.quests.get(g)
    if qd:
        return d.text.get(qd["title_loc"]) or qd["stem"]
    e = d.entries.get(g)
    if e:
        return d.text.get(e["title_loc"]) or e["base_name"] or g[:8]
    return (g or "?")[:8]


def _stem(d, g):
    qd = d.quests.get(g)
    return qd["stem"] if qd else (g or "?")[:8]


def _entry_name(d, g):
    e = d.entries.get(g)
    if not e:
        return (g or "?")[:8]
    return d.text.get(e["title_loc"]) or e["base_name"] or (g or "?")[:8]


def _path(d, fid):
    f = d.files.get(fid)
    return f["path"] if f else f"file {fid}"


def _cmp(c):
    return COMPARE.get(c, c or "=")


def _val(v):
    return "(no value recorded)" if v is None else str(v)


def _ev_text(d, kind, ev):
    """One human line for one piece of relation evidence."""
    if kind == "fails":
        return (f"Failure input wired at block {ev.get('block')} of {_path(d, ev.get('file'))}, "
                f"for entry '{_entry_name(d, ev.get('entry'))}' ({ev.get('entry_class')})")
    if kind == "fail_when_journal":
        return (f"fires when entry '{_entry_name(d, ev.get('entry'))}' is {ev.get('status')} "
                f"(block {ev.get('fail_block')}, {ev.get('hops')} hop(s), {_path(d, ev.get('file'))})")
    if kind == "fail_when_fact":
        return (f"fires when fact `{ev.get('fact')}` {_cmp(ev.get('compare'))} {_val(ev.get('value'))} "
                f"(block {ev.get('fail_block')}, {ev.get('hops')} hop(s), {_path(d, ev.get('file'))})")
    if kind == "fail_unless_journal":
        return (f"fails unless entry '{_entry_name(d, ev.get('entry'))}' is {ev.get('status')} "
                f"(block {ev.get('fail_block')}, {ev.get('hops')} hop(s), {_path(d, ev.get('file'))})")
    if kind == "fail_unless_fact":
        return (f"fails unless fact `{ev.get('fact')}` {_cmp(ev.get('compare'))} {_val(ev.get('value'))} "
                f"(block {ev.get('fail_block')}, {ev.get('hops')} hop(s), {_path(d, ev.get('file'))})")
    if kind == OBJECTIVE_KIND:
        return (f"marks objective '{_entry_name(d, ev.get('entry'))}' failed at block {ev.get('block')} of "
                f"{_path(d, ev.get('file'))} (the quest goes on)")
    if kind == "completes":
        return (f"completes entry '{_entry_name(d, ev.get('entry'))}' ({ev.get('entry_class')}) at block "
                f"{ev.get('block')} of {_path(d, ev.get('file'))}")
    if kind == "starts_or_advances":
        return (f"activates entry '{_entry_name(d, ev.get('entry'))}' ({ev.get('entry_class')}) at block "
                f"{ev.get('block')} of {_path(d, ev.get('file'))}")
    if kind in ("fact_test", "fact_forbid"):
        return f"tests fact `{ev.get('fact')}`"
    if kind == "journal_test":
        return (f"tests that entry '{_entry_name(d, ev.get('entry'))}' is {ev.get('status')} "
                f"(node {ev.get('node')}, {_path(d, ev.get('file'))})")
    if kind == "removes_community":
        comm = _s(ev.get("community")).rsplit("/", 1)[-1]
        return f"switches off community {comm} (node {ev.get('node')}, {_path(d, ev.get('file'))})"
    return json.dumps(ev, ensure_ascii=False)


def _ev_json(d, kind, ev):
    out = {"text": _ev_text(d, kind, ev)}
    for k, v in ev.items():
        if k == "file":
            out["file_path"] = _path(d, v)
        elif k == "entry":
            out["entry_name"] = _entry_name(d, v)
            out["entry"] = v
        else:
            out[k] = v
    return out


def _is_strong(recs):
    for r in recs:
        if r["kind"] in ("fails", "fail_when_journal"):
            return True
        if r["kind"] == "fail_when_fact" and any((e.get("hops") or 99) <= STRONG_HOPS for e in r["ev"]):
            return True
    return False


def _min_hops(recs):
    hops = [e.get("hops") for r in recs for e in r["ev"] if e.get("hops") is not None]
    return min(hops) if hops else 99


# ---------------------------------------------------------------- per-quest record

def _record(d, g):
    qd = d.quests[g]
    stem = qd["stem"]
    jfid = qd["file_id"]
    rec = {"stem": stem, "guid": g, "title": _title(d, g), "pack": d.files.get(jfid, {}).get("pack"),
           "type": qd["type"], "journal_file": _path(d, jfid)}

    # description: the quest's description entries, in order, at most three paragraphs
    paras = []
    for _ordv, dloc, tloc in sorted(d.desc_by_root.get(g, []), key=lambda t: t[0]):
        text = d.text.get(dloc) or d.text.get(tloc)
        for p in _clean_paragraphs(text):
            if len(paras) < 3:
                paras.append(p)
    rec["description"] = paras

    # objectives: phase order, then the objective's own order
    objs = []
    for o in sorted(d.objectives.get(g, []),
                    key=lambda o: (d.phase_ord.get(o["phase"], 1 << 40), o["ord"] if o["ord"] is not None else 1 << 40)):
        objs.append({"text": d.text.get(o["title_loc"]) or o["base"] or "(no text)",
                     "optional": o["mandatory"] == 0, "counter": o["counter"]})
    rec["objectives"] = objs

    rec["phase_files"] = [{"path": _path(d, fid), "how": how, "votes": votes}
                          for fid, how, votes in sorted(d.files_by_quest.get(g, []), key=lambda t: _path(d, t[0]))]

    # starts: who activates this quest's entries
    starts = []
    for r in sorted(d.rels_in.get(g, []), key=lambda r: _title(d, r["a"]).lower()):
        if r["kind"] == "starts_or_advances":
            starts.append({"quest": _stem(d, r["a"]), "title": _title(d, r["a"]), "n": r["n"],
                           "examples": [_ev_text(d, r["kind"], e) for e in r["ev"][:3]]})
    rec["starts"] = starts

    # start conditions: facts this quest tests in its own files, grouped by the other quests that set them
    tested = {row["fact"] for row in d.tests_by_owner.get(g, [])}
    by_writer = defaultdict(set)
    for fact in tested:
        for w in d.writers_by_fact.get(fact, []):
            if w["owner"] and w["owner"] != g:
                by_writer[w["owner"]].add(fact)
    rec["start_conditions"] = [
        {"quest": _stem(d, w), "title": _title(d, w), "facts": sorted(facts)}
        for w, facts in sorted(by_writer.items(), key=lambda kv: _title(d, kv[0]).lower())]

    # cutoffs: quests that can lose this one, and the quests this one can lose
    def link_rows(rels, other_key, kinds):
        out = []
        for r in sorted(rels, key=lambda r: (_title(d, r[other_key]).lower(), r["kind"])):
            if r["kind"] in kinds:
                out.append({"quest": _stem(d, r[other_key]), "title": _title(d, r[other_key]), "kind": r["kind"],
                            "n": r["n"], "evidence": [_ev_json(d, r["kind"], e) for e in r["ev"][:8]]})
        return out
    rec["can_be_lost"] = link_rows(d.rels_in.get(g, []), "a", CUT_KINDS)
    rec["fails_unless"] = link_rows(d.rels_in.get(g, []), "a", UNLESS_KINDS)
    rec["loses"] = link_rows(d.rels_out.get(g, []), "b", LOSS_KINDS)
    # objectives: this quest's objectives that other quests mark failed (this quest goes on), and the reverse
    rec["objectives_failed_by_others"] = link_rows(d.rels_in.get(g, []), "a", (OBJECTIVE_KIND,))
    rec["objectives_failed_by_this"] = link_rows(d.rels_out.get(g, []), "b", (OBJECTIVE_KIND,))

    # NPC removals (weak evidence). removes_community: a = the quest that switches the community off,
    # b = a quest whose files reference it. Community names only, no paths.
    def communities(rels, other_key):
        seen, out = set(), []
        for r in rels:
            other = r[other_key]
            for e in r["ev"]:
                name = _s(e.get("community")).rsplit("/", 1)[-1].replace(".w2comm", "")
                if name and (name, other) not in seen:
                    seen.add((name, other))
                    out.append({"community": name, "other": _stem(d, other), "other_title": _title(d, other)})
        return sorted(out, key=lambda x: (x["community"], x["other"]))[:15]
    rec["npc_removed_by_this"] = communities(
        [r for r in d.rels_out.get(g, []) if r["kind"] == "removes_community"], "b")
    rec["npc_removed_elsewhere"] = communities(
        [r for r in d.rels_in.get(g, []) if r["kind"] == "removes_community"], "a")

    # dialogue choices played by this quest's phase files
    scenes = set()
    for fid, _how, _votes in d.files_by_quest.get(g, []):
        scenes |= d.scenes_by_file.get(fid, set())
    choices, seen = [], set()
    for scene in sorted(scenes):
        for c in d.choices_by_scene.get(scene, []):
            key = (scene, c["loc"])
            if key in seen:
                continue
            seen.add(key)
            effects = d.effects_by_choice.get(key, [])
            lines = []
            for e in effects:
                lines.append(_effect_text(d, e))
            lines = list(dict.fromkeys(lines))
            choices.append({"text": d.text.get(c["loc"]), "loc_id": c["loc"], "scene": scene,
                            "outputs": c["outputs"], "effects": lines,
                            "quests": sorted({_title(d, e["quest"]) for e in effects if e["quest"]})})
    choices.sort(key=lambda c: (0 if c["effects"] else 1, c["scene"], c["loc_id"] or 0))
    rec["dialogue_choices"] = choices[:60]
    rec["dialogue_choices_total"] = len(choices)

    # facts this quest sets, and which other quests test them
    facts = defaultdict(lambda: {"ops": set(), "testers": set()})
    for row in d.facts_by_owner.get(g, []):
        facts[row["fact"]]["ops"].add(row["op"])
    rec_facts = []
    for fact in sorted(facts)[:40]:
        testers = sorted({_title(d, t["owner"]) for t in d.testers_by_fact.get(fact, [])
                          if t["owner"] and t["owner"] != g})
        rec_facts.append({"fact": fact, "ops": sorted(facts[fact]["ops"]), "tested_by": testers[:12],
                          "tested_by_count": len(testers)})
    rec["facts_set"] = rec_facts
    rec["facts_set_total"] = len(facts)

    # rewards and Gwent decks in this quest's files
    my_files = [fid for fid, _h, _v in d.files_by_quest.get(g, [])]
    rewards = []
    for fid in my_files:
        for name in sorted(set(d.reward_names.get(fid, []))):
            row = d.rewards.get(name) if d.has_rewards else None
            items = [f"{iname} x{amount}" for iname, amount in d.reward_items.get(name, [])] if d.has_rewards else []
            rewards.append({"name": name, "experience": row["experience"] if row else None,
                            "gold": row["gold"] if row else None, "items": items,
                            "in_file": _path(d, fid)})
    rec["rewards"] = rewards
    gwent = []
    for fid in my_files:
        for deck, diff in d.gwent_decks.get(fid, []):
            gwent.append({"deck": deck, "difficulty": diff, "in_file": _path(d, fid)})
    rec["gwent_decks"] = gwent

    # saves
    tr = d.transitions.get(g)
    if tr:
        rec["saves"] = {"transitions_by_status": dict(sorted(tr["status"].items())),
                        "failed_in_save_files": sorted(tr["failed_files"])[:10]}
    else:
        rec["saves"] = None
    return rec


def _effect_text(d, e):
    eff = e["effect"] or ""
    who = f" (quest {_title(d, e['quest'])})" if e["quest"] else ""
    if eff.startswith("fact_"):
        val = f" = {e['value']}" if e["value"] is not None else ""
        return f"{eff[5:]} fact `{e['target']}`{val}{who}"
    return f"{eff.replace('_', ' ')}: entry '{_entry_name(d, e['target'])}'{who}"


# ---------------------------------------------------------------- markdown renderers

def _dossier_md(rec):
    L = [f"# {rec['title']}", "",
         f"- Stem: `{rec['stem']}`",
         f"- GUID: `{rec['guid']}`",
         f"- Pack: {rec['pack'] or 'unknown'}",
         f"- Type: {rec['type'] or 'none recorded'}",
         f"- Journal file: `{rec['journal_file']}`", ""]

    if rec["description"]:
        L += ["## Description", ""]
        for p in rec["description"]:
            L += [p, ""]

    if rec["objectives"]:
        L += ["## Objectives", ""]
        for o in rec["objectives"]:
            tag = " (optional)" if o["optional"] else ""
            L.append(f"- {o['text']}{tag}")
        L.append("")

    if rec["phase_files"]:
        L += ["## Phase files", ""]
        for f in rec["phase_files"]:
            L.append(f"- `{f['path']}` ({f['how']}, {f['votes']} journal block(s))")
        L.append("")

    if rec["starts"] or rec["start_conditions"]:
        L += ["## Starts", ""]
        if rec["starts"]:
            for s in rec["starts"]:
                L.append(f"- Activated by **{s['title']}** (`{s['quest']}`), {s['n']} link(s):")
                for ex in s["examples"]:
                    L.append(f"  - {ex}")
        else:
            L.append("No other quest activates an entry of this one in the game files.")
        if rec["start_conditions"]:
            L += ["", "Conditions: facts this quest's own files test, set by other quests:"]
            for w in rec["start_conditions"]:
                L.append(f"- **{w['title']}** (`{w['quest']}`) sets: {', '.join(f'`{x}`' for x in w['facts'][:12])}"
                         + (f", +{len(w['facts']) - 12} more" if len(w["facts"]) > 12 else ""))
        L.append("")

    def link_block(rows, empty_text=None):
        for c in rows:
            L.append(f"- **{c['title']}** (`{c['quest']}`) [{c['kind']}], {c['n']} link(s):")
            for e in c["evidence"]:
                L.append(f"  - {e['text']}")
            if c["n"] > len(c["evidence"]):
                L.append(f"  - (first {len(c['evidence'])} of {c['n']} recorded)")
        if not rows and empty_text:
            L.append(empty_text)

    L += ["## Can be lost (cutoffs)", ""]
    link_block(rec["can_be_lost"], "none found in the game files")
    if rec["fails_unless"]:
        L += ["", "Also fails unless a condition holds (skipping that quest loses this one; doing it does not):", ""]
        link_block(rec["fails_unless"])
    L.append("")

    L += ["## Loses (this quest's effect on others)", ""]
    link_block(rec["loses"], "none found in the game files")
    L.append("")

    if rec["objectives_failed_by_others"] or rec["objectives_failed_by_this"]:
        L += ["## Objectives failed (the quest goes on)", ""]
        for c in rec["objectives_failed_by_others"]:
            L.append(f"- Failed by **{c['title']}** (`{c['quest']}`):")
            for e in c["evidence"]:
                L.append(f"  - {e['text']}")
        for c in rec["objectives_failed_by_this"]:
            L.append(f"- This quest fails an objective of **{c['title']}** (`{c['quest']}`):")
            for e in c["evidence"]:
                L.append(f"  - {e['text']}")
        L.append("")

    L += ["## NPC removals (weak evidence)", "",
          "Removing an NPC's community does not by itself fail a quest.", ""]
    if rec["npc_removed_by_this"] or rec["npc_removed_elsewhere"]:
        if rec["npc_removed_by_this"]:
            L.append("Communities this quest switches off (max 15):")
            for c in rec["npc_removed_by_this"]:
                L.append(f"- {c['community']} (referenced by {c['other_title']}, `{c['other']}`)")
        if rec["npc_removed_elsewhere"]:
            L.append("Communities other quests switch off that this quest's files reference (max 15):")
            for c in rec["npc_removed_elsewhere"]:
                L.append(f"- {c['community']} (switched off by {c['other_title']}, `{c['other']}`)")
    else:
        L.append("none found in the game files")
    L.append("")

    if rec["dialogue_choices"]:
        L += ["## Dialogue choices", ""]
        if rec["dialogue_choices_total"] > len(rec["dialogue_choices"]):
            L.append(f"Showing {len(rec['dialogue_choices'])} of {rec['dialogue_choices_total']} choices "
                     "(those with effects first).")
            L.append("")
        for c in rec["dialogue_choices"]:
            if c["text"]:
                text = f"\"{c['text']}\""
            elif c["loc_id"] is None:
                text = "(no text recorded)"
            else:
                text = f"(no English text, locId {c['loc_id']})"
            L.append(f"- {text} ({c['scene'].rsplit('/', 1)[-1]})")
            if c["effects"]:
                for e in c["effects"][:8]:
                    L.append(f"  - {e}")
                if len(c["effects"]) > 8:
                    L.append(f"  - (+{len(c['effects']) - 8} more)")
            else:
                L.append("  - no quest effect recorded")
        L.append("")

    if rec["facts_set"]:
        L += ["## Facts", "", f"Facts this quest sets ({rec['facts_set_total']} total, first 40):", ""]
        for f in rec["facts_set"]:
            tests = ", ".join(f["tested_by"][:6]) if f["tested_by"] else "no other quest tests it"
            more = f" (+{f['tested_by_count'] - 6} more)" if f["tested_by_count"] > 6 else ""
            L.append(f"- `{f['fact']}` ({'/'.join(f['ops'])}); tested by: {tests}{more}")
        L.append("")

    if rec["rewards"] or rec["gwent_decks"]:
        L += ["## Rewards and Gwent", ""]
        for r in rec["rewards"]:
            extra = []
            if r["experience"] is not None:
                extra.append(f"{r['experience']} XP")
            if r["gold"] is not None:
                extra.append(f"{r['gold']} gold")
            if r["items"]:
                extra.append("items: " + ", ".join(r["items"]))
            L.append(f"- Reward `{r['name']}`" + (f": {'; '.join(extra)}" if extra else ""))
        for g_ in rec["gwent_decks"]:
            L.append(f"- Gwent deck `{g_['deck']}`" + (f" ({g_['difficulty']})" if g_["difficulty"] else ""))
        L.append("")

    if rec["saves"]:
        L += ["## Seen in your saves", ""]
        for status, n in rec["saves"]["transitions_by_status"].items():
            L.append(f"- {status}: {n} transition(s)")
        if rec["saves"]["failed_in_save_files"]:
            L.append("- JS_Failed first seen in: " + ", ".join(f"`{x}`" for x in rec["saves"]["failed_in_save_files"]))
        L.append("")
    return "\n".join(L) + "\n"


def _index_md(d, recs):
    L = ["# Quest index", "",
         "Every quest (journal category 'quest'), grouped by pack, then by type, sorted by title.",
         "'can be failed by N quests' counts the quests whose Failure input can fire this quest; "
         "'fails M quests' counts the quests this one can fail. See README.md for what the kinds mean.", ""]
    groups = defaultdict(list)
    for g, rec in recs.items():
        groups[rec["pack"] or "unknown"].append(g)
    packs = sorted(groups, key=lambda p: (["base", "ep1", "bob"].index(p) if p in ("base", "ep1", "bob") else 9, p))
    for pk in packs:
        L += [f"## {PACK_TITLE.get(pk, 'Other pack: ' + pk)}", ""]
        bytype = defaultdict(list)
        for g in groups[pk]:
            bytype[recs[g]["type"] or "untyped"].append(g)
        types = sorted(bytype, key=lambda t: (TYPE_ORDER.index(t) if t in TYPE_ORDER else 9, t))
        for t in types:
            L += [f"### {t}", ""]
            for g in sorted(bytype[t], key=lambda g: recs[g]["title"].lower()):
                rec = recs[g]
                lost_by = len({r["a"] for r in d.rels_in.get(g, []) if r["kind"] in CUT_KINDS})
                fails = len({r["b"] for r in d.rels_out.get(g, []) if r["kind"] in CUT_KINDS})
                L.append(f"- [{rec['title']}](quests/{_safe(rec['stem'])}.md) - {t}; "
                         f"can be failed by {lost_by} quests; fails {fails} quests")
            L.append("")
    return "\n".join(L) + "\n"


def _missable_md(d, recs):
    L = ["# Quests that other quests can fail", "",
         "For each quest B that another quest A can fail, A is listed under B with the kind of link and "
         "the decisive fact or journal status. Strong evidence first: `fails`, `fail_when_journal`, and "
         f"`fail_when_fact` within {STRONG_HOPS} graph hops. Weaker `fail_when_fact` links follow under "
         "'weaker evidence'. Read README.md, 'How to read evidence strength', before relying on an entry.", ""]
    strong_by_a = defaultdict(list)
    for B in sorted(recs, key=lambda g: recs[g]["title"].lower()):
        by_a = defaultdict(list)
        for r in d.rels_in.get(B, []):
            if r["kind"] in CUT_KINDS:
                by_a[r["a"]].append(r)
        if not by_a:
            continue
        strong, weak = [], []
        for A in sorted(by_a, key=lambda a: _title(d, a).lower()):
            recs_a = by_a[A]
            (strong if _is_strong(recs_a) else weak).append((A, recs_a))
        L += [f"## {recs[B]['title']} (`{recs[B]['stem']}`)", ""]
        for A, recs_a in strong:
            L.append(_missable_line(d, A, recs_a, weak=False))
            strong_by_a[A].append(B)
        if weak:
            L += ["", "### weaker evidence", ""]
            for A, recs_a in weak:
                L.append(_missable_line(d, A, recs_a, weak=True))
        L.append("")
    L += ["## Doing a quest loses these (strong evidence)", ""]
    for A in sorted(strong_by_a, key=lambda a: _title(d, a).lower()):
        names = ", ".join(sorted((recs[b]["title"] for b in set(strong_by_a[A])), key=str.lower))
        L.append(f"- Doing **{_title(d, A)}** (`{_stem(d, A)}`) loses: {names}")
    L.append("")
    return "\n".join(L) + "\n"


def _missable_line(d, A, recs_a, weak):
    kinds = sorted({r["kind"] for r in recs_a})
    lines, weak_only = [], []
    for r in recs_a:
        for e in sorted(r["ev"], key=lambda e: e.get("hops") or 0):
            text = _ev_text(d, r["kind"], e)
            if r["kind"] == "fail_when_fact" and (e.get("hops") or 99) > STRONG_HOPS:
                weak_only.append(text)
            else:
                lines.append(text)
    # a strong pair shows its strong evidence; a weak pair (no strong line) shows its weak lines
    lines = list(dict.fromkeys(lines if lines else weak_only))
    shown = "; ".join(lines[:3]) + (f"; +{len(lines) - 3} more" if len(lines) > 3 else "")
    return f"- **{_title(d, A)}** (`{_stem(d, A)}`) [{', '.join(kinds)}]: {shown}"


# ---------------------------------------------------------------- facts and choices

def _facts_rows(d):
    out = []
    for fact in sorted(d.fact_rows):
        rows = d.fact_rows[fact]
        sets, tests = {}, {}
        for r in rows:
            if r["op"] in ("set", "add", "remove"):
                key = (r["owner"], r["file_id"], r["op"], r["value"], r["source"])
                sets.setdefault(key, r)
            elif r["op"] in ("test", "forbid"):
                key = (r["owner"], r["file_id"], r["op"], r["compare"], r["value"])
                tests.setdefault(key, r)
        set_by = [{"quest": _stem(d, r["owner"]) if r["owner"] else None,
                   "title": _title(d, r["owner"]) if r["owner"] else None,
                   "file": _path(d, r["file_id"]) if r["file_id"] is not None else None,
                   "op": r["op"], "value": r["value"], "source": r["source"]} for r in sets.values()]
        tested_by = [{"quest": _stem(d, r["owner"]) if r["owner"] else None,
                      "title": _title(d, r["owner"]) if r["owner"] else None,
                      "file": _path(d, r["file_id"]) if r["file_id"] is not None else None,
                      "op": r["op"], "compare": _cmp(r["compare"]) if r["compare"] else None,
                      "value": r["value"]} for r in tests.values()]
        out.append({"fact": fact, "set_count": len(set_by), "tested_count": len(tested_by),
                    "set_by": set_by[:50], "tested_by": tested_by[:50]})
    return out


def _choices_rows(d):
    out = []
    for (scene, loc, output) in sorted(d.effects_by_choice_output, key=lambda k: (k[0], k[1] or 0, k[2] or "")):
        effs = d.effects_by_choice_output[(scene, loc, output)]
        effects = []
        for e in effs:
            effects.append({"effect": e["effect"], "target": e["target"],
                            "target_name": _entry_name(d, e["target"]) if e["effect"].startswith("journal_")
                            else e["target"],
                            "value": e["value"], "quest": _stem(d, e["quest"]) if e["quest"] else None,
                            "quest_title": _title(d, e["quest"]) if e["quest"] else None,
                            "hops": e["hops"]})
        out.append({"text": d.text.get(loc), "loc_id": loc, "scene": scene, "output": output,
                    "effects": effects,
                    "quests": sorted({e["quest_title"] for e in effects if e["quest_title"]})})
    return out


# ---------------------------------------------------------------- cards (only when the items stage ran)

def _cards(con, d):
    q = con.execute
    items = {}
    for name, loc_name_key, category in q("SELECT name, loc_name_key, category FROM items WHERE name IS NOT NULL"):
        items.setdefault(name.lower(), {"name": name, "loc_name_key": loc_name_key, "category": category})
    loot = defaultdict(list)
    if "loot_entries" in d.tables:
        for loot_name, item_name, qmin, qmax, chance in q(
                "SELECT loot_name, item_name, quantity_min, quantity_max, chance FROM loot_entries "
                "WHERE item_name IS NOT NULL"):
            loot[item_name.lower()].append({"loot_table": loot_name, "item": item_name, "quantity_min": qmin,
                                            "quantity_max": qmax, "chance": chance})
    rew = defaultdict(list)
    if "reward_items" in d.tables:
        for rname, iname, amount in q("SELECT reward_name, item_name, amount FROM reward_items "
                                      "WHERE item_name IS NOT NULL"):
            rew[iname.lower()].append({"reward": rname, "item": iname, "amount": amount})
    sources = defaultdict(list)
    for card, kind, detail in q("SELECT card, kind, detail_json FROM card_sources"):
        sources[(card or "").lower()].append({"kind": kind, "detail": (detail or "")[:300]})

    rows = list(q("SELECT card_index, file_id, title_key, desc_key, faction, power, card_type, picture, attrs_json "
                  "FROM gwent_cards ORDER BY card_index, file_id"))
    names = Counter()
    parsed = []
    for row in rows:
        try:
            a = json.loads(row[8] or "{}")
        except ValueError:
            a = {}
        name = a.get("name") if isinstance(a, dict) else None
        names[name] += 1
        parsed.append((row, name))

    cards = []
    for (idx, fid, title_key, desc_key, faction, power, ctype, picture, attrs), name in parsed:
        lname = (name or "").lower()
        try:
            a = json.loads(attrs or "{}")
        except ValueError:
            a = {}
        item_attr = str((a.get("item") if isinstance(a, dict) else None) or "").strip().lower()
        candidates = [c for c in dict.fromkeys([item_attr, lname, f"gwint_card_{lname}" if lname else ""]) if c]
        item_names = [c for c in candidates if c in items]
        if item_attr and item_attr in items:
            link = "item attribute"
        elif item_names:
            link = "name"
        else:
            link = None
        src_keys = [k for k in (f"card_{lname}", lname) if k and k in sources]
        src = []
        for k in src_keys:
            src.extend(sources[k])
        lt, rw = [], []
        for c in candidates:
            lt.extend(loot.get(c, []))
            rw.extend(rew.get(c, []))
        cards.append({
            "card_index": idx, "name": name, "english_name": d.key_text.get(title_key),
            "title_key": title_key, "desc_key": desc_key, "faction": faction, "power": power,
            "card_type": ctype, "picture": picture, "file": _path(d, fid),
            "definitions_with_this_name": names[name] if name else 1,
            "item_match": [items[c]["name"] for c in item_names],
            "link": link,
            "match_note": {"item attribute": "linked by the card's item attribute",
                           "name": "no item attribute; linked by the card's name"}.get(
                link, "no item with this card's name or item attribute; sources and loot use the name only"
                if name else "card has no name attribute, cannot be linked"),
            "sources": src, "loot": lt, "reward_items": rw,
        })
    return cards


def _cards_md(cards):
    dup = sum(1 for c in cards if c["definitions_with_this_name"] > 1)
    L = ["# Gwent cards", "",
         "Each card's English name comes from its title key (strings.key). The card's item is its `item` "
         "attribute when that names a built item (the game files set it on a minority of cards); otherwise the "
         "item is found by the card's script name (`<name>` or `gwint_card_<name>`). card_sources keys are "
         "`card_<name>`. Loot and reward rows are joined on the same names. A card with no match says so in the "
         "Link column.", "",
         f"One row per card definition in the game files. {dup} rows share their name with another definition "
         "(the same card is often defined in both gameplay/items and gameplay/items_plus); the File column tells "
         "them apart.", "",
         "| # | Card | Name | Faction | Power | Sources | Loot entries | Reward items | Link | File |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for c in cards:
        nm = c["english_name"] or c["name"] or f"card {c['card_index']}"
        link = c["link"] or "no item"
        L.append(f"| {c['card_index']} | {nm} | {c['name'] or ''} | {c['faction'] or ''} "
                 f"| {c['power'] if c['power'] is not None else ''} "
                 f"| {len(c['sources'])} | {len(c['loot'])} | {len(c['reward_items'])} | {link} | {c['file']} |")
    L.append("")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- README

def _readme_md(table_rows):
    L = ["# Witcher 3 game database: start here", "",
         "This folder holds `w3db.sqlite` and the plain-text views generated from it. The database is built "
         "from the game's own REDkit files (quest graphs, journal, dialogue scenes, the string table, item and "
         "Gwent definitions) and from the player's save files. It is read-only for these views: nothing here "
         "writes to the game, REDkit or the saves. Nothing was reviewed by a person; every claim cites a file "
         "and a block.", "",
         "Regenerate everything with `py tools/gamedb/build.py` from the w3tracker folder.", "",
         "## Files in this folder", "",
         "- `README.md` - this file.",
         "- `INDEX.md` - every quest, grouped by pack and type, with how many quests can fail it and how many it fails.",
         "- `MISSABLE.md` - quests that another quest can fail, with the trigger and the decisive fact or status.",
         "- `quests/<stem>.md` - one dossier per quest: description, objectives, the files that run it, what can "
         "lose it, what it loses, NPC removals, dialogue choices, facts, rewards, Gwent decks and save evidence.",
         "- `quests.jsonl` - the same dossiers, one JSON object per line.",
         "- `facts.jsonl` - one object per fact: which quests set it and which test it (lists capped at 50).",
         "- `choices.jsonl` - one object per dialogue choice (per scene, locId and output) with a quest effect.",
         "- `CARDS.md`, `cards.jsonl` - Gwent cards, only when the items tables were built.",
         "- `w3db.sqlite` - the database. Every table is listed below.", "",
         "## Tables", ""]
    for name, n in table_rows:
        note = TABLE_NOTES.get(name, "(no description)")
        L.append(f"- `{name}` ({n} rows): {note}")
    L += ["", "## How to read evidence strength", "",
          "Relations between quests are stored in `quest_relations`, one row per (quest A, quest B, kind). "
          "Each kind has a different strength:", "",
          "- `fails` (strongest): a journal block in A's files has its Failure input wired for an entry of B. "
          "The file and block are cited.",
          "- `fail_when_journal`: B's own Failure input is fired by a journal status condition that tests an entry "
          "of A (for example, an entry of A is JS_Success). Strong when `hops` is small; `hops` counts graph steps "
          "back from the Failure input to the condition.",
          "- `fail_when_fact`: B's Failure input is fired by a fact test, and A sets that fact (set or add). "
          "Strong when `hops` is small (6 or fewer is treated as strong in MISSABLE.md). A is the writer of the "
          "fact; the link is through the fact, not a direct wire, so it is weaker than the journal case.",
          "- `fail_unless_fact`, `fail_unless_journal`: the reverse. B's Failure input fires when A's condition is "
          "false, so B is lost if A is skipped. Doing A does not lose B. These are listed apart and kept out of "
          "MISSABLE.md and the 'can be failed by' counts.",
          "- `fails_objective`: A marks one objective of B failed; B itself goes on. Listed apart and not counted "
          "as a loss.",
          "- `fact_test`, `journal_test`: dependency, not loss. B's files test something A sets or A's entry. "
          "Nothing is failed by this kind.",
          "- `removes_community`: weak. A switches off an NPC group (a community) that B's files reference. "
          "Switching off an NPC group does not by itself fail a quest.",
          "- `completes`, `starts_or_advances`: A completes or activates an entry of B. Not a failure.", "",
          "Limits: the evidence list stored per relation is capped at 20 items; `n` is the true total. "
          "`hops` is searched up to 12 steps back through the graph. A relation says what the files wire, "
          "not whether a player can reach or miss the step in practice.", "",
          "## Example queries", "",
          "Each query is one read-only statement. Run them with `sqlite3 w3db.sqlite` or any SQLite reader. "
          "Quest stems (for example `q402ciri`) are the file names of the quest journals. "
          "`quest` columns show the English title where one exists.", ""]
    for i, (title, sql) in enumerate(EXAMPLES, 1):
        L += [f"### {i}. {title}", "", "```sql", sql, "```", ""]
    L += ["## Row counts", "", "| table | rows |", "|---|---|"]
    for name, n in table_rows:
        L.append(f"| `{name}` | {n} |")
    L.append("")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- build

def build(con, verbose=True):
    t0 = time.time()
    out = Path(common.OUT)
    out.mkdir(parents=True, exist_ok=True)
    d = _load(con)
    qdir = out / "quests"
    shutil.rmtree(qdir, ignore_errors=True)
    qdir.mkdir(parents=True, exist_ok=True)

    recs = {g: _record(d, g) for g in d.quests}
    manifest = []

    for g, rec in recs.items():
        p = qdir / f"{_safe(rec['stem'])}.md"
        _write(p, _dossier_md(rec))
        manifest.append((_rel(out, p), "dossier", 1))

    _jsonl(out / "quests.jsonl", [recs[g] for g in sorted(recs, key=lambda g: recs[g]["stem"])])
    manifest.append(("quests.jsonl", "jsonl", len(recs)))

    index = _index_md(d, recs)
    _write(out / "INDEX.md", index)
    manifest.append(("INDEX.md", "index", index.count("\n- [")))

    missable = _missable_md(d, recs)
    _write(out / "MISSABLE.md", missable)
    manifest.append(("MISSABLE.md", "missable", missable.count("\n- **")))

    facts = _facts_rows(d)
    _jsonl(out / "facts.jsonl", facts)
    manifest.append(("facts.jsonl", "jsonl", len(facts)))

    choices = _choices_rows(d)
    _jsonl(out / "choices.jsonl", choices)
    manifest.append(("choices.jsonl", "jsonl", len(choices)))

    if {"gwent_cards", "items"} <= d.tables:
        cards = _cards(con, d)
        _write(out / "CARDS.md", _cards_md(cards))
        _jsonl(out / "cards.jsonl", cards)
        manifest.append(("CARDS.md", "cards", len(cards)))
        manifest.append(("cards.jsonl", "jsonl", len(cards)))
    elif verbose:
        print("  cards: gwent_cards or items table missing, CARDS.md skipped")

    # table list and counts for the README (read from the db, so it reflects the stages that ran)
    table_rows = []
    for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"):
        n = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        table_rows.append((name, n))
    readme = _readme_md(table_rows)
    _write(out / "README.md", readme)
    manifest.append(("README.md", "readme", len(table_rows)))

    # manifest: the only table written. A read-only connection cannot take it; say so and go on.
    try:
        con.execute("DELETE FROM views_manifest")
        con.executemany("INSERT INTO views_manifest VALUES (?,?,?)", manifest)
        con.commit()
        wrote = True
    except sqlite3.Error as exc:
        wrote = False
        if verbose:
            print(f"  views_manifest not written ({exc}); files were written anyway")

    if verbose:
        print(f"  dossiers: {len(recs)}, jsonl: quests {len(recs)}, facts {len(facts)}, choices {len(choices)}")
        print(f"  views written to {out} in {time.time() - t0:.1f}s; manifest {'written' if wrote else 'skipped'}")
