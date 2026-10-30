"""Read the NPC community phases a quest switches on and off, straight from its .w2phase.

Why this exists: whether an NPC can be talked to at all is not a journal fact. The quest log
stays Active while the NPC's community sits in a different story phase, which is the difference
between "the quest is still winnable" and "you can hand it in right now". A quest that offers a
turn-in activates one or more phases of the NPC's `.w2comm` (`CActivateStoryPhase`), and the rest
of the game swaps the NPC into other phases or deactivates the spawnset.

The statuette case this was written for: `mq3012_jade_statuettes.w2phase` activates exactly two
Triss phases, `triss_default` (her usual Novigrad spot) and `q310_ap_triss_dandelions` (Dandelion's
place during Final Preparations). `q309_casablanca.w2phase` moves her through a long list of
`q309_triss_*` phases, which is why she has nothing to say about the statuettes while Now or Never
runs. That is the code's own statement of the two windows, not an inference from save states.

  activations(g, community)    -> [{block, class, phase, deactivates, gates}]
  gates(g, block)              -> normalized journal/fact conditions feeding a block
  scenes(g, needle)            -> scene and context-dialog blocks that name a scene
  check_windows(path)          -> reviewed windows vs the phases the code actually activates

What makes a *dialogue option* available is a separate question from what switches a community
on, and it is answered by the block that offers the option. `dialogue_gates` reads a turn-in
dialogue block's own branch conditions, including the True/False output the graph took, so a fact
tested on the False branch is reported as "unset". For the statuettes the block is
`mq3012_jade_statuettes.w2phase` #161, a `CQuestContextDialogBlock` hung on Triss's default
dialogue (`triss_default.w2scene`): its branches test `q309_completed` on the False output - the
option exists while Now or Never is not completed - and `q310_philippa_rescued` as set, which is
why it comes back only after Philippa is rescued during Final Preparations. `fact_setters` says
which phase sets such a fact, so a gate is traced to the story event that opens it.

  dialogue_gates(g, block)     -> [{kind, name, state, via}] with False-branch polarity
  dialogue_blocks(g, needle)   -> the scene/dialogue blocks and their gates
  fact_setters(fact)           -> [{file, block, value}] every phase that sets the fact
  dialogue_evidence(idx, w)    -> reviewed window vs the option's actual branch conditions

CLI:
  py dialog_windows.py show <phase rel path> [--community triss.w2comm] [--stem mq3012] [--json out]
  py dialog_windows.py dialogue --stem mq3012noblestatuette [--json out]
  py dialog_windows.py scan [--limit 40] [--json out]
  py dialog_windows.py check data/cutoff_windows.json
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cr2w
import questgraph
from paths import QUEST_ROOT, REDKIT_R4

ACTIVATE = "CActivateStoryPhase"
DEACTIVATE = "CDeactivateSpawnset"
SCENE_BLOCKS = ("CQuestSceneBlock", "CQuestContextDialogBlock", "CQuestInteractionDialogBlock")
FACT_CLASS = "CQuestFactsDBChangingBlock"


def props(g, i):
    return {x["name"]: x["value"] for x in cr2w.props(g.p, g.p["exports"][i - 1])}


def _ref(value):
    if isinstance(value, dict):
        for key in ("ref_import", "ref_name", "ref"):
            if value.get(key):
                return str(value[key])
        return ""
    return str(value or "")


def gates(g, block):
    """Journal statuses and facts that gate a block, normalized and de-duplicated."""
    out, seen = [], set()
    for c in g.journal_conditions_upstream(block):
        if c["kind"] == "journal":
            stem = (c["resource"] or "").split("\\")[-1].removesuffix(".journal")
            item = {"kind": "journal", "resource": c["resource"], "quest": stem, "status": c["status"]}
        else:
            item = {"kind": "fact", "fact": c["fact"], "query": c["query"], "value": c["value"]}
        key = json.dumps(item, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def activations(g, community):
    """Every block that switches this community file into or out of a story phase."""
    needle = community.lower()
    out = []
    for e in g.p["exports"]:
        if e["className"] not in (ACTIVATE, DEACTIVATE):
            continue
        refs = cr2w.refs(g.p, e)
        if not any(needle in r.lower() for r in refs):
            continue
        ps = props(g, e["index"])
        out.append({
            "block": e["index"],
            "class": e["className"],
            "community": next((r for r in refs if needle in r.lower()), community),
            "phase": ps.get("phase") or "",
            "deactivates": e["className"] == DEACTIVATE,
            "gates": gates(g, e["index"]),
        })
    return out


def scenes(g, needle):
    """Scene and context-dialog blocks whose scene or target scene names `needle`."""
    needle = (needle or "").lower()
    out = []
    for e in g.p["exports"]:
        if e["className"] not in SCENE_BLOCKS:
            continue
        ps = props(g, e["index"])
        scene, target = _ref(ps.get("scene")), _ref(ps.get("targetScene"))
        if needle and needle not in (scene + target).lower():
            continue
        out.append({
            "block": e["index"],
            "class": e["className"],
            "scene": scene,
            "target_scene": target,
            "gates": gates(g, e["index"]),
        })
    return out


def _conditions_of(g, block):
    """The journal/fact conditions attached to one block (nested logic followed)."""
    ps = props(g, block)
    out = []
    for key in ("questCondition", "condition"):
        ref = ps.get(key)
        if isinstance(ref, dict) and ref.get("ref_chunk"):
            g._condition(ref["ref_chunk"], out, set(), 0)
    for ref in g.ref_list(ps.get("conditions")):
        g._condition(ref, out, set(), 0)
    return out


def _incoming(g, block):
    """[(source block, source socket name)] feeding `block`."""
    socks = g._sockets()
    out = []
    for src, dst in g._connections():
        if src in socks and dst in socks and socks[dst]["block"] == block and socks[src]["block"]:
            out.append((socks[src]["block"], socks[src]["name"]))
    return out


def _state(row):
    """What one condition row requires, before branch polarity is applied."""
    if row.get("kind") == "journal":
        return row.get("status") or ""
    query, value = row.get("query") or "", row.get("value")
    if query == "QF_DoesExist":
        return "set" if value in (1, True, "1") else "unset"
    return f"{query or 'value'} {value}"


def _name(row):
    if row.get("kind") == "journal":
        return re.split(r"[\\/]", row.get("resource") or "")[-1].removesuffix(".journal").lower()
    return row.get("fact") or ""


def _invert(state):
    return {"set": "unset", "unset": "set"}.get(state, state)


def dialogue_gates(g, block, depth=6):
    """Every fact/journal condition gating a dialogue block, with its branch polarity.

    A `CQuestConditionBlock` has True and False outputs, so the same fact appears twice in a
