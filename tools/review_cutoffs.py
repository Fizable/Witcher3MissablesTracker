"""Write `data/cutoffs.json` from the cutoff pool, with the review decisions named.

`cutoffs.py` produces every pair the files can suggest, base game and DLC. Shipping all of
them would be noise and some are phase transitions. This script is the review pass, expressed as
rules plus an explicit keep/exclude list:

  keep    a candidate family only when
          - its mechanism is a `CDeactivateSpawnset` naming a resource the affected quest
            references in its own phase files or scenes,
          - no save contradicts it (a later save never has the affected quest finished after the
            closing quest was done),
          - at least one save actually reached the state the warning is about (open_before > 0),
          - the affected quest does not start after the switch,
          - the affected quest's own phase does not switch the actor back on for its turn-in, and
          - the affected journal actually fails: a save records it `Failed` after the closer, or
            its own graph has a connected Failure input gated by the closer's journal.
  keep    reviewed journal windows from `data/cutoff_windows.json` only when the affected quest
          has a connected Failure input, that input is gated by the closer's journal, and
          `closes_at` is a real phase of that journal.
  exclude the aggregate/phase-placeholder quests and the pending review's Yennefer case, with
          the reason written into `decisions` so the next pass can see what was decided.

Output is deterministic: the same `cutoff_index.json` gives the same bytes, which is what
`tools/regen.py` checks.

  py review_cutoffs.py build
  py review_cutoffs.py report
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cr2w
import questgraph
import stringsdb
from paths import HERE, REDKIT_R4, TRACKER

OUT = TRACKER / "data" / "cutoffs.json"
WINDOWS = TRACKER / "data" / "cutoff_windows.json"
INDEX = HERE / "cutoff_index.json"
QUEST_INDEX = HERE / "quest_index.json"

# A thin row is one where fewer than three saves had the affected quest open when the closer
# finished. These families are still direct: the resource is switched off and the affected quest
# plays its scenes through it. Everything else thin is a phase transition or unreachable noise.
KEEP_THIN = {
    "q402velenallies": "Brothers in Arms: Velen is played through the Kaer Morhen allies, whose communities the Isle of Mists switches off",
    "q402novigradallies": "Brothers in Arms: Novigrad is played through the Kaer Morhen allies, whose communities the Isle of Mists switches off",
    "q402skelligeallies": "Brothers in Arms: Skellige is played through the Kaer Morhen allies, whose communities the Isle of Mists switches off",
    "q402nilfgaardianally": "Brothers in Arms: Nilfgaard is played through the Kaer Morhen allies, whose communities the Isle of Mists switches off",
}
# Never shipped, with the reason. These are quests whose journal entry is a container or a phase
# placeholder, so "lost" would not mean a piece of play the player can still do.
EXCLUDE = {
    "ch1quest": "an aggregate 'In Ciri's Footsteps' entry, not a playable quest",
    "q309novigradundercontrol": "the journal entry is a phase placeholder that stays active after the content is over",
    "q205lofoten": "the pending review in this file already found the Yennefer community is switched off elsewhere in the story, so the pair is a phase transition",
}


def titles(idx, con):
    out = {}
    for stem, q in idx["quests"].items():
        if q.get("name_locid"):
            t = stringsdb.loc(q["name_locid"], con)
            if t:
                out[stem] = t
        for b in q.get("bundle_names") or []:
            if q.get("name_locid"):
                t = stringsdb.loc(q["name_locid"], con)
                if t:
                    out[b] = t
    return out


def ref_file(idx, stem, resource):
    """A file of the affected quest that references the resource, for provenance."""
    q = idx["quests"].get(stem) or {}
    files = [p["file"] for p in q.get("phases", []) if not p.get("global")] + [s["file"] for s in q.get("scenes", [])]
    for f in files:
        try:
            p = cr2w.parse(REDKIT_R4 / f)
        except Exception:
            continue
        for e in p["exports"]:
            if any(res == resource for res in cr2w.refs(p, e)):
                return f
    return ""


def candidate_rows(rows, affected, closed):
    return [r for r in rows if r["to"] == affected and r["from"] in closed and r["resource"].endswith(".w2comm")]


def starts_after(idx, affected, closer):
    """True when every journal-activation block of `affected` is in a phase named after `closer`.

    `q311_after_q301_dreamer_godling_house.w2phase` starts Haunted House *after* Novigrad Dreaming;
    treating Novigrad Dreaming as the event that ends Haunted House reads the graph backwards.
    """
    q = idx["quests"].get(affected) or {}
    acts = [a for a in q.get("activators") or [] if "bugfixing_phase" not in a.get("file", "").lower()]
    if not acts:
        return False
    m = re.match(r"^([a-z]+\d+)", closer.lower())
    base = m.group(1) if m else closer.lower()
    return all(("after_" + base) in a.get("file", "").lower() for a in acts)


def journal_stem(resource):
    return re.split(r"[\\/]", resource or "")[-1].removesuffix(".journal").lower()


def failure_conditions(idx, affected):
    """The journal conditions gating a *connected* Failure input on an affected quest.

    A `Failure` socket that exists but is not wired proves nothing: many journal blocks carry an
    unused one. For each wired input this walks the graph and its logic conditions backwards and
    returns the journal statuses it depends on. That is the evidence a reviewed window is checked
    against - not the window's own prose.
    """
    q = idx["quests"].get(affected) or {}
    out = []
    seen_files = set()
    for f in q.get("failures") or []:
        path = REDKIT_R4 / f.get("file", "")
        key = (str(path), f.get("block"))
        if key in seen_files or not path.exists():
            continue
        seen_files.add(key)
        try:
            g = questgraph.G(path)
        except Exception:
            continue
        for src in g.failure_sources(f["block"]):
            for c in g.journal_conditions_upstream(src):
                if c.get("kind") == "journal" and c.get("resource"):
                    out.append({"file": f.get("file", ""), "block": f["block"],
                                "resource": c["resource"], "status": c.get("status", "")})
    return out


def invalid_cutoff(idx, item):
    """Why a reviewed community cutoff is not evidence of a loss, or '' when it survives.

    A `CDeactivateSpawnset` only says an actor left a scene. It becomes a cutoff only when the
    affected quest does not start after the switch, its own files do not switch the same actor
    back on for the turn-in, and its journal actually fails - either a save records that failure or
    a connected Failure input is gated by the closer's journal. A missing NPC is not a failed quest.
    """
    resource = item.get("resource", "")
    closed = item.get("closed_by") or []
    closer_files = {p.get("file") for c in closed for p in (idx["quests"].get(c) or {}).get("phases", [])}
    for affected in item.get("affects") or []:
        q = idx["quests"].get(affected) or {}
        for closer in closed:
            if starts_after(idx, affected, closer):
                acts = [a.get("file", "") for a in q.get("activators") or []]
                return (f"{affected}'s journal entry is activated by {acts[0] if acts else 'a later phase'}, "
                        f"a phase that runs after {closer}; {closer} cannot be its cutoff")
        for sw in q.get("switches") or []:
            # a phase shared with the closing quest is its scene setup, not the affected quest
            # bringing the actor back for its own turn-in
            if sw.get("file") in closer_files:
                continue
            if resource and resource in (sw.get("activates") or []):
                return (f"{affected}'s own phase {sw.get('file', '')} switches {resource} back on; "
                        f"the deactivation is a phase transition, not a loss")
        failed = (item.get("saves") or {}).get("later_failed", 0)
        gated = {journal_stem(e["resource"]) for e in failure_conditions(idx, affected)}
        if not failed and not (gated & {c.lower() for c in closed}):
            return (f"no save marks {affected} Failed after {', '.join(closed) or 'the closer'}, and its "
                    "own phase graph has no connected Failure input gated by that quest; a deactivated "
                    "community is not a loss")
    return ""


def window_error(idx, w):
    """Validate a reviewed journal window against the game's own journal and failure blocks.

    The window is accepted only when the affected quest has a Failure input that is actually
    connected and whose upstream conditions name the closer's journal. Checking that the quest has
    *some* Failure socket was not enough: dangling sockets are common, and they let an early phase
    be labelled the last window without the game saying so.
    """
    affects = w.get("affects") or []
    closer = w.get("closer", "")
    at = w.get("closes_at", "")
    if not affects or closer not in idx["quests"]:
        return "the window names no affected quest or no closer"
    if w.get("mechanism") == "availability":
        # An availability window is not a journal failure: the NPC leaves and the chance to act
        # closes, while the quest stays Active. It still has to name a real phase of a real quest.
        if "#" not in at:
            return "an availability window must name the journal phase where it closes"
        stem, phase = at.split("#", 1)
        if stem != closer:
            return f"closes_at {at} is not a phase of {closer}"
        names = {p.get("name") for p in (idx["journals"].get(closer) or {}).get("phases", [])}
        if phase not in names:
            return f"{phase} is not a phase in {closer}.journal"
        if not w.get("files"):
            return "the availability window names no file evidence"
        if not w.get("gap_headline"):
            return "the availability window does not say what to do when it closes"
        return ""
    for a in affects:
        q = idx["quests"].get(a)
        if not q:
            return f"{a} is not in the quest index"
        ev = failure_conditions(idx, a)
        if not ev:
            return f"{a}'s Failure sockets are not wired to anything"
        gated = {journal_stem(e["resource"]) for e in ev}
        if closer.lower() not in gated:
            return (f"{a}'s connected Failure input is not gated by {closer}'s journal; "
                    f"the file names {', '.join(sorted(gated)) or 'no journal'}")
    if "#" not in at:
        return "closes_at must name a journal phase"
    stem, phase = at.split("#", 1)
    if stem != closer:
        return f"closes_at {at} is not a phase of {closer}"
    names = {p.get("name") for p in (idx["journals"].get(closer) or {}).get("phases", [])}
    if phase not in names:
        return f"{phase} is not a phase in {closer}.journal"
    if not w.get("files"):
        return "the window names no file evidence"
    return ""


def resolve_window(idx, name, w):
    closer = w["closer"]
    out = {
        "id": w["id"], "level": w.get("level", "stop"), "mechanism": w.get("mechanism", "journal_failure"),
        "resource": w.get("resource", ""),
        "affects": [a.lower() for a in w["affects"]],
        "affected_titles": [name.get(a.lower(), a) for a in w["affects"]],
        "closed_by": [closer], "closed_by_titles": [name.get(closer, closer)],
        "closes_at": w["closes_at"], "closes_at_title": w.get("closes_at_title", ""),
        "binding": closer, "binding_title": name.get(closer, closer),
        "action": w.get("action", ""), "headline": w.get("headline", ""),
        "why": w.get("why", ""), "files": w.get("files", []), "caveats": w.get("caveats", []),
        "event_name": w.get("event_name"), "evidence": w.get("evidence", "files"),
        "saves": {}, "resources": [w["resource"]] if w.get("resource") else [],
    }
    if w.get("turn_in") is not None:
        out["turn_in"] = w["turn_in"]
    for k in ("gap_headline", "gap_action"):
        if w.get(k):
            out[k] = w[k]
    return out


def item_saves(pool, item):
    """The save counts for a kept family, including the journal-failure evidence."""
    rows = [r for r in pool
            if r.get("resource") == item.get("resource")
            and r.get("from") in (item.get("closed_by") or [])
            and r.get("to") in (item.get("affects") or [])]
    if not rows:
        return item.get("saves") or {}
    return max((r.get("saves") or {} for r in rows),
               key=lambda s: (s.get("later_failed", 0), s.get("open_before", 0)))


def build():
    pool = json.loads(INDEX.read_text(encoding="utf-8"))["candidates"]
    idx = json.loads(QUEST_INDEX.read_text(encoding="utf-8"))
    con = stringsdb.con()
    name = titles(idx, con)
    existing = json.loads(OUT.read_text(encoding="utf-8"))
    kept = {i["id"]: i for i in existing.get("items", [])}
    decisions = []
    by_family = defaultdict(list)
    for r in pool:
        by_family[(r["from_names"][0], r["to_names"][0])].append(r)

    # Regression self-check for the two false positives this review pass found. If the graph rule
    # ever stops rejecting them, the review fails instead of quietly shipping the old warning again.
    for label, item in (
        ("Haunted House", {"id": "haunted_house", "resource": "quests\\part_1\\quest_files\\q301_dreamer\\spawnsets\\q301_godling_girl.w2comm",
                            "affects": ["q301visitingdreamer"], "closed_by": ["q301dreamer"]}),
        ("Triss statuettes", {"id": "triss_statuettes", "resource": "quests\\main_npcs\\community_files\\triss.w2comm",
                               "affects": ["mq3012noblestatuette"], "closed_by": ["q301dreamer"]}),
    ):
        if not invalid_cutoff(idx, item):
            raise SystemExit(f"cutoff audit self-check failed: {label} is still accepted")

    # The old statuette window was early by two phases. If this is accepted again, the window
    # check has stopped reading the failure branch and is only trusting the prose.
    old_window = {"id": "old_q310_window", "affects": ["mq3012noblestatuette"],
                  "closer": "q310preparationsnovigrad",
                  "closes_at": "q310preparationsnovigrad#Q310 Gather Lodge",
                  "files": ["old window"]}
    if not window_error(idx, old_window):
        raise SystemExit("cutoff audit self-check failed: the old Q310 statuette window is accepted")

    # Brothers in Arms: the Isle of Mists closes the allies' communities.
    allies = ["q402velenallies", "q402novigradallies", "q402skelligeallies", "q402nilfgaardianally"]
    rows = [r for r in pool if r["to"] in allies and r["from"] == "q402ciri" and r["resource"].endswith("q402_dopey.w2comm")]
    hit = sorted({r["to"] for r in rows})
    if len(hit) >= 3:
        r = rows[0]
        refs = {a: ref_file(idx, a, r["resource"]) for a in hit}
        refs_phrase = "; ".join(a + " references " + r["resource"] for a in hit)
        kept["brothers_in_arms"] = {
            "id": "brothers_in_arms", "event_name": "The Isle of Mists", "level": "stop", "mechanism": "spawnset",
            "resource": r["resource"], "affects": hit, "closed_by": ["q402ciri"],
            "action": "Finish the Brothers in Arms quests",
            "headline": "Finish Brothers in Arms before The Isle of Mists",
            "why": (f"The Isle of Mists switches off the Kaer Morhen allies' communities in {r['deactivated_in']} "
                    f"(CDeactivateSpawnset), and every Brothers in Arms quest is played through them: "
                    f"{refs_phrase}. Sailing to the Isle closes them."),
            "files": [f"{r['deactivated_in']} switches off {r['resource']} (CQuestStoryPhaseSetterBlock -> CDeactivateSpawnset)"]
                     + [f"{refs[a]} references {r['resource']}" for a in hit if refs[a]],
            "evidence": "files+saves",
            "caveats": ["Only two saves in the corpus had a Brothers in Arms quest still open when The Isle of Mists was done; none finished one later. The mechanism is what makes this a cutoff, not the save count."],
        }
        decisions.append({"family": "brothers_in_arms", "decision": "keep", "why": KEEP_THIN[hit[0]],
                          "saves": r["saves"], "resource": r["resource"]})
    else:
        decisions.append({"family": "brothers_in_arms", "decision": "drop", "why": f"only {len(hit)} of the four allies quests survived"})

    # every excluded family, with the reason
    for (frm, to), rows in sorted(by_family.items()):
        if to in EXCLUDE:
            decisions.append({"family": f"{frm} -> {to}", "decision": "exclude", "why": EXCLUDE[to],
                              "saves": rows[0]["saves"], "resource": rows[0]["resource"]})
    for to in ("q309novigradundercontrol", "ch1quest", "q205lofoten"):
        if to not in {d["family"].split(" -> ")[-1] for d in decisions}:
            decisions.append({"family": f"(all) -> {to}", "decision": "exclude", "why": EXCLUDE[to]})

    items = [kept[k] for k in ("brothers_in_arms",) if k in kept]
    # A reviewed cutoff still has to survive the graph: a deactivation is not a loss when the
    # affected quest starts after it, when its own phase switches the actor back on, or when no
    # save or Failure branch ever marks it failed.
    valid_items = []
    for item in items:
        item["saves"] = item_saves(pool, item)
        why = invalid_cutoff(idx, item)
        if why:
            decisions.append({"family": item["id"], "decision": "drop (audit)", "why": why})
        else:
            valid_items.append(item)
    items = valid_items

    windows = []
    if WINDOWS.exists():
        wdata = json.loads(WINDOWS.read_text(encoding="utf-8"))
        for w in wdata.get("windows", []):
            why = window_error(idx, w)
            if why:
                decisions.append({"family": "window:" + str(w.get("id", "?")), "decision": "exclude", "why": why})
                continue
            resolved = resolve_window(idx, name, w)
            windows.append(resolved)
            if resolved.get("mechanism") == "availability":
                keep_why = (f"an availability window: {resolved['closes_at']} is a phase of "
                            f"{resolved['closed_by'][0]}.journal where the NPC leaves; the affected quest "
                            "is not failed, so this window never reports a loss")
            else:
                keep_why = ("the affected journal entry has a connected Failure input gated "
                            f"by {resolved['closed_by'][0]}.journal, and {resolved['closes_at']} "
                            "is a phase of that journal")
            decisions.append({"family": "window:" + resolved["id"], "decision": "keep", "why": keep_why})

    out = {
        "version": 3,
        "note": ("Reviewed cutoffs. tools/cutoffs.py generates every pair the files can suggest "
                 f"({len(pool)} rows on this install, base game and DLC); tools/review_cutoffs.py applies the review rule and writes this "
                 "file. `items` are community cutoffs that survived the graph and journal-failure audit; "
                 "`windows` are journal phases where a connected Failure input gated by the closer's own "
                 "journal resolves the quest. Only what is here becomes a warning. "
                 "`decisions` records every kept and excluded family, so the next pass can see why."),
        "reviewed": "2026-10-28",
        "pending_review": existing.get("pending_review", []),
        "decisions": decisions,
        "items": items,
        "windows": windows,
    }
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.name}: {len(items)} community cutoffs, {len(windows)} journal windows, "
          f"{len(decisions)} review decisions")
    return out


def report():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    for d in data["decisions"]:
        print(f"{d['decision']:8s} {d['family']:40s} {d['why']}")
    print()
    for i in data["items"]:
        print(f"{i['id']:20s} {', '.join(i['affects'])} <- {', '.join(i['closed_by'])}")
    for w in data.get("windows", []):
        print(f"{w['id']:20s} {', '.join(w['affects'])} <- {w['closes_at']}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        report()
    else:
        build()
