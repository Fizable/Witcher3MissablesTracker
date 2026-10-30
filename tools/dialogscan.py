"""Audit every quest's dialogue options for the statuette shape: a turn-in gated by someone else.

The statuettes were not a one-off rule, they were a *shape*: the quest's own journal entry is what
the option reacts to, but a fact set by another quest decides whether the option is offered at
all. `dialog_gates` in `dialog_windows.py` reads one block's branches with True/False polarity;
this walks every `.w2phase` in the install that carries a context or interaction dialogue block,
records the block's gates, records every fact setter in the same pass, and joins the two.

Two classes come out of it, and they are not the same thing:

  turn-in   the block reacts to its own quest's journal status *and* a fact another quest sets.
            These are the statuette shape: an option that comes and goes with the story.
  other     the block is gated by a foreign fact but never by its own quest's journal. In practice
            these are the Gwent opponent tables, fistfights and hero-card cameos - a scene that is
            offered when someone is in town, not a quest being turned in.

The community side of the same problem (an NPC switched out of their phase) is audited separately
by `cutoffs.py` and `review_cutoffs.py`; this tool answers only the dialogue-option half.

  py dialogscan.py build     read the files -> tools/dialog_gate_index.json (git-ignored)
  py dialogscan.py report    join the index with the quest index and data/cutoffs.json
  py dialogscan.py show <quest stem or journal name>

The report is a triage list, not a verdict: each row names the setting file and block so the next
pass can decide, the same way `review_cutoffs.py` decides a window. Read-only.
"""
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cr2w
import dialog_windows as dw
import questgraph
from paths import HERE, QUEST_ROOT, REDKIT_R4, TRACKER

INDEX = HERE / "dialog_gate_index.json"
QUEST_INDEX = HERE / "quest_index.json"
CUTOFFS = TRACKER / "data" / "cutoffs.json"
REPORT = HERE / "dialog_gate_report.md"
DIALOG = ("CQuestContextDialogBlock", "CQuestInteractionDialogBlock")
SETTER = "CQuestFactsDBChangingBlock"


def build():
    """One pass over every dialogue-bearing phase: blocks, gates and the fact setters they need."""
    quest_index = json.loads(QUEST_INDEX.read_text(encoding="utf-8"))
    file_quests = collections.defaultdict(set)
    for stem, q in quest_index["quests"].items():
        for p in q.get("phases") or []:
            if p.get("file") and not p.get("global"):
                file_quests[p["file"]].add(stem)

    rows, setters = [], collections.defaultdict(list)
    parsed = 0
    for path in sorted(QUEST_ROOT.rglob("*.w2phase")):
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"CQuestContextDialogBlock" not in raw and b"CQuestInteractionDialogBlock" not in raw \
                and b"CQuestFactsDBChangingBlock" not in raw:
            continue
        rel = str(path.relative_to(REDKIT_R4))
        try:
            g = questgraph.G(path)
        except Exception:
            continue
        parsed += 1
        for e in g.p["exports"]:
            cls = e["className"]
            ps = dw.props(g, e["index"])
            if cls == SETTER:
                fact = ps.get("factId") or ps.get("factID")
                if fact:
                    setters[fact].append({"file": rel, "block": e["index"],
                                          "value": ps.get("value"),
                                          "comment": ps.get("comment") or ""})
                continue
            if cls not in DIALOG:
                continue
            rows.append({
                "file": rel, "block": e["index"], "class": cls,
                "comment": ps.get("comment") or "",
                "scene": dw._ref(ps.get("scene")),
                "target_scene": dw._ref(ps.get("targetScene")),
                "quests": sorted(file_quests.get(rel, [])),
                "gates": dw.dialogue_gates(g, e["index"]),
            })

    doc = {
        "note": ("Every context/interaction dialogue block in the install with its branch gates, "
                 "and every fact setter in the same files. Built by tools/dialogscan.py; joined "
                 "against tools/quest_index.json by its report."),
        "files_parsed": parsed,
        "blocks": rows,
        "setters": {k: v for k, v in sorted(setters.items())},
    }
    INDEX.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"parsed {parsed} dialogue-bearing phase files: {len(rows)} option blocks, "
          f"{len(setters)} facts with a setter")
    return doc


def _own_names(quest_index, stems):
    """A quest's own journal names, by REDkit stem and by bundle name."""
    names = set()
    bundle_of = collections.defaultdict(set)
    for b, s in (quest_index.get("alias") or {}).items():
        bundle_of[s.lower()].add(b.lower())
    for s in stems:
        names.add(s.lower())
        names |= bundle_of.get(s.lower(), set())
    return names