graph: once as set and once as unset. Reading the socket name is what makes the extracted gate
mean what the game means - `q309_completed` leaving a condition block through False is "Now or
Never not completed", which is the statuettes' first window. Only rows attached to the block
whose False output was taken are inverted, so a deeper ancestor keeps its own branch.
    """
    rows, seen = [], set()

    def walk(b, d):
        if b in seen or d > depth or not (1 <= b <= len(g.p["exports"])):
            return
        seen.add(b)
        # `A >= 1 || B >= 1` is one condition block with two facts, not two conditions: the label
        # is the only place the OR survives the flattening, so it is carried with each row.
        label = " ".join(str(props(g, b).get(k) or "") for k in ("name", "comment"))
        logic = "or" if "||" in label else ""
        for c in _conditions_of(g, b):
            name, st = _name(c), _state(c)
            if name:
                row = {"kind": c.get("kind", ""), "name": name, "state": st, "via": b}
                if logic:
                    row["logic"] = logic
                rows.append(row)
        for src, sock in _incoming(g, b):
            before = len(rows)
            walk(src, d + 1)
            if sock == "False":
                for r in rows[before:]:
                    if r["via"] == src:
                        r["state"] = _invert(r["state"])
                        r["via"] = f"{src} (False)"

    walk(block, 0)
    out, keys = [], set()
    for r in rows:
        k = (r["kind"], r["name"], r["state"])
        if k not in keys:
            keys.add(k)
            out.append(r)
    return out


def dialogue_blocks(g, needle=""):
    """The scene/dialogue blocks that play or hang off a scene naming `needle`, with their gates."""
    needle = (needle or "").lower()
    out = []
    for e in g.p["exports"]:
        if e["className"] not in SCENE_BLOCKS:
            continue
        ps = props(g, e["index"])
        scene, target = _ref(ps.get("scene")), _ref(ps.get("targetScene"))
        if needle and needle not in (scene + " " + target).lower():
            continue
        out.append({"block": e["index"], "class": e["className"],
                    "comment": ps.get("comment") or "", "scene": scene,
                    "target_scene": target, "gates": dialogue_gates(g, e["index"])})
    return out


_SETTERS = {}


def fact_setters(fact, limit=8):
    """Every quest phase that sets this fact, so a gate is traced to the event that opens it."""
    if fact in _SETTERS:
        return _SETTERS[fact]
    needle = fact.encode()
    out = []
    for p in QUEST_ROOT.rglob("*.w2phase"):
        try:
            if needle not in p.read_bytes():
                continue
            g = questgraph.G(p)
        except Exception:
            continue
        for e in g.p["exports"]:
            if e["className"] != FACT_CLASS:
                continue
            ps = props(g, e["index"])
            # setters write `factID`; conditions read `factId`. Both spellings are in the files.
            if (ps.get("factId") or ps.get("factID") or "") != fact:
                continue
            out.append({"file": str(p.relative_to(REDKIT_R4)), "block": e["index"],
                        "value": ps.get("value"), "comment": ps.get("comment") or ""})
            break
        if len(out) >= limit:
            break
    _SETTERS[fact] = out
    return out


def dialogue_evidence(idx, w):
    """Check a reviewed window against the option block's real branches.

    Returns (error, evidence). Every fact in `opens_at` must be tested as set somewhere in the
    block's branches and be set by a real phase; `close_gate` must be tested as unset, because
    that is the state the option exists in before the closing quest runs. This is the difference
    between a window proven by the dialogue graph and a window that reads well.
    """
    d = w.get("dialogue") or {}
    rel, block = d.get("file"), d.get("block")
    if not rel or not block:
        return ("a window that names a dialogue option must name the phase file and the block", {})
    path = Path(rel)
    if not path.exists():
        path = REDKIT_R4 / rel
    if not path.exists():
        return (f"{rel} is not on this install", {})
    g = questgraph.G(path)
    if not (1 <= block <= len(g.p["exports"])):
        return (f"{rel} has no block {block}", {})
    if g.cls(block) not in SCENE_BLOCKS:
        return (f"{rel}#{block} is a {g.cls(block)}, not a scene or dialogue block", {})
    rows = dialogue_gates(g, block)
    have = {(r["name"], r["state"]) for r in rows}
    setters = {}
    for fact in w.get("opens_at") or []:
        if (fact, "set") not in have:
            return (f"{rel}#{block} never tests {fact} as set; the reviewed opening gate is not "
                    "in the option's branches", {})
        found = fact_setters(fact)
        if not found:
            return (f"no quest phase sets {fact}, so it cannot open the window", {})
        setters[fact] = found
    gate = w.get("close_gate")
    if gate and (gate, "unset") not in have:
        return (f"{rel}#{block} never tests {gate} as unset; the reviewed closing gate is not in "
                "the option's branches", {})
    if gate:
        setters[gate] = fact_setters(gate)
    return ("", {"file": rel, "block": block, "class": g.cls(block),
                  "scene": _ref(props(g, block).get("scene")),
                  "target_scene": _ref(props(g, block).get("targetScene")),
                  "gates": rows, "setters": setters})


def load(phase_rel):
    path = Path(phase_rel)
    if not path.exists():
        path = REDKIT_R4 / phase_rel
    return questgraph.G(path)


def quest_phase_files(quest_index, stem):
    """The quest's own phase files, skipping the shared fixup phase."""
    q = quest_index.get("quests", {}).get(stem) or {}
    files = []
    for p in q.get("phases") or []:
        f = p.get("file") or ""
        if f and "bugfixing_phase" not in f.lower():
            files.append(f)
    return files


