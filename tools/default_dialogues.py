"""Quest steps that run through an NPC's default dialogue, and the story points that switch it off.

Why this exists: a quest step can be a `CQuestContextDialogBlock` that hangs an extra option on an
NPC's everyday chat (`<npc>_default.w2scene`). That chat only plays while one
`CQuestInteractionDialogBlock` loop runs, and the loop is held by two counters: it starts on
`<npc>_dd_start` and stops on `<npc>_dd_stop`. When a main quest sets the stop fact and no later
story point sets the start fact again, the option is gone for good. The journal still says Active,
and the quest may only be failed much later, if at all.

Berengar's Blade is the case this was written for. `mq4005_sword.w2phase` #72 hangs "Vesemir about
sword" on `vesemir_default.w2scene`, and that block is the only way on to the boat, the cave and
the chort. `quest_npcs_default_dialogues.w2phase` #3960 plays `vesemir_default.w2scene` until
`vesemir_dd_stop` is set. `q403_battle.w2phase` sets it in "Switch Off Default Dialogs" (#31 ->
#2440), the first block of the Supporters phase, which starts with the Council phase when The
Battle of Kaer Morhen begins. Every `vesemir_dd_start` setter is in the prologue or the first
Kaer Morhen visit. So Vesemir cannot be asked about the sword once the battle has started, even
though the journal only fails the quest later, at `q403_council`.

  build_index()            -> {"hooks", "players", "setters"} read from every quest phase file
  owners(rel, own)         -> the quest stems that run a phase file (sub-phases via their main file)
  window_evidence(idx, w)  -> (error, evidence) for a reviewed `dialogue_off` window
  scan(idx)                -> one row per hook, with the stop/start setters and the story order

CLI:
  py default_dialogues.py index           rebuild tools/default_dialogue_index.json (slow: reads every phase)
  py default_dialogues.py scan [--md out] every hook, and which ones a main quest switches off for good
  py default_dialogues.py check           validate every dialogue_off window in cutoff_windows.json
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dialog_windows as dw
import questgraph
from paths import HERE, REDKIT_R4, ROUTE, TRACKER

INDEX = HERE / "default_dialogue_index.json"
WINDOWS = HERE / "cutoff_windows.json"
CUTOFFS = TRACKER / "data" / "cutoffs.json"
DEFAULT_SCENE = re.compile(r"_default\.w2scene$", re.I)
HOOK = "CQuestContextDialogBlock"
PLAYER = "CQuestInteractionDialogBlock"


def _phase_files():
    for root in (REDKIT_R4 / "quests", REDKIT_R4 / "dlc"):
        if root.exists():
            yield from sorted(root.rglob("*.w2phase"))


def _fact(ps):
    # setters write `factID`; conditions read `factId`. Both spellings are in the files.
    return ps.get("factId") or ps.get("factID") or ""


def build_index():
    """One pass over every phase file: default-dialogue hooks, the loops that play them, and setters.

    Only files that name a default scene or a `_dd_` fact are parsed, which keeps the pass to the
    few hundred files that matter. The setters of gate facts with other names are looked up after.
    """
    hooks, players, setters = [], [], {}
    for p in _phase_files():
        raw = p.read_bytes()
        if b"_default" not in raw and b"_dd_" not in raw:
            continue
        try:
            g = questgraph.G(p)
        except Exception:
            continue
        rel = str(p.relative_to(REDKIT_R4))
        for e in g.p["exports"]:
            cls, i = e["className"], e["index"]
            if cls not in (HOOK, PLAYER, dw.FACT_CLASS):
                continue
            ps = dw.props(g, i)
            if cls == dw.FACT_CLASS:
                fact = _fact(ps)
                if "_dd_" in fact:
                    setters.setdefault(fact, []).append({"file": rel, "block": i, "value": ps.get("value"),
                                                         "comment": ps.get("comment") or ""})
                continue
            scene, target = dw._ref(ps.get("scene")), dw._ref(ps.get("targetScene"))
            if cls == HOOK and DEFAULT_SCENE.search(target):
                hooks.append({"file": rel, "block": i, "comment": ps.get("comment") or "",
                              "scene": scene, "target_scene": target})
            elif cls == PLAYER and DEFAULT_SCENE.search(scene):
                players.append({"file": rel, "block": i, "scene": scene,
                                "gates": dw.dialogue_gates(g, i)})
    for row in players:
        for gate in row["gates"]:
            if gate["kind"] == "fact" and gate["name"] not in setters:
                setters[gate["name"]] = [{"file": s["file"], "block": s["block"], "value": s["value"],
                                          "comment": s["comment"]} for s in dw.fact_setters(gate["name"], limit=50)]
    doc = {"note": "Built by tools/default_dialogues.py index from the REDkit quest phases. Derived; regenerate, do not edit.",
           "hooks": hooks, "players": players, "setters": setters}
    INDEX.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc


def load_index():
    if not INDEX.exists():
        return build_index()
    return json.loads(INDEX.read_text(encoding="utf-8"))


def own_map(quest_index):
    """phase file (lower case) -> the quest stems whose journal runs it; the shared fixup phase is left out."""
    own = {}
    for stem, q in quest_index["quests"].items():
        for p in q.get("phases") or []:
            f = (p.get("file") or "").lower()
            if f and "bugfixing_phase" not in f:
                own.setdefault(f, []).append(stem)
    return own


def owners(rel, own):
    """The quests that run a phase file. A sub-phase under `quest_files\\<name>\\phases\\` is not in the
    quest index; it runs inside `<name>.w2phase` next to that folder, so it belongs to that file's quests."""
    key = rel.lower()
    if key in own:
        return sorted(own[key])
    m = re.match(r"(.*)\\quest_files\\([^\\]+)\\", key)
    if m:
        main = f"{m.group(1)}\\{m.group(2)}.w2phase"
        if main in own:
            return sorted(own[main])
    return []