def analyse(doc, quest_index):
    """Split the option blocks into turn-ins gated by another quest and everything else."""
    file_owners = collections.defaultdict(set)
    for stem, q in quest_index["quests"].items():
        for p in q.get("phases") or []:
            if p.get("file"):
                file_owners[p["file"]].add(stem)
    setter_quest = {fact: sorted({s for r in rows for s in file_owners.get(r["file"], ())})
                    for fact, rows in doc["setters"].items()}

    cut = json.loads(CUTOFFS.read_text(encoding="utf-8")) if CUTOFFS.exists() else {}
    covered = set()
    for item in (cut.get("items") or []) + (cut.get("windows") or []):
        covered |= {a.lower() for a in item.get("affects") or []}

    turn_in, other = [], []
    for b in doc["blocks"]:
        stems = b.get("quests") or []
        if not stems:
            continue
        own = _own_names(quest_index, stems)
        gates = b.get("gates") or []
        foreign_facts = []
        for g in gates:
            if g["kind"] != "fact":
                continue
            owners = setter_quest.get(g["name"], [])
            if owners and not (set(owners) & set(stems)):
                foreign_facts.append({"fact": g["name"], "state": g["state"], "via": g["via"],
                                      "setters": doc["setters"].get(g["name"], [])[:3],
                                      "owner_quests": owners})
        foreign_journal = [{"quest": g["name"], "state": g["state"], "via": g["via"]}
                           for g in gates
                           if g["kind"] == "journal" and g["name"] not in own
                           and g["state"] in ("JS_Active", "JS_Success", "JS_Failed")]
        if not foreign_facts and not foreign_journal:
            continue
        row = {k: b[k] for k in ("file", "block", "class", "comment", "scene", "target_scene")}
        row.update({
            "quests": stems,
            "own_journal": [g for g in gates if g["kind"] == "journal" and g["name"] in own],
            "foreign_facts": foreign_facts,
            "foreign_journal": foreign_journal,
            "modelled": sorted(covered & (set(own) | set(stems))),
        })
        (turn_in if row["own_journal"] else other).append(row)
    return turn_in, other


def report():
    doc = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else build()
    quest_index = json.loads(QUEST_INDEX.read_text(encoding="utf-8"))
    turn_in, other = analyse(doc, quest_index)

    lines = ["# Dialogue options gated by another quest", "",
             f"{doc['files_parsed']} dialogue-bearing phase files, {len(doc['blocks'])} option blocks:",
             f"**{len(turn_in)} turn-in blocks** react to their own quest's journal *and* a fact or",
             f"journal another quest controls; **{len(other)} other blocks** are gated by a foreign",
             "fact without being a turn-in (Gwent tables, fistfights, hero-card cameos).", "",
             "A turn-in row is a candidate window, not a verdict: whether it is a deadline depends",
             "on what the fact means and whether anything fails the quest.", ""]

    lines.append("## Turn-ins whose option depends on another quest")
    lines.append("")
    by_quest = collections.OrderedDict()
    for r in turn_in:
        for stem in r["quests"]:
            by_quest.setdefault(stem, []).append(r)
    for stem, rs in sorted(by_quest.items()):
        lines.append(f"### {stem}")
        for r in rs:
            where = Path(r["target_scene"]).name if r["target_scene"] else Path(r["scene"]).name
            state = "modelled by the tracker" if r["modelled"] else "**not modelled**"
            lines.append(f"- `{Path(r['file']).name}#{r['block']}` {r['class']} on `{where}` - {state}")
            if r["own_journal"]:
                lines.append("  - own journal: " + ", ".join(
                    f"`{g['name']}` {g['state']}" for g in r["own_journal"]))
            for g in r["foreign_facts"]:
                setters = ", ".join(f"`{Path(s['file']).name}#{s['block']}`" for s in g["setters"]) or "no phase"
                owners = ", ".join(g["owner_quests"][:3]) or "no owning quest"
                lines.append(f"  - fact `{g['fact']}` {g['state']} - set by {setters} ({owners})")
            for g in r["foreign_journal"]:
                lines.append(f"  - journal `{g['quest']}` {g['state']}")
        lines.append("")

    lines.append("## Other foreign-fact options (checked, not turn-ins)")
    lines.append("")
    kinds = collections.Counter(Path(r["file"]).name.split("_")[0] for r in other)
    lines.append(f"{len(other)} blocks in {len({s for r in other for s in r['quests']})} quests, by file prefix: "
                 + ", ".join(f"`{k}` {n}" for k, n in kinds.most_common(10)) + ".")
    lines.append("")
    fact_seen = collections.Counter(g["fact"] for r in other for g in r["foreign_facts"])
    lines.append("Most common gate facts: " + ", ".join(f"`{f}` ({n})" for f, n in fact_seen.most_common(8)) + ".")
    lines.append("")
    lines.append("These are scenes offered when someone is in town, not quests being turned in. They")
    lines.append("would be worth a card only if the tracker ever told a player to talk to that NPC.")
    lines.append("")
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(turn_in)} turn-in blocks, {len(other)} other foreign-fact blocks -> {REPORT.name}")
    for stem, rs in sorted(by_quest.items()):
        print(f"  turn-in {stem:34s} {len(rs)} block(s) {'modelled' if any(r['modelled'] for r in rs) else 'NOT MODELLED'}")
    return turn_in, other


def show(needle):
    doc = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else build()
    quest_index = json.loads(QUEST_INDEX.read_text(encoding="utf-8"))
    needle = needle.lower()
    turn_in, other = analyse(doc, quest_index)
    shown = 0
    for r in turn_in + other:
        names = set(r["quests"])
        own = _own_names(quest_index, r["quests"])
        if needle not in names and not any(needle in n for n in own):
            continue
        shown += 1
        print(f"{r['file']} #{r['block']} {r['class']} {r['comment']!r}")
        for g in r["own_journal"]:
            print(f"    own journal {g['name']} {g['state']}")
        for g in r["foreign_facts"]:
            print(f"    needs fact {g['fact']} {g['state']} via {g['via']}")
            for s in g["setters"]:
                print(f"        set in {s['file']} #{s['block']} {s['comment']!r}")
        for g in r["foreign_journal"]:
            print(f"    needs {g['quest']} journal {g['state']} via {g['via']}")
    if not shown:
        print(f"no option block for {needle} is gated by another quest")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "build":
        build()
        sys.exit(0)
    if cmd == "show":
        show(sys.argv[2])
        sys.exit(0)
    report()
    sys.exit(0)