def check_windows(windows_path, quest_index_path=None):
    """Verify reviewed availability windows against the phases the code activates.

    A window that claims an NPC availability window must name the community file and the phases
    the quest itself activates. This fails when the phase file stops activating them, so the
    window cannot outlive the evidence.
    """
    windows_path = Path(windows_path)
    data = json.loads(windows_path.read_text(encoding="utf-8"))
    qi_path = Path(quest_index_path) if quest_index_path else Path(__file__).resolve().parent / "quest_index.json"
    quest_index = json.loads(qi_path.read_text(encoding="utf-8"))
    problems, checked = [], []
    for w in data.get("windows", []):
        if w.get("mechanism") != "availability":
            continue
        community = w.get("community") or ""
        wanted = w.get("community_phases") or []
        if not community or not wanted:
            problems.append(f"{w.get('id')}: availability window needs community and community_phases")
            continue
        found = {}
        for stem in w.get("affects") or []:
            for rel in quest_phase_files(quest_index, stem):
                g = load(rel)
                for row in activations(g, community):
                    if row["phase"]:
                        found.setdefault(row["phase"], []).append({"file": rel, "block": row["block"], "gates": row["gates"]})
        missing = [p for p in wanted if p not in found]
        if missing:
            problems.append(f"{w.get('id')}: {community} is never put into {', '.join(missing)} by "
                            f"{', '.join(w.get('affects') or [])}")
        checked.append({"id": w.get("id"), "community": community,
                        "phases": {p: found[p] for p in wanted if p in found}})
    for w in data.get("windows", []):
        if not w.get("dialogue"):
            continue
        err, ev = dialogue_evidence(quest_index, w)
        if err:
            problems.append(f"{w.get('id')}: {err}")
        else:
            checked.append({"id": w.get("id"), "community": ev["file"],
                            "phases": {"gates": ev["gates"]}})
    return checked, problems


