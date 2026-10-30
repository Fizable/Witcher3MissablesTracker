"""What gates each Gwent opponent's option, straight from the hub dialogue blocks.

The Gwent hubs are not journal quests with a window of their own: every opponent is an extra
option hung on an NPC's default dialogue in `quests/generic_quests/card_minigame_all_hubs`.
That block's branch conditions are the game's own statement of when the player can be challenged,
which is exactly what `dialog_gates` reads. This tool turns those gates into a table:

    player          who the block is hung on, from the NPC dialogue scene it targets
    steps           the game's own Gwent objective that names them (route.json `cg...#Win...`)
    gates           each fact the option tests, with the branch state it expects, plus the phase
                    and quest that sets it
    ambiguous       true when the same fact is tested both set and unset on different branches.
                    Those gates are not a simple "wait for X": the option exists in more than one
                    story state, so they need a human decision before they become a card rule.
    cards           card ids whose non-deck source names the player (never opponent-deck rows:
                    an opponent deck is evidence of a deck, not of a reward)

Output: `data/gwent_players.json` (shipped, generated) and `tools/gwent_players_report.md`.
Read-only against the game; nothing here is a loss claim.

  py gwentplayers.py build
  py gwentplayers.py check
"""
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dialogscan
from paths import HERE, TRACKER

INDEX = HERE / "dialog_gate_index.json"
QUEST_INDEX = HERE / "quest_index.json"
ROUTE = TRACKER / "data" / "route.json"
CARDS = TRACKER / "data" / "gwent_cards.json"
OUT = TRACKER / "data" / "gwent_players.json"
REPORT = HERE / "gwent_players_report.md"

HUBS = "card_minigame_all_hubs"
DECK_ONLY = {"deck_definition", "opponent_deck"}
# the NPC dialogue scene -> the name the game uses in its own Gwent objective
PLAYER = {
    "cg300_03_stjepan": "stjepan",
    "cg100_04_crossroads_innkeeper": "crossroads innkeeper",
    "cg300_04_olivier": "olivier",
    "cg300_02_zoltan": "zoltan",
    "cg300_08_roche": "roche",
    "cg100_06_talar": "thaler",
    "cg300_05_lambert": "lambert",
}


def _state(row):
    """The branch state of one gate, in the words the card gate uses (`set` / `unset`)."""
    raw = (row.get("state") or "").strip()
    if row.get("kind") == "journal":
        return raw
    if raw in ("set", "unset"):
        return raw
    if raw.endswith(" None"):
        return "unset"
    if raw.startswith("value ") and raw.endswith(" 1"):
        return "set"
    return raw or "set"


def _objectives():
    """(step, objective) rows from the route's own file strings: `cginnkeepers#Win ...`."""
    out = []
    if not ROUTE.exists():
        return out
    for node in json.loads(ROUTE.read_text(encoding="utf-8")).get("nodes", []):
        for f in node.get("files") or []:
            for part in f.split("|"):
                if "#" in part:
                    step, obj = part.split("#", 1)
                    if step.lower().startswith("cg") and obj.strip():
                        out.append({"step": step.lower(), "objective": obj.strip()})
    return out


def players(doc=None, quest_index=None):
    doc = doc if doc is not None else json.loads(INDEX.read_text(encoding="utf-8"))
    quest_index = quest_index or json.loads(QUEST_INDEX.read_text(encoding="utf-8"))
    file_owners = collections.defaultdict(set)
    for stem, q in quest_index["quests"].items():
        for p in q.get("phases") or []:
            if p.get("file"):
                file_owners[p["file"]].add(stem)
    setters = doc.get("setters") or {}
    objectives = _objectives()
    out = []
    for b in doc["blocks"]:
        if HUBS not in b["file"].replace("\\", "/"):
            continue
        scene = Path(b["scene"]).stem
        player = PLAYER.get(scene, scene)
        gates, seen = [], set()
        for g in b.get("gates") or []:
            if g["kind"] != "fact":
                continue
            state = _state(g)
            key = (g["name"], state)
            if key in seen:
                continue
            seen.add(key)
            rows = setters.get(g["name"]) or []
            gate = {
                "fact": g["name"], "state": state, "via": g["via"],
                "set_by": [{"file": r["file"], "block": r["block"], "comment": r.get("comment", ""),
                            "quests": sorted({s for r in [r] for s in file_owners.get(r["file"], ())})}
                           for r in rows[:3]],
                "setter_count": len(rows),
                "setter_note": "" if rows else "tested here but no phase sets it (scene or script)",
            }
            if g.get("logic"):
                gate["logic"] = g["logic"]
            gates.append(gate)
        states = collections.defaultdict(set)
        for g in gates:
            states[g["fact"]].add(g["state"])
        for g in gates:
            g["ambiguous"] = len(states[g["fact"]]) > 1
        steps = [o for o in objectives if player in o["objective"].lower()]
        out.append({
            "player": player,
            "file": b["file"], "block": b["block"], "class": b["class"],
            "comment": b["comment"], "scene": b["scene"], "target_scene": b["target_scene"],
            "gates": gates, "steps": steps,
            "gated": bool(gates),
            "simple": bool(gates) and not any(g["ambiguous"] for g in gates),
        })
    return out


