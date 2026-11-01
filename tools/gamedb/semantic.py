"""Stage `semantic`: what the raw graph rows mean for quests.

Reads the tables of the graph, journal, scenes and strings stages and writes:

  phase_tree       which phase file includes which
  file_quest       which quest each phase file belongs to, and how that was decided
  journal_ops      every journal block: which entry it activates, completes, fails or tracks
  journal_tests    every condition that tests a journal entry's status
  fact_ops         every fact a phase or a dialogue choice sets, removes or tests
  spawnset_ops     every community a phase switches on or off
  fail_triggers    for each wired Failure input: the conditions upstream of it
  fail_paths       each backward path to a Failure input as one conjunction of block tests
  scene_objectives the objective(s) active when each conversation in a quest graph can play
  choice_effects   which facts and journal changes a dialogue choice leads to in the quest graph
  quest_relations  quest-to-quest effects with their evidence (the table to start from)

Nothing here is reviewed: a row says what the files say, with the file and block it came from.
"""
import json
from collections import defaultdict, deque

SCHEMA = """
CREATE TABLE IF NOT EXISTS phase_tree (parent_file INTEGER, block_idx INTEGER, child_file INTEGER);
CREATE TABLE IF NOT EXISTS file_quest (
    file_id INTEGER PRIMARY KEY, quest_guid TEXT, how TEXT, votes INTEGER
);
CREATE TABLE IF NOT EXISTS journal_ops (
    file_id INTEGER, block_idx INTEGER, block_class TEXT, op TEXT,
    entry_guid TEXT, entry_class TEXT, quest_guid TEXT, owner_quest TEXT
);
CREATE TABLE IF NOT EXISTS journal_tests (
    file_id INTEGER, node_idx INTEGER, owner_block INTEGER, status TEXT,
    entry_guid TEXT, entry_class TEXT, quest_guid TEXT, owner_quest TEXT
);
CREATE TABLE IF NOT EXISTS fact_ops (
    fact TEXT, op TEXT, value INTEGER, compare TEXT,
    file_id INTEGER, node_idx INTEGER, owner_block INTEGER, owner_quest TEXT,
    source TEXT, choice_loc_id INTEGER
);
CREATE TABLE IF NOT EXISTS spawnset_ops (
    file_id INTEGER, node_idx INTEGER, owner_block INTEGER, op TEXT, community TEXT, owner_quest TEXT
);
CREATE TABLE IF NOT EXISTS fail_triggers (
    file_id INTEGER, fail_block INTEGER, entry_guid TEXT, quest_guid TEXT, owner_quest TEXT,
    hops INTEGER, cond_block INTEGER, cond_node INTEGER, cond_class TEXT, via TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS fail_paths (
    file_id INTEGER, fail_block INTEGER, entry_guid TEXT, quest_guid TEXT, owner_quest TEXT,
    path INTEGER, n_tests INTEGER, truncated INTEGER, tests_json TEXT,
    anchor TEXT,  -- the journal entry activated last before the failure point: the path runs after it
    after_json TEXT  -- names of the sub-phases control passes through before the failure, nearest first
);
CREATE TABLE IF NOT EXISTS scene_objectives (
    scene TEXT, file_id INTEGER, scene_block INTEGER, objective_guid TEXT, hops INTEGER, quest_guid TEXT
);
CREATE TABLE IF NOT EXISTS choice_effects (
    scene TEXT, choice_loc_id INTEGER, output TEXT, file_id INTEGER, scene_block INTEGER, hops INTEGER,
    effect TEXT, target TEXT, value INTEGER, quest_guid TEXT
);
CREATE TABLE IF NOT EXISTS quest_relations (
    a_guid TEXT, b_guid TEXT, kind TEXT, n INTEGER, evidence TEXT
);
CREATE INDEX IF NOT EXISTS fact_ops_fact ON fact_ops(fact);
CREATE INDEX IF NOT EXISTS choice_effects_loc ON choice_effects(choice_loc_id);
CREATE INDEX IF NOT EXISTS journal_ops_quest ON journal_ops(quest_guid);
CREATE INDEX IF NOT EXISTS quest_relations_a ON quest_relations(a_guid);
CREATE INDEX IF NOT EXISTS quest_relations_b ON quest_relations(b_guid);
"""

