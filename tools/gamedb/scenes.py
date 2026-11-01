"""Stage `scenes`: the scene graph of every .w2scene under REDkit, one row per structural element.

A scene is a graph of exports. Sections hold lines and choices; a choice holds choice lines; every
element continues to the next one through `nextLinkElement`, and flow blocks branch through
`trueLink` / `falseLink`, `cases` / `thenLink` / `defaultLink` and `outputs`. `linkedElements` on
an element lists the elements that run into it (its predecessors), so it is only written for
scripts, as 'linked' edges from the predecessor to the script.

Dialogue choices carry what the rest of the toolchain needs to join a scene to the quest graph:
the facts the choice sets (questindex.scene_choices, matched by locId and order), and the
CStorySceneOutput names its branch reaches. A CStorySceneOutput name is the output socket of the
CQuestSceneBlock in a quest graph that plays the scene, so `leads_to_outputs` says which quest
branch a dialogue choice leads to. The walk stops at another choice section, because the choices
there own what follows.

Read-only against REDkit: each file is parsed once here, and the scene_* tables and the shared
`files` table are the only writes. Output is git-ignored.
"""
import json
import math
import time
from collections import Counter, defaultdict, deque

import common
import cr2w
import questindex

SCHEMA = """
CREATE TABLE IF NOT EXISTS scene_nodes (
    file_id     INTEGER,
    idx         INTEGER,
    class       TEXT,
    parent_idx  INTEGER,
    section_idx INTEGER,       -- nearest CStorySceneSection / CStorySceneCutsceneSection (itself for a section)
    label       TEXT,
    loc_id      INTEGER,       -- the element's own text: choiceLine / dialogLine, else first locId
    props_json  TEXT,
    PRIMARY KEY(file_id, idx)
);
CREATE TABLE IF NOT EXISTS scene_links (
    file_id   INTEGER,
    from_idx  INTEGER,
    to_idx    INTEGER,
    kind      TEXT           -- next | linked | choice | branch:<prop>
);
CREATE INDEX IF NOT EXISTS scene_links_from ON scene_links(file_id, from_idx);
CREATE TABLE IF NOT EXISTS scene_lines (
    file_id     INTEGER,
    idx         INTEGER,
    section_idx INTEGER,
    speaker     TEXT,          -- voicetag
    loc_id      INTEGER        -- dialogLine
);
CREATE INDEX IF NOT EXISTS scene_lines_loc ON scene_lines(loc_id);
CREATE TABLE IF NOT EXISTS scene_choices (
    file_id          INTEGER,
    idx              INTEGER,  -- the CStorySceneChoiceLine export
    section_idx      INTEGER,
    loc_id           INTEGER,  -- choiceLine locId: join strings(loc_id) for the wording
    one_shot         INTEGER,  -- singleUseChoice
    ord              INTEGER,  -- order of the choice line within the scene
    sets_facts       TEXT,     -- JSON list: facts taking this choice sets (NULL when not matched)
    section_facts    TEXT,     -- JSON list: facts the surrounding section names (NULL when not matched)
    leads_to_outputs TEXT,     -- JSON list: CStorySceneOutput names reached from this choice
    PRIMARY KEY(file_id, idx)
);
CREATE INDEX IF NOT EXISTS scene_choices_loc ON scene_choices(loc_id);
CREATE TABLE IF NOT EXISTS scene_outputs (
    file_id  INTEGER,
    idx      INTEGER,
    name     TEXT,
    PRIMARY KEY(file_id, idx)
);
CREATE INDEX IF NOT EXISTS scene_outputs_name ON scene_outputs(name);
CREATE TABLE IF NOT EXISTS scene_inputs (
    file_id  INTEGER,
    idx      INTEGER,
    name     TEXT,
    PRIMARY KEY(file_id, idx)
);
CREATE INDEX IF NOT EXISTS scene_inputs_name ON scene_inputs(name);
"""

SECTIONS = frozenset({"CStorySceneSection", "CStorySceneCutsceneSection", "CStorySceneVideoSection"})
NAMED_KEPT = frozenset({"CStorySceneChoice", "CStorySceneInput", "CStorySceneOutput",
                        "CStorySceneFlowCondition", "CStorySceneFlowSwitch", "CStorySceneFlowSwitchCase",
                        "CStorySceneScript"})