def card_matches(rows, cards):
    """Cards whose non-deck source text or container names the player."""
    out = {}
    for row in rows:
        player = row["player"]
        hits = []
        for card in cards:
            for src in card.get("sources") or []:
                if src.get("kind") in DECK_ONLY:
                    continue
                text = " ".join(str(src.get(k) or "") for k in ("text", "container")).lower()
                if player.lower() in text:
                    hits.append({"id": card["id"], "kind": src.get("kind"), "text": src.get("text")})
                    break
        out[player] = hits
    return out


def build():
    doc = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else dialogscan.build()
    rows = players(doc)
    cards = json.loads(CARDS.read_text(encoding="utf-8")).get("cards", []) if CARDS.exists() else []
    matches = card_matches(rows, cards)
    for row in rows:
        row["cards"] = matches.get(row["player"], [])

    lines = ["# Gwent opponents and what gates their option", "",
             f"{len(rows)} hub dialogue blocks. `set` means the option needs the fact; `unset` means it",
             "needs the fact absent. A fact tested both ways is marked ambiguous: the option exists in",
             "more than one story state, so it is not a simple \"wait for X\" gate.", ""]
    for row in sorted(rows, key=lambda r: r["player"]):
        state = "not gated" if not row["gated"] else ("simple gate" if row["simple"] else "AMBIGUOUS")
        lines.append(f"## {row['player']} - {state}")
        lines.append(f"`{Path(row['file']).name}#{row['block']}` on "
                     f"`{Path(row['target_scene']).name}` (plays `{Path(row['scene']).name}`)")
        if row["steps"]:
            lines.append("- objective: " + "; ".join(f"`{s['step']}#{s['objective']}`" for s in row["steps"]))
        for g in row["gates"]:
            setters = ", ".join(f"`{Path(s['file']).name}#{s['block']}` ({', '.join(s['quests'][:2]) or '?'})"
                                for s in g["set_by"]) or g.get("setter_note") or "no setter found"
            marks = [m for m in ("or-gate" if g.get("logic") == "or" else "",
                                 "ambiguous" if g["ambiguous"] else "") if m]
            lines.append(f"- fact `{g['fact']}` **{g['state']}**"
                         + (f" ({', '.join(marks)})" if marks else "")
                         + f" - set by {setters}")
        if row["cards"]:
            lines.append("- cards naming this player: " + ", ".join(f"`{c['id']}`" for c in row["cards"]))
        lines.append("")

    doc_out = {
        "note": ("Gwent opponent availability, read from the hub context-dialogue blocks "
                 "(tools/dialogscan.py index) and joined to the route's own Gwent objectives and "
                 "the card source rows. This is availability evidence, not a loss claim: a card "
                 "window may use these facts as `opens.requires` (see card_dijkstra and "
                 "cg_baron_discovered), but an ambiguous gate needs a review decision first."),
        "players": sorted(rows, key=lambda r: r["player"]),
    }
    OUT.write_text(json.dumps(doc_out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT.name}: {len(rows)} players, "
          f"{sum(1 for r in rows if r['gated'])} gated, {sum(1 for r in rows if r['simple'])} simple")
    for row in sorted(rows, key=lambda r: r["player"]):
        gates = ", ".join(f"{g['fact']}={g['state']}" for g in row["gates"]) or "no gate"
        print(f"  {row['player']:22s} {'SIMPLE ' if row['simple'] else ('AMBIG  ' if row['gated'] else 'open   ')} {gates[:90]}")
    return doc_out


_FACTS = None


def known_facts():
    """Every fact name the game's own index knows, so a gate cannot name an invented fact."""
    global _FACTS
    if _FACTS is None:
        path = HERE / "fact_index.json"
        _FACTS = ({row.get("fact") for row in json.loads(path.read_text(encoding="utf-8"))
                   if isinstance(row, dict) and row.get("fact")} if path.exists() else set())
    return _FACTS


def check():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    doc = json.loads(INDEX.read_text(encoding="utf-8"))
    blocks = {(b["file"], b["block"]) for b in doc["blocks"]}
    quest_index = json.loads(QUEST_INDEX.read_text(encoding="utf-8"))
    route_ids = {n["id"].lower() for n in json.loads(ROUTE.read_text(encoding="utf-8")).get("nodes", [])}
    problems = []
    for row in data["players"]:
        if (row["file"], row["block"]) not in blocks:
            problems.append(f"{row['player']}: block {row['file']}#{row['block']} is not in the index")
        for g in row["gates"]:
            if not g["setter_count"] and g["fact"] not in known_facts():
                problems.append(f"{row['player']}: fact {g['fact']} has no setter phase and is not in "
                                "fact_index.json, so the gate names nothing this install can read")
            for s in g["set_by"]:
                for q in s["quests"]:
                    if q not in quest_index["quests"]:
                        problems.append(f"{row['player']}: setter quest {q} is not in the quest index")
        for s in row["steps"]:
            if s["step"] not in route_ids:
                problems.append(f"{row['player']}: objective step {s['step']} is not a route step")
        for c in row["cards"]:
            if c["kind"] in DECK_ONLY:
                problems.append(f"{row['player']}: card {c['id']} came from deck-only evidence")
    for p in problems:
        print("FAIL", p)
    print(f"{len(data['players'])} players checked, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "check":
        sys.exit(check())
    build()
    sys.exit(0)