JOURNAL_BLOCKS = ("CJournalQuestBlock", "CJournalQuestTrackBlock", "CJournalBlock",
                  "CJournalQuestObjectiveCounterGraphBlock", "CJournalQuestMappinStateBlock")
FACT_TESTS = ("CQuestFactsDBCondition", "CQuestFactsDBForbiddenCondition", "CQuestFactsDBExCondition")
FACT_SCRIPTS = {"RemoveFactQuest": "remove", "TryToAddUniqueFact": "set", "AddFactQuest": "add",
                "AddFact": "add", "FactsAddQuest": "add", "SetFactQuest": "set"}
# How far back from a Failure input to look for the condition that fires it.
FAIL_HOPS = 12
SHARED_MIN_QUESTS = 8
SHARED_MAX_SHARE = 0.3
SHARED_NAMES = ("bugfix", "character_journal_entries", "character_entries", "ff_all_hubs",
                "card_minigame_meta", "traveling_merchants", "patch_signal")
# How far forward from a scene output to follow a choice into the quest graph.
CHOICE_HOPS = 8
# Backward paths kept per Failure input; graphs with loops fan out fast.
MAX_PATHS = 64
# Blocks walked back per path, across sub-phases and files.
PATH_HOPS = 30
# Blocks walked back from a conversation to the objective that is active while it plays.
SCENE_HOPS = 150


def _pairs(params):
    """CQuestScriptBlock.parameters decode as a flat [name, value, name, value...] bag."""
    out, key = {}, None
    for p in params or []:
        if not isinstance(p, dict):
            continue
        if p.get("name") == "name":
            key = p.get("value")
        elif p.get("name") == "value" and key:
            v = p.get("value")
            out[key] = v.get("value") if isinstance(v, dict) and "variant_type" in v else v
            key = None
    return out


def fact_test_holds(t, v):
    """Whether a fact test holds when the fact's value is v (0 = absent). Mirrors the game's
    CQuestFactsDBCondition: compareFunc defaults to CF_Equal, queryFact QF_DoesExist compares
    existence (0/1) instead of the value."""
    if t["kind"] == "forbid":
        return not v
    want = t.get("value") or 0
    x = (1 if v else 0) if t.get("query") == "QF_DoesExist" else v
    return {"CF_Equal": x == want, "CF_NotEqual": x != want, "CF_Less": x < want, "CF_LessEqual": x <= want,
            "CF_Greater": x > want, "CF_GreaterEqual": x >= want}.get(t.get("compare") or "CF_Equal", x == want)


def _fact_polarity(t):
    """'set' when the test holds only once the fact is set, 'unset' when only while it is not."""
    on, off = fact_test_holds(t, 1), fact_test_holds(t, 0)
    return "set" if on and not off else "unset" if off and not on else None


def _short(t):
    keep = ("kind", "fact", "compare", "value", "query", "status", "entry", "quest", "group")
    return {k: t[k] for k in keep if t.get(k) is not None}