def story_order():
    """main-story quest stem -> its position in the route's Main section (the order the story runs)."""
    route = json.loads(ROUTE.read_text(encoding="utf-8"))
    pos = {}
    for n in route["nodes"]:
        if n.get("section") != "Main":
            continue
        for f in n.get("files") or []:
            for stem in re.split(r"[|#]", f)[:1]:
                pos.setdefault(stem.lower(), len(pos))
    return pos


def _placed(rows, own, order):
    """Setter rows with their owning quests and the earliest main-story position among them."""
    out = []
    for s in rows:
        who = owners(s["file"], own)
        at = [order[q] for q in who if q in order]
        out.append({**s, "owners": who, "story_pos": min(at) if at else None})
    return out


def _gate_split(player):
    stop = sorted({g["name"] for g in player["gates"] if g["kind"] == "fact" and "stop" in g["name"]})
    start = sorted({g["name"] for g in player["gates"] if g["kind"] == "fact" and "start" in g["name"]})
    return stop, start


def scan(quest_index, index=None):
    """One row per default-dialogue hook: which quest needs it, and where the story switches it off for good.

    A stop setter is final when it sits in a main-story quest and every start setter of the same loop
    sits earlier in the main story. A start setter owned by a side quest, or by no quest the index
    knows, may run later; such a row is reported as `reopen_unknown` rather than called final.
    """
    index = index or load_index()
    own, order = own_map(quest_index), story_order()
    by_scene = {}
    for pl in index["players"]:
        by_scene.setdefault(pl["scene"].lower(), []).append(pl)
    reviewed = {}
    if CUTOFFS.exists():
        for w in json.loads(CUTOFFS.read_text(encoding="utf-8")).get("windows", []):
            if w.get("mechanism") == "dialogue_off":
                for a in w.get("affects") or []:
                    reviewed.setdefault(a.lower(), []).append(w["id"])
    rows = []
    for h in index["hooks"]:
        players = by_scene.get(h["target_scene"].lower(), [])
        stop_f, start_f = set(), set()
        for pl in players:
            s, t = _gate_split(pl)
            stop_f.update(s)
            start_f.update(t)
        stops = _placed([dict(r, fact=f) for f in sorted(stop_f) for r in index["setters"].get(f, [])], own, order)
        starts = _placed([dict(r, fact=f) for f in sorted(start_f) for r in index["setters"].get(f, [])], own, order)
        reopen_unknown = [s for s in starts if s["story_pos"] is None]
        last_start = max([s["story_pos"] for s in starts if s["story_pos"] is not None] or [-1])
        after = [s for s in stops if s["story_pos"] is not None and s["story_pos"] > last_start]
        # a start setter the main story cannot place may run after any stop, so nothing is final then
        final = [] if reopen_unknown else after
        quests = owners(h["file"], own)
        rows.append({
            **h, "quests": quests, "npc": Path(h["target_scene"]).stem.removesuffix("_default"),
            "players": [{"file": p["file"], "block": p["block"]} for p in players],
            "stop_facts": sorted(stop_f), "start_facts": sorted(start_f),
            "stop_setters": stops, "start_setters": starts,
            "final_stops": final, "unplaced_stops": after if reopen_unknown else [],
            "reopen_unknown": reopen_unknown,
            "reviewed": sorted({w for q in quests for w in reviewed.get(q, [])}),
        })
    return rows