# camera / animation / event / light / dialogset / lipsync / mimic noise, never kept as a node
NOISE = ("Event", "Camera", "Animation", "Light", "Dialogset", "Lipsync", "Mimic")
# position-like props: layout of the editor graph, not story content
DROP_PROPS = frozenset({"position", "sockets", "color", "placement", "slotPlacement"})
# the text an element itself carries, in preference order; any other locId is the fallback
TEXT_PROPS = ("choiceLine", "dialogLine", "commentText")
# An output or input left at its default carries no name property at all; the quest graph's
# CQuestSceneBlock then shows the default socket name ("Output" / "Input").
DEFAULT_OUTPUT = "Output"
DEFAULT_INPUT = "Input"
LABEL_PROPS = ("sectionName", "inputName", "name", "comment", "functionName", "factId", "elementID")
WALK_LIMIT = 200       # BFS pops per choice line
ANCESTOR_LIMIT = 12    # parent hops when looking for the section an element belongs to


def kept(cls):
    if any(n in cls for n in NOISE):
        return False
    return (cls in SECTIONS or cls in NAMED_KEPT or cls.endswith("ChoiceLine")
            or any(k in cls for k in ("Fact", "Condition", "Quest")))


def _clean(v):
    """JSON-safe copy of a decoded value (non-finite floats become null)."""
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    return v


def scan(path):
    """Everything one scene file contributes: row lists per table, plus the class counts.

    Raises when the file cannot be read; the caller records that in files.error.
    """
    p = cr2w.parse(path)
    ex = {e["index"]: e for e in p["exports"]}
    props = {}
    for e in p["exports"]:
        props[e["index"]] = cr2w.props(p, e)
    vals = {i: {v["name"]: v["value"] for v in pr} for i, pr in props.items()}

    def cls(i):
        return ex[i]["className"]

    def val(i, name):
        return vals.get(i, {}).get(name)

    def ref(i, name):
        v = val(i, name)
        if isinstance(v, dict) and v.get("ref_chunk") in ex:
            return v["ref_chunk"]
        return None

    def chunks(i, name):
        return [c for c in questindex.chunk_array(val(i, name)) if c in ex]

    def text(i, name):
        v = val(i, name)
        return v if isinstance(v, str) and v else None

    def loc_of(i, names=TEXT_PROPS):
        for n in names:
            v = val(i, n)
            if isinstance(v, dict) and "locId" in v:
                return v["locId"]
        for v in vals.get(i, {}).values():
            if isinstance(v, dict) and "locId" in v:
                return v["locId"]
        return None

    def section_of(i):
        for _ in range(ANCESTOR_LIMIT):
            if not i or i not in ex:
                return None
            if cls(i) in SECTIONS:
                return i
            i = ex[i]["parentID"]
        return None

    # every outgoing or incoming link, as (from, to, kind)
    edges = []
    for i in ex:
        c = cls(i)
        nxt = ref(i, "nextLinkElement")
        if nxt:
            edges.append((i, nxt, "next"))
        if c == "CStorySceneFlowCondition":
            for prop in ("trueLink", "falseLink"):
                t = ref(i, prop)
                if t:
                    edges.append((i, t, "branch:" + prop))
        elif c == "CStorySceneFlowSwitch":
            t = ref(i, "defaultLink")
            if t:
                edges.append((i, t, "branch:defaultLink"))
            for t in chunks(i, "cases"):
                edges.append((i, t, "branch:cases"))
        elif c == "CStorySceneFlowSwitchCase":
            t = ref(i, "thenLink")
            if t:
                edges.append((i, t, "branch:thenLink"))
        elif c == "CStorySceneRandomizer":
            for t in chunks(i, "outputs"):
                edges.append((i, t, "branch:outputs"))
        elif c in SECTIONS:
            t = ref(i, "choice")
            if t:
                edges.append((i, t, "choice"))
        elif c == "CStorySceneScript":
            for t in chunks(i, "linkedElements"):
                edges.append((t, i, "linked"))

    walk = defaultdict(list)
    for a, b, k in edges:
        if k == "next" or k.startswith("branch:"):
            walk[a].append(b)

    def leads_to(choice):
        """Output names reached from a choice line along next / branch links.

        Stops at another choice section (its choices own what follows) and at the step limit.
        """
        outs = set()
        seen = {choice}
        queue = deque(walk.get(choice, []))
        steps = 0
        while queue and steps < WALK_LIMIT:
            n = queue.popleft()
            steps += 1
            if n in seen or n not in ex:
                continue
            seen.add(n)
            if cls(n) == "CStorySceneOutput":
                outs.add(text(n, "name") or DEFAULT_OUTPUT)
                continue
            if cls(n) in SECTIONS and ref(n, "choice"):
                continue
            queue.extend(walk.get(n, []))
        return sorted(outs)

    nodes, lines, choices, outputs, inputs = [], [], [], [], []
    kept_counts = Counter()
    counts = Counter()

    for i in sorted(ex):
        c = cls(i)
        if c == "CStorySceneLine":
            lines.append((i, section_of(i), text(i, "voicetag"), loc_of(i, ("dialogLine",))))
            counts["line"] += 1
        if c == "CStorySceneOutput":
            outputs.append((i, text(i, "name") or DEFAULT_OUTPUT))
        if c == "CStorySceneInput":
            inputs.append((i, text(i, "inputName") or DEFAULT_INPUT))
        if kept(c):
            kept_counts[c] += 1
            label = next((text(i, n) for n in LABEL_PROPS if text(i, n)), None)
            pj = {}
            for v in props[i]:
                name = v["name"]
                if name in DROP_PROPS:
                    continue
                value = v["value"]
                if isinstance(value, dict) and "raw_hex" in value:
                    # an array the reader left raw: the export indices are the content
                    if str(v["type"]).startswith("array"):
                        arr = questindex.chunk_array(value)
                        if arr:
                            pj[name] = arr
                    continue
                pj[name] = _clean(value)
            nodes.append((i, c, ex[i]["parentID"], section_of(i) if c not in SECTIONS else i,
                          label, loc_of(i), json.dumps(pj, ensure_ascii=False)))

    # dialogue choices: the facts from questindex, matched by locId in order, and the reach
    if any(cls(i) == "CStorySceneChoiceLine" for i in ex):
        theirs = defaultdict(deque)
        for r in questindex.scene_choices(path):
            theirs[r["locid"]].append(r)
        for ord_, i in enumerate(k for k in sorted(ex) if cls(k) == "CStorySceneChoiceLine"):
            loc = loc_of(i, ("choiceLine",))
            match = theirs[loc].popleft() if theirs.get(loc) else None
            counts["choice_matched" if match else "choice_unmatched"] += 1
            choices.append((i, section_of(i), loc, 1 if val(i, "singleUseChoice") else 0, ord_,
                            json.dumps(match["section_sets"]) if match else None,
                            json.dumps(match["section_facts"]) if match else None,
                            json.dumps(leads_to(i))))

    return {"version": p["version"], "nodes": nodes, "links": edges, "lines": lines,
            "choices": choices, "outputs": outputs, "inputs": inputs,
            "counts": counts, "kept": kept_counts}