def build(con, verbose=True):
    q = con.execute
    # entry guid -> (class, quest guid); a quest's own guid maps to itself
    entry = {}
    for g, cls, root in q("SELECT guid, class, root_guid FROM journal_entries WHERE guid IS NOT NULL"):
        entry.setdefault(g, (cls, root))
    quests = {g for (g,) in q("SELECT guid FROM journal_quests WHERE category='quest'")}

    def quest_of(chain_json, leaf):
        """The quest a journal path points into: the deepest guid in the chain that is a quest."""
        try:
            chain = json.loads(chain_json or "[]")
        except ValueError:
            chain = []
        found = None
        for g in chain:
            if g in quests:
                found = g
        if found is None and leaf in entry:
            root = entry[leaf][1]
            found = root if root in quests else None
        return found

    # ---- phase tree ---------------------------------------------------------------
    path_id = {p: i for p, i in q("SELECT path, file_id FROM files")}
    rows = []
    for fid, idx, ref in q("""SELECT r.file_id, r.owner_block, r.ref_path FROM graph_refs r
                              WHERE r.ref_path LIKE '%.w2phase'"""):
        child = path_id.get(ref)
        if child and child != fid:
            rows.append((fid, idx, child))
    con.executemany("INSERT INTO phase_tree VALUES (?,?,?)", rows)
    parents = defaultdict(set)
    parent_blocks = defaultdict(list)
    for p, _b, c in rows:
        parents[c].add(p)
        parent_blocks[c].append((p, _b, c))

    # ---- journal paths per node -----------------------------------------------------
    jref = defaultdict(list)  # (file, node) -> [(prop, leaf, quest)]
    for fid, idx, prop, chain, leaf in q("SELECT file_id, idx, prop, guid_chain, leaf_guid FROM graph_journal_refs"):
        jref[(fid, idx)].append((prop, leaf, quest_of(chain, leaf)))

    # ---- which quest owns each phase file -------------------------------------------
    votes = defaultdict(lambda: defaultdict(int))
    for (fid, idx), refs in jref.items():
        for _prop, _leaf, qg in refs:
            if qg:
                votes[fid][qg] += 1
    owner, shared = {}, set()
    fpath = {i: p for p, i in path_id.items()}
    for fid, v in votes.items():
        best = max(v.items(), key=lambda kv: kv[1])
        total = sum(v.values())
        # Global fix-up and bookkeeping graphs touch many quests; crediting them to the quest they
        # mention most would make that quest "fail" every other one. They belong to no quest.
        if (len(v) >= SHARED_MIN_QUESTS and best[1] / total < SHARED_MAX_SHARE) or                 any(k in fpath.get(fid, "") for k in SHARED_NAMES):
            shared.add(fid)
            continue
        owner[fid] = (best[0], "journal", best[1])
    phase_files = [f for (f,) in q("SELECT file_id FROM files WHERE kind IN ('w2phase','w2quest')")]
    # files with no journal block of their own inherit from the phase that includes them
    changed = True
    while changed:
        changed = False
        for f in phase_files:
            if f in owner or f in shared:
                continue
            ps = [owner[p][0] for p in parents.get(f, ()) if p in owner]
            if len(set(ps)) == 1:
                owner[f] = (ps[0], "parent", 0)
                changed = True
    con.executemany("INSERT INTO file_quest VALUES (?,?,?,?)",
                    [(f, o[0], o[1], o[2]) for f, o in owner.items()] + [(f, None, "shared", 0) for f in shared])
    oq = lambda f: owner.get(f, (None,))[0]  # noqa: E731

    # ---- graph edges into a block, per input socket ----------------------------------
    incoming = defaultdict(list)  # (file, dst_block) -> [(dst_socket, src_block, src_socket)]
    for fid, sb, ss, db, ds in q("SELECT file_id, src_block, src_socket, dst_block, dst_socket FROM graph_edges"):
        incoming[(fid, db)].append((ds, sb, ss))

    # ---- journal ops ------------------------------------------------------------------
    ops = []
    marks = ",".join("?" * len(JOURNAL_BLOCKS))
    for fid, idx, cls in q(f"SELECT file_id, idx, class FROM graph_nodes WHERE is_block=1 AND class IN ({marks})",
                           JOURNAL_BLOCKS):
        refs = jref.get((fid, idx), [])
        if not refs:
            continue
        wired = {s for s, _, _ in incoming.get((fid, idx), [])}
        if cls == "CJournalQuestBlock":
            kinds = [s.lower() for s in ("Activate", "Success", "Failure") if s in wired] or ["unwired"]
        elif cls == "CJournalQuestTrackBlock":
            kinds = ["track"]
        else:
            kinds = [cls.replace("CJournalQuest", "").replace("GraphBlock", "").replace("Block", "").lower() or "journal"]
        for _prop, leaf, qg in refs:
            for k in kinds:
                ops.append((fid, idx, cls, k, leaf, entry.get(leaf, (None,))[0], qg, oq(fid)))
    con.executemany("INSERT INTO journal_ops VALUES (?,?,?,?,?,?,?,?)", ops)

    # ---- journal status tests ---------------------------------------------------------
    tests = []
    for fid, idx, ob, props in q("SELECT file_id, idx, owner_block, props_json FROM graph_nodes "
                                 "WHERE class='CQuestJournalStatusCondition'"):
        st = json.loads(props).get("status")
        for _prop, leaf, qg in jref.get((fid, idx), []):
            tests.append((fid, idx, ob, st, leaf, entry.get(leaf, (None,))[0], qg, oq(fid)))
    con.executemany("INSERT INTO journal_tests VALUES (?,?,?,?,?,?,?,?)", tests)

    # ---- facts ------------------------------------------------------------------------
    facts = []
    for fid, idx, ob, cls, props in q("""SELECT file_id, idx, owner_block, class, props_json FROM graph_nodes
            WHERE class IN ('CQuestFactsDBChangingBlock','CQuestFactsDBCondition','CQuestFactsDBForbiddenCondition',
                            'CQuestFactsDBExCondition','CQuestScriptBlock')"""):
        ps = json.loads(props)
        if cls == "CQuestFactsDBChangingBlock":
            op = "set" if ps.get("setExactValue") else "add"
            facts.append((ps.get("factID") or ps.get("factId"), op, ps.get("value"), None, fid, idx, ob, oq(fid), "phase", None))
        elif cls in FACT_TESTS:
            op = "forbid" if cls == "CQuestFactsDBForbiddenCondition" else "test"
            facts.append((ps.get("factId") or ps.get("factID"), op, ps.get("value"), ps.get("compareFunc"),
                          fid, idx, ob, oq(fid), "phase", None))
        else:
            fn = ps.get("functionName")
            if fn in FACT_SCRIPTS:
                args = _pairs(ps.get("parameters"))
                name = args.get("factId") or args.get("factName") or args.get("fact") or args.get("id")
                if isinstance(name, str):
                    val = args.get("value") if isinstance(args.get("value"), int) else None
                    facts.append((name, FACT_SCRIPTS[fn], val, None, fid, idx, ob, oq(fid), "script:" + fn, None))
    # dialogue choices: the scene is played by a CQuestSceneBlock in some phase; the choice's
    # facts are credited to that phase's quest
    scene_users = defaultdict(set)
    for fid, ob, ref in q("SELECT file_id, owner_block, ref_path FROM graph_refs WHERE ref_path LIKE '%.w2scene'"):
        scene_users[ref].add(fid)
    has_scenes = q("SELECT 1 FROM sqlite_master WHERE name='scene_choices'").fetchone()
    for path, sfid, cidx, loc, sets in (q("""SELECT f.path, c.file_id, c.idx, c.loc_id, c.sets_facts
                                            FROM scene_choices c JOIN files f ON f.file_id=c.file_id""")
                                        if has_scenes else []):
        for fact in json.loads(sets or "[]"):
            users = scene_users.get(path) or {None}
            for u in users:
                facts.append((fact, "set", None, None, u, None, None, oq(u) if u else None, "choice:" + path, loc))
    con.executemany("INSERT INTO fact_ops VALUES (?,?,?,?,?,?,?,?,?,?)", [f for f in facts if f[0]])

    # ---- spawnsets ----------------------------------------------------------------------
    sp = []
    for fid, idx, ob, cls, props in q("""SELECT file_id, idx, owner_block, class, props_json FROM graph_nodes
                                         WHERE class IN ('CDeactivateSpawnset','CActivateStoryPhase')"""):
        ps = json.loads(props)
        comm = None
        for k in ("spawnset", "community"):
            v = ps.get(k)
            if isinstance(v, dict) and v.get("ref_import"):
                comm = v["ref_import"].replace("\\", "/").lower()
        op = "off" if cls == "CDeactivateSpawnset" else "on:" + str(ps.get("phase") or "")
        sp.append((fid, idx, ob, op, comm, oq(fid)))
    con.executemany("INSERT INTO spawnset_ops VALUES (?,?,?,?,?,?)", sp)

    # ---- what fires each wired Failure input --------------------------------------------
    conds = defaultdict(list)  # (file, block) -> [(node, class, detail)]
    for fid, idx, ob, cls, props in q("""SELECT file_id, idx, owner_block, class, props_json FROM graph_nodes
            WHERE class IN ('CQuestFactsDBCondition','CQuestFactsDBForbiddenCondition','CQuestFactsDBExCondition',
                            'CQuestJournalStatusCondition')"""):
        ps = json.loads(props)
        if cls == "CQuestJournalStatusCondition":
            refs = jref.get((fid, idx), [])
            detail = {"status": ps.get("status"), "entry": refs[0][1] if refs else None,
                      "quest": refs[0][2] if refs else None}
        else:
            detail = {"fact": ps.get("factId") or ps.get("factID"), "value": ps.get("value"),
                      "compare": ps.get("compareFunc")}
        conds[(fid, ob)].append((idx, cls, detail))
    ft = []
    for fid, idx, cls, k, leaf, ecls, qg, own in ops:
        if k != "failure":
            continue
        seen, dq = {idx}, deque([(idx, 0)])
        while dq:
            b, h = dq.popleft()
            for sock, src, via in incoming.get((fid, b), []):
                if b == idx and sock != "Failure":
                    continue
                if src in seen or h + 1 > FAIL_HOPS:
                    continue
                seen.add(src)
                # `via` is the output the path leaves the condition's block by: on a False output the
                # failure follows when the condition does NOT hold
                for node, ccls, det in conds.get((fid, src), []):
                    ft.append((fid, idx, leaf, qg, own, h + 1, src, node, ccls, via, json.dumps(det)))
                dq.append((src, h + 1))
    con.executemany("INSERT INTO fail_triggers VALUES (?,?,?,?,?,?,?,?,?,?,?)", ft)

    # ---- the full condition behind each failure: one row per path ------------------------
    # A failure usually needs several conditions at once: Brothers in Arms: Velen fails at the Isle
    # of Mists only when the Skellige AND Novigrad allies are gathered AND Keira was NOT sent to Kaer
    # Morhen. Each backward path from a Failure input is a conjunction of block tests; a block test
    # is its conditions combined by the block's logic operation, required True or False depending on
    # which output the path leaves the block by.
    logic = {}  # (file, node) -> LO_And / LO_Or / ...
    parent_of = {}
    for fid, idx, par, props in q("SELECT file_id, idx, parent_idx, props_json FROM graph_nodes "
                                  "WHERE class='CQuestLogicOperationCondition'"):
        logic[(fid, idx)] = json.loads(props).get("logicOperation") or "LO_And"
    tests_of = defaultdict(list)  # (file, block) -> [test dicts]
    for fid, idx, ob, par, cls, props in q("""SELECT file_id, idx, owner_block, parent_idx, class, props_json
            FROM graph_nodes WHERE class IN ('CQuestFactsDBCondition','CQuestFactsDBForbiddenCondition',
                                             'CQuestFactsDBExCondition','CQuestJournalStatusCondition')"""):
        ps = json.loads(props)
        t = {"node": idx, "group": logic.get((fid, par), "LO_And")}
        if cls == "CQuestJournalStatusCondition":
            refs = jref.get((fid, idx), [])
            t.update(kind="journal", status=ps.get("status"), entry=refs[0][1] if refs else None,
                     quest=refs[0][2] if refs else None)
        else:
            t.update(kind="forbid" if cls == "CQuestFactsDBForbiddenCondition" else "fact",
                     fact=ps.get("factId") or ps.get("factID"), value=ps.get("value"),
                     compare=ps.get("compareFunc") or "CF_Equal", query=ps.get("queryFact") or "QF_Sum")
        tests_of[(fid, ob)].append(t)
    ops_by_block_early = defaultdict(list)
    for fid, idx, cls, k, leaf, ecls, qg, own in ops:
        ops_by_block_early[(fid, idx)].append((k, leaf, qg))
    node = {}
    for fid, idx, cls, gi, pi, props in q("""SELECT file_id, idx, class, graph_idx, parent_idx,
            CASE WHEN class='CQuestPhaseInputBlock' THEN props_json END FROM graph_nodes
            WHERE is_block=1 OR class IN ('CQuestGraph','CQuestPhase')"""):
        node[(fid, idx)] = (cls, gi, pi, props)

    def enclosing(f, b):
        """Where control comes from when it enters the sub-phase that holds block b: the phase
        block embedding it in the same file, or the phase blocks of other files including it."""
        cls, gi, _pi, props = node.get((f, b), (None, None, None, None))
        if cls != "CQuestPhaseInputBlock":
            return []
        ps = json.loads(props or "{}")
        name = ps.get("socketID") or ps.get("name") or "In"
        holder = node.get((f, gi), (None, None, None, None))[2] if gi else None
        if holder and node.get((f, holder), ("",))[0] not in ("CQuestPhase", ""):
            return [(f, holder, name)]
        # Leaving the file's top graph would follow every place that includes it, up through the
        # whole game structure: the paths explode and say nothing more about this quest.
        return []

    node_label = {(f, i): lb for f, i, lb in q("SELECT file_id, idx, label FROM graph_nodes "
                                               "WHERE class='CQuestPhaseBlock' AND label IS NOT NULL")}
    fp = []
    for fid, idx, cls, k, leaf, ecls, qg, own in ops:
        if k != "failure":
            continue
        paths = []

        def back(f, b, trail, depth, want, anchor):
            """Walk backwards from block b of file f. `want` limits the input socket on the first
            block (Failure) and after leaving a sub-phase (the phase input's socket name)."""
            if len(paths) >= MAX_PATHS:
                return
            srcs = [(s_, v) for sock, s_, v in incoming.get((f, b), []) if want is None or sock == want]
            if not srcs:
                up = enclosing(f, b)
                if up and depth < PATH_HOPS:
                    for uf, ub, name in up:
                        back(uf, ub, trail, depth + 1, name, anchor)
                    return
                paths.append((trail, False, anchor))
                return
            if depth >= PATH_HOPS:
                paths.append((trail, True, anchor))
                return
            for src, via in srcs:
                if (f, src) in visiting:
                    paths.append((trail, True, anchor))
                    continue
                step = trail
                lbl = node_label.get((f, src))
                if lbl:
                    after_here = after_of.setdefault(id(paths), [])
                    if lbl not in after_here:
                        after_here.append(lbl)
                if tests_of.get((f, src)):
                    step = trail + [{"file": f, "block": src, "via": via, "require": via != "False",
                                     "tests": tests_of[(f, src)]}]
                # the most recent journal activation before the failure says when the path runs
                a2 = anchor or next((leaf_ for k_, leaf_, _q in ops_by_block_early.get((f, src), ())
                                     if k_ in ("activate", "success")), None)
                visiting.add((f, src))
                back(f, src, step, depth + 1, None, a2)
                visiting.discard((f, src))

        visiting = set()
        after_of = {}
        back(fid, idx, [], 0, "Failure", None)
        after = json.dumps(after_of.get(id(paths), [])[:8])
        for n, (trail, cut, anchor) in enumerate(paths):
            fp.append((fid, idx, leaf, qg, own, n, len(trail), int(cut), json.dumps(trail), anchor, after))
    con.executemany("INSERT INTO fail_paths VALUES (?,?,?,?,?,?,?,?,?,?,?)", fp)

    # ---- what a dialogue choice does in the quest graph -----------------------------------
    # The choice reaches a scene output; the CQuestSceneBlock playing that scene has an output socket
    # of the same name; walk forward from it to the fact and journal blocks it fires.
    ops_by_block = defaultdict(list)
    for fid, idx, cls, k, leaf, ecls, qg, own in ops:
        ops_by_block[(fid, idx)].append((k, leaf, qg))
    sets_by_block = defaultdict(list)
    for fact, op, val, fid, ob in q("SELECT fact, op, value, file_id, owner_block FROM fact_ops "
                                    "WHERE source='phase' OR source LIKE 'script:%'"):
        if op in ("set", "add", "remove"):
            sets_by_block[(fid, ob)].append((fact, op, val))
    outgoing = defaultdict(list)
    for fid, sb, ss, db in q("SELECT file_id, src_block, src_socket, dst_block FROM graph_edges"):
        outgoing[(fid, sb, ss)].append(db)
        outgoing[(fid, sb, None)].append(db)
    block_cls = {(f, i): c for f, i, c in q("SELECT file_id, idx, class FROM graph_nodes WHERE is_block=1")}
    scene_blocks = defaultdict(list)
    for fid, ob, ref in q("SELECT file_id, owner_block, ref_path FROM graph_refs WHERE prop='scene'"):
        scene_blocks[ref].append((fid, ob))
    ce = []
    if has_scenes:
        for path, loc, outs in q("""SELECT f.path, c.loc_id, c.leads_to_outputs FROM scene_choices c
                                    JOIN files f ON f.file_id=c.file_id WHERE c.leads_to_outputs != '[]'"""):
            for out in json.loads(outs):
                for fid, sb in scene_blocks.get(path, ()):
                    seen, dq = set(), deque((d, 1) for d in outgoing.get((fid, sb, out), ()))
                    while dq:
                        b, h = dq.popleft()
                        if b in seen or h > CHOICE_HOPS:
                            continue
                        seen.add(b)
                        for fact, op, val in sets_by_block.get((fid, b), ()):
                            ce.append((path, loc, out, fid, sb, h, "fact_" + op, fact, val, oq(fid)))
                        for k, leaf, qg in ops_by_block.get((fid, b), ()):
                            ce.append((path, loc, out, fid, sb, h, "journal_" + k, leaf, None, qg))
                        if block_cls.get((fid, b)) == "CQuestSceneBlock":
                            continue  # the next conversation owns what follows it
                        dq.extend((d, h + 1) for d in outgoing.get((fid, b, None), ()))
    con.executemany("INSERT INTO choice_effects VALUES (?,?,?,?,?,?,?,?,?,?)", ce)

    # ---- which objective is on screen when a conversation plays -----------------------------
    # Walk back from every CQuestSceneBlock to the nearest blocks that activate an objective (into
    # the embedding phase when a sub-phase input is reached). Those objectives are the ones the
    # player has highlighted while the scene can start, so a choice in that scene is "now".
    obj_act = defaultdict(list)
    for fid, idx, cls, k, leaf, ecls, qg, own in ops:
        if k == "activate" and ecls == "CJournalQuestObjective":
            obj_act[(fid, idx)].append(leaf)
    root_inputs = defaultdict(list)  # file -> its top graph's phase inputs (entry points)

    def up_from(f, b):
        """Predecessors when control enters b from outside: the embedding phase in this file, or,
        at the file's top graph, every phase block in other files that includes this file."""
        up = enclosing(f, b)
        if up:
            return [(uf, ub) for uf, ub, _n in up]
        if node.get((f, b), ("",))[0] == "CQuestPhaseInputBlock":
            return [(pf, pb) for pf, pb, _c in parent_blocks.get(f, ())]
        return []

    so = []
    for path, blocks in scene_blocks.items():
        for fid, sb in blocks:
            seen, dq, found = {(fid, sb)}, deque([(fid, sb, 0)]), []
            while dq:
                f, b, h = dq.popleft()
                if obj_act.get((f, b)) and (f, b) != (fid, sb):
                    found += [(g, h) for g in obj_act[(f, b)]]
                    continue  # nearest on this branch: what lies behind it is an older objective
                if h >= SCENE_HOPS:
                    continue
                preds = [(f, s_) for _sock, s_, _v in incoming.get((f, b), [])] or up_from(f, b)
                for nxt in preds:
                    if nxt not in seen:
                        seen.add(nxt)
                        dq.append((nxt[0], nxt[1], h + 1))
            for g, h in found:
                so.append((path, fid, sb, g, h, oq(fid)))
    con.executemany("INSERT INTO scene_objectives VALUES (?,?,?,?,?,?)", so)

    # ---- quest relations ----------------------------------------------------------------
    rel = defaultdict(list)

    def add(a, b, kind, ev):
        if a and b and a != b:
            rel[(a, b, kind)].append(ev)

    for fid, idx, cls, k, leaf, ecls, qg, own in ops:
        if k in ("activate", "success", "failure"):
            kind = {"activate": "starts_or_advances", "success": "completes", "failure": "fails"}[k]
            if k == "failure" and ecls != "CJournalQuest":
                kind = "fails_objective"  # an objective marked failed; the quest itself goes on
            add(own, qg, kind, {"file": fid, "block": idx, "entry": leaf, "entry_class": ecls})
    def objective_only(leaf):
        return entry.get(leaf, (None,))[0] != "CJournalQuest"

    writers = defaultdict(set)
    for fact, owq in q("SELECT DISTINCT fact, owner_quest FROM fact_ops WHERE op IN ('set','add') AND owner_quest IS NOT NULL"):
        writers[fact].add(owq)
    # One relation per decisive test on a failure path. A test is decisive when the path needs it to
    # come out one way on its own: alone in its block, in an AND block that must hold, or in an OR
    # block that must fail. Anything else only takes part ("fail_involves_*").
    for fid, fb, leaf, qg, own, n, nt, cut, tj, _anchor, _after in fp:
        if objective_only(leaf):
            continue
        trail = json.loads(tj)
        summary = [{"require": s_["require"], "tests": [_short(t) for t in s_["tests"]]} for s_ in trail]
        for pos, step in enumerate(trail):
            step_tests = step["tests"]
            group = step_tests[0]["group"] if step_tests else "LO_And"
            decisive = len(step_tests) == 1 or (group == "LO_And" and step["require"]) or                 (group == "LO_Or" and not step["require"])
            for t in step_tests:
                ev = {"file": fid, "fail_block": fb, "path": n, "hops": pos + 1, "via": step["via"],
                      "truncated": bool(cut), "path_tests": summary, **_short(t)}
                if t["kind"] == "journal":
                    if not t.get("quest"):
                        continue
                    if not decisive:
                        add(t["quest"], qg, "fail_involves_journal", ev)
                    else:
                        add(t["quest"], qg, "fail_when_journal" if step["require"] else "fail_unless_journal", ev)
                    continue
                pol = _fact_polarity(t)
                for w in writers.get(t.get("fact"), ()):
                    if not decisive or pol is None:
                        add(w, qg, "fail_involves_fact", ev)
                    else:
                        add(w, qg, "fail_when_fact" if (pol == "set") == step["require"] else "fail_unless_fact", ev)
    for fact, op, owq in q("SELECT DISTINCT fact, op, owner_quest FROM fact_ops WHERE op IN ('test','forbid')"):
        for w in writers.get(fact, ()):
            add(w, owq, "fact_" + op, {"fact": fact})
    for fid, idx, ob, st, leaf, ecls, qg, own in tests:
        add(qg, own, "journal_test", {"file": fid, "node": idx, "status": st, "entry": leaf})
    users = defaultdict(set)
    for fid, ref in q("SELECT DISTINCT file_id, ref_path FROM graph_refs WHERE ref_path LIKE '%.w2comm'"):
        if oq(fid):
            users[ref].add(oq(fid))
    for fid, idx, ob, op, comm, own in sp:
        if op == "off" and comm:
            for u in users.get(comm, ()):
                add(own, u, "removes_community", {"file": fid, "node": idx, "community": comm})
    con.executemany("INSERT INTO quest_relations VALUES (?,?,?,?,?)",
                    [(a, b, k, len(ev), json.dumps(ev[:20])) for (a, b, k), ev in rel.items()])
    if verbose:
        for t in ("phase_tree", "file_quest", "journal_ops", "journal_tests", "fact_ops", "spawnset_ops",
                  "fail_triggers", "fail_paths", "scene_objectives", "choice_effects", "quest_relations"):
            print(f"  {t}: {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
