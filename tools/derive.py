"""Derive `data/derived.json`: what the app shows, worked out from the game's own files.

Inputs, all of them read-only:

  tools/quest_index.json    built by questindex.py: per-quest names, objectives, activators, facts,
                            scenes, dialogue choices, and what its story phases switch off
  tools/cutoff_index.json   built by cutoffs.py: cutoff candidates from the files, judged against
                            the order the saves were written
  tools/save_index.json     built by saveindex.py: the journal status each save recorded
  data/cutoffs.json         the reviewed selection of those candidates (a human pass, this file)
  data/route.json           the route the app walks

Output `data/derived.json` (sorted, no timestamps: the same inputs give the same bytes):

  quests.<stem>   title, objectives with their GUIDs and the game's wording, activators, the phase
                  files and scenes the quest is read from, its dialogue choices, the facts only
                  dialogue sets, the save status histogram, and its reviewed cutoffs.
  steps.<id>      per route step: the quests it reads, the game's own name for it, and `watch` -
                  one entry per reason to be careful, each naming the mechanism that causes it.

"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stringsdb
from paths import HERE, ROUTE, TRACKER

CUTOFFS = TRACKER / "data" / "cutoffs.json"
DERIVED = TRACKER / "data" / "derived.json"
PRESENT = ("Active", "Done", "Failed")
LEVELS = {"stop", "warn", "info"}


def load(name, default=None):
    p = HERE / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def route_order():
    """step id -> (section index, node index), and every step's quest names."""
    route = json.loads(ROUTE.read_text(encoding="utf-8"))
    order, quests = {}, {}
    for i, n in enumerate(route["nodes"]):
        sec = route["sections"].index(n["section"]) if n["section"] in route["sections"] else 99
        order[n["id"]] = (sec, i)
        quests[n["id"]] = sorted({p.lower() for f in n.get("files", []) for p in re.split(r"[|#]", f) if p})
    return route, order, quests


def earliest(names, order_of_quest):
    """Of these quest names, the one the route reaches first (unknown ones last, by name)."""
    return sorted(names, key=lambda q: (order_of_quest.get(q, (999, 999)), q))[0]