def build(con, verbose=True):
    t0 = time.time()
    paths = sorted(common.R4.rglob("*.w2scene"))
    totals = Counter()
    kept_totals = Counter()
    parsed = errors = 0
    for n, path in enumerate(paths, 1):
        rel = common.rel(path)
        size = path.stat().st_size
        try:
            s = scan(path)
        except Exception as e:  # unreadable or truncated: recorded, the build goes on
            common.file_id(con, rel, "w2scene", size, None, f"{type(e).__name__}: {e}")
            errors += 1
            continue
        fid = common.file_id(con, rel, "w2scene", size, s["version"], None)
        parsed += 1
        con.executemany("INSERT INTO scene_nodes VALUES (?,?,?,?,?,?,?,?)",
                        [(fid,) + r for r in s["nodes"]])
        con.executemany("INSERT INTO scene_links VALUES (?,?,?,?)",
                        [(fid,) + r for r in s["links"]])
        con.executemany("INSERT INTO scene_lines VALUES (?,?,?,?,?)",
                        [(fid,) + r for r in s["lines"]])
        con.executemany("INSERT INTO scene_choices VALUES (?,?,?,?,?,?,?,?,?)",
                        [(fid,) + r for r in s["choices"]])
        con.executemany("INSERT INTO scene_outputs VALUES (?,?,?)", [(fid,) + r for r in s["outputs"]])
        con.executemany("INSERT INTO scene_inputs VALUES (?,?,?)", [(fid,) + r for r in s["inputs"]])
        totals.update(s["counts"])
        kept_totals.update(s["kept"])
        totals["scene_nodes"] += len(s["nodes"])
        totals["scene_links"] += len(s["links"])
        totals["scene_lines"] += len(s["lines"])
        totals["scene_choices"] += len(s["choices"])
        totals["scene_outputs"] += len(s["outputs"])
        totals["scene_inputs"] += len(s["inputs"])
        if verbose and n % 500 == 0:
            print(f"  {n}/{len(paths)} files, {time.time() - t0:.0f}s", flush=True)
    if verbose:
        print(f"  {len(paths)} .w2scene files: {parsed} parsed, {errors} errors", flush=True)
        for k in ("scene_nodes", "scene_links", "scene_lines", "scene_choices", "scene_outputs", "scene_inputs"):
            print(f"  {k}: {totals[k]}", flush=True)
        print("  classes kept: " + ", ".join(f"{k}={v}" for k, v in kept_totals.most_common()), flush=True)
        print(f"  choices matched to questindex: {totals['choice_matched']}, unmatched: {totals['choice_unmatched']}",
              flush=True)