def community_evidence(quest_index, w):
    """The file evidence for an availability window, or why the code does not support it.

    Returns (error, [evidence lines]). The lines name the phase file, the graph block and the
    community phase, so the review records what the game actually does rather than a paraphrase.
    """
    community = w.get("community") or ""
    wanted = w.get("community_phases") or []
    if not community or not wanted:
        return ("an availability window must name the community file and the phases the quest "
                "switches it into"), []
    found = {}
    for stem in w.get("affects") or []:
        for rel in quest_phase_files(quest_index, stem):
            g = load(rel)
            for row in activations(g, community):
                if row["phase"]:
                    found.setdefault(row["phase"], []).append({"file": rel, "block": row["block"]})
    missing = [p for p in wanted if p not in found]
    if missing:
        return (f"{community} is never put into {', '.join(missing)} by "
                f"{', '.join(w.get('affects') or [])}"), []
    rows = []
    for phase in wanted:
        for hit in found[phase]:
            rows.append({"phase": phase, "file": hit["file"], "block": hit["block"]})
    return "", rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    show = sub.add_parser("show")
    show.add_argument("phase")
    show.add_argument("--community", default="triss.w2comm")
    show.add_argument("--stem", default="")
    show.add_argument("--json")
    chk = sub.add_parser("check")
    chk.add_argument("windows")
    win = sub.add_parser("windows")
    win.add_argument("--stem", required=True)
    win.add_argument("--community", default="triss.w2comm")
    win.add_argument("--blocker", default="")
    win.add_argument("--json")
    dlg = sub.add_parser("dialogue")
    dlg.add_argument("--stem", required=True)
    dlg.add_argument("--json")
    scn = sub.add_parser("scan")
    scn.add_argument("--limit", type=int, default=40)
    scn.add_argument("--json")
    args = ap.parse_args()

    if args.cmd == "show":
        g = load(args.phase)
        doc = {
            "phase": args.phase,
            "community": args.community,
            "activations": activations(g, args.community),
            "scenes": scenes(g, args.stem),
        }
        if args.json:
            Path(args.json).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        for row in doc["activations"]:
            mark = "off" if row["deactivates"] else "on "
            print(f"{mark} block {row['block']:<6} {row['phase'] or '(spawnset off)'}")
            for gate in row["gates"]:
                if gate["kind"] == "journal":
                    print(f"       journal {gate['quest']} = {gate['status']}")
                else:
                    print(f"       fact {gate['fact']} {gate['query'] or ''} {gate['value']}")
        for row in doc["scenes"]:
            print(f"scene block {row['block']:<6} {row['scene'].split(chr(92))[-1]}"
                  + (f" -> {row['target_scene'].split(chr(92))[-1]}" if row["target_scene"] else ""))
            for gate in row["gates"]:
                if gate["kind"] == "journal":
                    print(f"       journal {gate['quest']} = {gate['status']}")
                else:
                    print(f"       fact {gate['fact']} {gate['query'] or ''} {gate['value']}")
        return 0

    if args.cmd == "windows":
        idx = json.loads((Path(__file__).resolve().parent / "quest_index.json").read_text(encoding="utf-8"))
        found = {}
        files = quest_phase_files(idx, args.stem)
        for rel in files:
            for row in activations(load(rel), args.community):
                if row["phase"]:
                    found.setdefault(row["phase"], []).append(row["block"])
        doc = {"stem": args.stem, "community": args.community, "files": files,
               "windows": [{"phase": p, "blocks": sorted(b)} for p, b in sorted(found.items())]}
        if args.blocker:
            other = {row["phase"] for row in activations(load(args.blocker), args.community) if row["phase"]}
            doc["blocked"] = {"file": args.blocker, "phases": sorted(other)}
        if args.json:
            Path(args.json).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        for row in doc["windows"]:
            print(f"window {row['phase']}: blocks " + ", ".join(str(b) for b in row["blocks"]))
        if "blocked" in doc:
            print(f"{args.blocker} puts {args.community} into " + ", ".join(doc["blocked"]["phases"]))
        return 0

    if args.cmd in ("dialogue", "scan"):
        idx = json.loads((Path(__file__).resolve().parent / "quest_index.json").read_text(encoding="utf-8"))
        if args.cmd == "dialogue":
            files = quest_phase_files(idx, args.stem)
            doc = {"stem": args.stem, "files": files, "blocks": []}
            for rel in files:
                g = load(rel)
                for row in dialogue_blocks(g):
                    if not row["scene"] and not row["target_scene"]:
                        continue
                    row["file"] = rel
                    doc["blocks"].append(row)
            for row in doc["blocks"]:
                print(f"{row['file']} #{row['block']} {row['class']} {row['comment']!r}")
                print(f"    scene {row['scene'].split(chr(92))[-1]}"
                      + (f" on {row['target_scene'].split(chr(92))[-1]}" if row["target_scene"] else ""))
                for gate in row["gates"]:
                    print(f"    {gate['kind']:7s} {gate['name']:34s} {gate['state']}")
            if args.json:
                Path(args.json).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            return 0
        rows = []
        for stem, q in sorted(idx["quests"].items()):
            for rel in quest_phase_files(idx, stem):
                g = load(rel)
                for row in dialogue_blocks(g):
                    if len(row["gates"]) < 2:
                        continue
                    rows.append({"stem": stem, "file": rel, **row})
                if len(rows) >= args.limit:
                    break
            if len(rows) >= args.limit:
                break
        for row in rows:
            gates = ", ".join(f"{g['name']}={g['state']}" for g in row["gates"][:6])
            print(f"{row['stem']:28s} #{row['block']:<5} {row['class']:28s} {gates}")
        if args.json:
            Path(args.json).write_text(json.dumps({"blocks": rows}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return 0

    checked, problems = check_windows(args.windows)
    for row in checked:
        print(f"{row['id']}: {row['community']} phases " + ", ".join(sorted(row["phases"])))
    for p in problems:
        print("FAIL", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