def window_evidence(quest_index, w, index=None):
    """Check a reviewed `dialogue_off` window against the files. Returns (error, evidence).

    The window must name the hook (`dialogue`: file and block), the stop fact (`close_gate`) and the
    objective that needs the NPC (`step`, "<stem>#<journal entry name>"). It is accepted only when
      - the hook is a context dialogue on an `<npc>_default.w2scene`, in one of the affected quests,
      - a loop that plays that scene is gated by `close_gate`,
      - the closing quest sets `close_gate` in its own phase files, and
      - every setter of the loop's start fact sits earlier in the main story than the closer,
    so the option cannot come back after the window closes.
    """
    index = index or load_index()
    d = w.get("dialogue") or {}
    rel, block = d.get("file"), d.get("block")
    if not rel or not block:
        return "a dialogue_off window must name the hook's phase file and block", {}
    hook = next((h for h in index["hooks"] if h["file"].lower() == rel.lower() and h["block"] == block), None)
    if not hook:
        return f"{rel}#{block} is not a context dialogue on an NPC's default scene", {}
    own, order = own_map(quest_index), story_order()
    affects = [a.lower() for a in w.get("affects") or []]
    if not set(owners(rel, own)) & set(affects):
        return f"{rel} is not a phase file of {', '.join(affects)}", {}
    step = w.get("step") or ""
    stem, _, entry = step.partition("#")
    if stem.lower() not in affects or not entry:
        return "a dialogue_off window must name the objective that needs the NPC as <affected stem>#<entry>", {}
    names = {o.get("name") for o in (quest_index["quests"].get(stem.lower()) or {}).get("objectives") or []}
    if entry not in names:
        return f"{entry!r} is not an objective of {stem}", {}
    row = next((r for r in scan(quest_index, index) if r["file"] == hook["file"] and r["block"] == block), None)
    gate = w.get("close_gate") or ""
    if not row["players"]:
        return f"nothing plays {hook['target_scene']}, so the hook has no dialogue to hang on", {}
    if gate not in row["stop_facts"]:
        return (f"the loop that plays {Path(hook['target_scene']).name} is not stopped by {gate}; "
                f"it stops on {', '.join(row['stop_facts']) or 'nothing'}"), {}
    closer = (w.get("closer") or "").lower()
    by_closer = [s for s in row["stop_setters"] if s["fact"] == gate and closer in s["owners"]]
    if not by_closer:
        return f"{closer} never sets {gate} in its own phase files", {}
    cpos = order.get(closer)
    if cpos is None:
        return f"{closer} is not a main-story quest, so nothing says it comes after the start setters", {}
    late = [s for s in row["start_setters"] if s["story_pos"] is None or s["story_pos"] >= cpos]
    if late:
        s = late[0]
        return (f"{s['fact']} is set again in {s['file']}#{s['block']} ({', '.join(s['owners']) or 'no known quest'}), "
                f"which is not earlier than {closer}; the option may come back"), {}
    return "", {"hook": hook, "players": row["players"], "close_setters": by_closer,
                "start_setters": row["start_setters"]}