def build(verbose=True):
    idx = load("quest_index.json")
    cut = load("cutoff_index.json", {"candidates": []})
    review = json.loads(CUTOFFS.read_text(encoding="utf-8")) if CUTOFFS.exists() else {"items": []}
    saves = load("save_index.json", {})
    route, order, step_quests = route_order()
    order_of_quest = {}
    for sid, (sec, i) in order.items():
        for q in step_quests[sid]:
            order_of_quest.setdefault(q, (sec, i))

    con = stringsdb.con()
    # bundle name -> redkit stem, and back
    alias = idx.get("alias", {})
    bundle_of = defaultdict(list)
    for b, r in alias.items():
        bundle_of[r].append(b)

    # the game's own quest-log name for every quest we know, by either of its names
    title_of = {}
    for stem, q in idx["quests"].items():
        if q.get("name_locid"):
            t = stringsdb.loc(q["name_locid"], con)
            if t:
                title_of[stem] = t
                for b in bundle_of.get(stem, []):
                    title_of[b] = t

    def game_name(q):
        """the game's name for a quest, by bundle name or REDkit stem, falling back to the id itself"""
        return title_of.get(q) or title_of.get(alias.get(q, q)) or q

    status = defaultdict(Counter)
    for name, v in saves.items():
        for q, st in (v.get("state") or {}).items():
            if st in PRESENT:
                status[q][st] += 1

    def texts(quest):
        """The game's own wording for a quest: journal text of its file."""
        out = {"title": None, "objectives": []}
        locids = []
        for o in quest.get("objectives", []):
            if o.get("locid"):
                locids.append((o["guid"], o["locid"]))
        m = stringsdb.locs([l for _g, l in locids], con)
        for guid, locid in locids:
            out["objectives"].append({"guid": guid, "locid": locid, "text": m.get(locid, "")})
        tl = quest.get("name_locid")
        if tl:
            out["title"] = stringsdb.loc(tl, con)
        return out

    # reviewed cutoffs, with the route order and the save counts filled in
    cut_rows = defaultdict(list)
    for r in cut["candidates"]:
        for a in r["from_names"]:
            for b in r["to_names"]:
                cut_rows[(b, a)].append(r)

    def resolve(item):
        """One reviewed cutoff, resolved against the index and the route."""
        affected = [a.lower() for a in item["affects"]]
        closed = [c.lower() for c in item["closed_by"]]
        binding = earliest(closed, order_of_quest)
        numbers, resources = [], set()
        # A journal window is not a community candidate: it has no resource row to borrow save
        # counts or a community path from. Without this guard, resource="" matches every row.
        if item.get("resource"):
            for x in affected:
                for e in closed:
                    for r in cut_rows.get((x, e), []):
                        if r["resource"].endswith(item.get("resource_tail", "")) or r["resource"] == item.get("resource"):
                            resources.add(r["resource"])
                            numbers.append(r.get("saves") or {})
        open_before = max([n.get("open_before", 0) for n in numbers] or [0])
        later = max([n.get("later_finished", 0) for n in numbers] or [0])
        why = item["why"].replace("{binding}", game_name(binding)).replace("{binding_name}", binding)
        return {
            "id": item["id"], "level": item.get("level", "stop"), "mechanism": item["mechanism"],
            "resource": item["resource"], "binding": binding, "binding_title": game_name(binding),
            "affected": affected, "affected_titles": [game_name(a) for a in affected],
            "closed_by": closed, "closed_by_titles": [game_name(c) for c in closed],
            "closes_at": item.get("closes_at", ""),
            "closes_at_title": item.get("closes_at_title", ""),
            "pending_review": review.get("pending_review", []),
            "caveats": item.get("caveats", []),
            "action": item["action"], "headline": item["headline"].replace("{binding}", game_name(binding)),
            "why": why, "evidence": item.get("evidence", "files+saves"),
            "files": item.get("files", []),
            "saves": {"open_before": open_before, "finished_after": later},
            "resources": sorted(resources),
        }

    resolved = [resolve(i) for i in (review.get("items", []) + review.get("windows", []))]
    for r in resolved:
        if r["level"] not in LEVELS:
            raise SystemExit(f"cutoffs.json: level {r['level']!r} in {r['id']}")

    # quests the app knows about: every route stem, resolved through the alias map
    quests_out = {}
    for bundle in sorted({q for qs in step_quests.values() for q in qs}):
        stem = alias.get(bundle, bundle)
        q = idx["quests"].get(stem)
        if not q:
            continue
        t = texts(q)
        # Choice text is deliberately not shipped: the app only says that a fact-setting branch
        # changes later content (`has_branch`) or that a one-shot dialogue row exists
        # (`has_dialogue_choice`), never what the options are. The text stays in the audit JSON.
        quests_out[stem] = {
            "bundle_names": sorted(set(q.get("bundle_names", [])) | {bundle}),
            "title": t["title"], "objectives": t["objectives"],
            "has_branch": bool(q.get("has_branch")),
            "has_dialogue_choice": bool(q.get("has_dialogue_choice")),
            # the app never shows the GUID chains tools/prereqs.py needs, so they stay in the index
            "activators": [{k: v for k, v in a.items() if k != "guids"} for a in q.get("activators", [])],
            "phase_files": [p["file"] for p in q.get("phases", []) if not p.get("global")],
            "global_phase_files": [p["file"] for p in q.get("phases", []) if p.get("global")],
            "scenes": [s["file"] for s in q.get("scenes", [])][:40],
            "dialogue_only_facts": q.get("dialogue_only", [])[:60],
            "saves": dict(status.get(bundle, {})),
        }

    # prerequisites the saves disagree with (tools/contradictions.py writes this): shown as a note,
    # never as a rule, so nobody is told a quest is locked when the saves say otherwise
    disputes = json.loads((TRACKER / "data" / "route_disputes.json").read_text(encoding="utf-8")) \
        if (TRACKER / "data" / "route_disputes.json").exists() else {"disputes": []}
    disputed_by_step = defaultdict(list)
    for d in disputes.get("disputes", []):
        disputed_by_step[d["step"]].append(d)

    steps_out = {}
    for sid, names in step_quests.items():
        stems = [alias.get(n, n) for n in names]
        watch = [r for r in resolved if any(a in names or a in stems for a in r["affected"])]
        for d in disputed_by_step.get(sid, []):
            watch = watch + [{
                "id": f"disputed_{sid}_{d['prereq']}", "level": "info", "mechanism": "save-disagreement",
                "resource": "", "binding": d["prereq"], "binding_title": d["prereq"],
                "closed_by": [], "closed_by_titles": [], "action": "",
                "headline": f"The saves do not always agree that {d['prereq']} comes first",
                "why": (f"This step is written as needing {d['prereq']} first, but {d['violations']} of "
                        f"{d['checked_in']} saves show it engaged without that. Part of this is the journal "
                        f"status reading: some quests read 'Failed' in saves where they were never available. "
                        f"Treat the order as advice, not as a rule, until it is settled."),
                "evidence": "saves-disagree", "caveats": [], "affected": [], "resources": [],
                "saves": {"open_before": d["violations"], "finished_after": 0}}]
        game_title = next((quests_out[s]["title"] for s in stems if quests_out.get(s, {}).get("title")), None)
        steps_out[sid] = {
            "quests": names,
            "stems": stems,
            "game_title": game_title,
            "objectives": next((quests_out[s]["objectives"] for s in stems if quests_out.get(s, {}).get("objectives")), []),
            "activators": next((quests_out[s]["activators"] for s in stems if quests_out.get(s, {}).get("activators")), []),
            "watch": sorted(watch, key=lambda r: ({"stop": 0, "warn": 1, "info": 2}[r["level"]], r["id"])),
        }

    out = {
        "note": "Derived from the game's own files (REDkit quest graphs, scenes, journal files and the "
                "editor string database) and from the saves. Quest names and objectives are the game's "
                "wording; choice text is never included. Every `watch` entry names the mechanism that "
                "causes it. Read-only to build; tools/derive.py regenerates it.",
        "sources": {"string_db": stringsdb.STRING_DB.name if hasattr(stringsdb, "STRING_DB") else "editor string database",
                    "saves": len(saves), "index": "tools/quest_index.json", "cutoffs": "tools/cutoff_index.json",
                    "reviewed_cutoffs": str(CUTOFFS.name)},
        "quests": quests_out,
        "steps": steps_out,
    }
    DERIVED.write_text(json.dumps(out, sort_keys=True, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    if verbose:
        print(f"wrote {DERIVED.name}: {len(quests_out)} quests, {len(steps_out)} steps, "
              f"{len(resolved)} reviewed cutoffs, "
              f"{sum(1 for s in steps_out.values() if s['watch'])} steps carry a warning")
    return out


if __name__ == "__main__":
    build()