def check():
    quest_index = json.loads((HERE / "quest_index.json").read_text(encoding="utf-8"))
    data = json.loads(WINDOWS.read_text(encoding="utf-8"))
    bad = 0
    for w in data.get("windows", []):
        if w.get("mechanism") != "dialogue_off":
            continue
        err, ev = window_evidence(quest_index, w)
        if err:
            bad += 1
            print(f"FAIL {w['id']}: {err}")
        else:
            print(f"ok   {w['id']}: {ev['hook']['file']}#{ev['hook']['block']} -> "
                  f"{', '.join(f'{s['file']}#{s['block']}' for s in ev['close_setters'])}")
    return 1 if bad else 0


def report_md(rows, quest_index):
    def title(stem):
        return (quest_index["quests"].get(stem) or {}).get("base_name") or stem

    def setter(s):
        return f"`{s['file']}`#{s['block']} ({', '.join(s['owners']) or 'no quest'})"

    final = [r for r in rows if r["final_stops"]]
    lines = [
        "# Default-dialogue cutoffs",
        "",
        "Generated by `py tools/default_dialogues.py scan --md tools/default_dialogue_report.md`. Each row is a quest",
        "step that hangs on an NPC's everyday chat (`CQuestContextDialogBlock` on `<npc>_default.w2scene`). The chat",
        "plays only between the NPC's `_dd_start` and `_dd_stop` facts. A stop is **final** when a main-story quest sets",
        "it and every start setter of the same loop is earlier in the main story. After a final stop the step cannot be",
        "done, whatever the journal says. `reviewed` names the window in `tools/cutoff_windows.json` that covers it.",
        "",
        f"{len(rows)} hooks; {len(final)} with a final stop.",
        "",
        "| quest | hook | NPC | final stop | start setters | reopen unknown | reviewed |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in sorted(rows, key=lambda r: (not r["final_stops"], not r["unplaced_stops"], r["npc"], r["file"], r["block"])):
        q = ", ".join(f"{title(s)} (`{s}`)" for s in r["quests"]) or "(no quest)"
        fin = "<br>".join(setter(s) for s in r["final_stops"]) or (
            "not final, a start setter is unplaced: " + "<br>".join(setter(s) for s in r["unplaced_stops"])
            if r["unplaced_stops"] else "-")
        st = "<br>".join(setter(s) for s in r["start_setters"]) or "-"
        ru = "<br>".join(setter(s) for s in r["reopen_unknown"]) or "-"
        lines.append(f"| {q} | `{Path(r['file']).name}`#{r['block']} {r['comment']!r} | {r['npc']} | {fin} | {st} | {ru} | "
                     f"{', '.join(r['reviewed']) or '-'} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("index")
    sc = sub.add_parser("scan")
    sc.add_argument("--json")
    sc.add_argument("--md")
    sub.add_parser("check")
    args = ap.parse_args()
    if args.cmd == "index":
        doc = build_index()
        print(f"wrote {INDEX.name}: {len(doc['hooks'])} hooks, {len(doc['players'])} default-dialogue loops, "
              f"{len(doc['setters'])} facts")
        return 0
    if args.cmd == "check":
        return check()
    quest_index = json.loads((HERE / "quest_index.json").read_text(encoding="utf-8"))
    rows = scan(quest_index)
    for r in rows:
        mark = "FINAL" if r["final_stops"] else "     "
        fin = ", ".join(f"{s['fact']}@{'/'.join(s['owners']) or Path(s['file']).name}" for s in r["final_stops"])
        print(f"{mark} {'/'.join(r['quests']) or '(none)':34s} #{r['block']:<5} {r['npc']:14s} {fin} "
              f"{'reviewed: ' + ','.join(r['reviewed']) if r['reviewed'] else ''}")
    if args.json:
        Path(args.json).write_text(json.dumps({"rows": rows}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.md:
        Path(args.md).write_text(report_md(rows, quest_index), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
