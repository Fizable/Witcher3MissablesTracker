"""Settle a route prerequisite: is it a rule of the game, and what did the saves do?

Every `hard` edge in data/route.json is a claim - "this step cannot be engaged until that one is
done" - and the app turns it into a lock, so it has to be right. Two independent lines decide it:

  files   where the quest's own journal entry is added. If the only blocks that add it sit in the
          other quest's phase files, the game really does hang one off the other's chain; if the two
          share a phase file, they run side by side.
  saves   what actually happened. A save holding S under way while H still has work left refutes
          "H first"; S never being under way or finished again once H is over, and sometimes Failed,
          is what being closed out looks like.

The objective-level read matters, because a quest's own entry can stay `Active` after its content is
done (the game waits for a later story beat to close it). So the saves are read twice: the quest's
own entry, and every objective entry the journal file gives it. "H unfinished" means H still has an
objective the save does not record as finished, not merely that its quest entry is not `JS_Success`.

Verdicts written to data/prereq_relations.json, one row per hard edge:

  gate          the files name H's chain as what adds S's entry, and no save shows S under way
                while H has work left -> "H before S" stands
  together      S and H run at the same time: they share a phase file, or a save holds S under way
                while H still has unfinished objectives
  lost_by_H     finishing H closes S out: no save ever has S under way or finished once H is over,
                and some save has it Failed -> the advice belongs on S ("do this before you finish
                H"), which is a cutoff, not a prerequisite
  reverse       the files name S's chain as what adds H's entry
  unverified    nothing in the files says how S starts, and the saves do not contradict it either

  py prereqs.py check                  every hard edge in route.json -> data/prereq_relations.json
  py prereqs.py pair <step> <step>     one edge in full: activators, objectives, save timeline
  py prereqs.py reading [N]            does the reader attach statuses to the right entries? (N saves)
"""
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import save_reader as sr
import stringsdb
from paths import HERE, ROUTE, SAVES, TRACKER

INDEX = HERE / "quest_index.json"
SAVES_CACHE = HERE / "save_index.json"
OUT = TRACKER / "data" / "prereq_relations.json"
PRESENT = ("Active", "Done", "Failed")
# a save that shows one odd reading is not a refutation; this many saves make it a pattern
MIN_REFUTE = 3
DEEP_CAP = 320  # saves read objective by objective, at most


def load(name, default=None):
    p = HERE / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def route_steps():
    """step id -> {'files': [...], 'hard': [...], 'title': ..., 'note': ...}"""
    route = json.loads(ROUTE.read_text(encoding="utf-8"))
    out = {}
    for n in route["nodes"]:
        files = sorted({p.lower() for f in n.get("files", []) for p in f.replace("|", "\n").split("\n")
                        if p and "#" not in p})
        out[n["id"]] = {"files": files, "hard": [h for h in n.get("hard", []) if h],
                        "title": n.get("title", ""), "note": n.get("note", "")}
    return out


def timeline():
    """[(save name, mtime, {quest: status})] in the order the saves were written."""
    cache = load("save_index.json", {})
    rows = [(n, v.get("mtime", 0), v["state"]) for n, v in cache.items() if v.get("state")]
    rows.sort(key=lambda r: r[1])
    return rows


# --------------------------------------------------------------------------- files

def guid_of(idx, stem):
    """The quest's own entry GUID, as raw 16 bytes in hex."""
    j = idx["journals"].get(stem) or {}
    g = (j.get("entry_guid") or "")
    return g.lower()


def objective_guids(idx, stems):
    """{(stem): [guid raw hex, ...]} in quest-log order, plus the game's text of each."""
    out = {}
    con = stringsdb.con()
    for stem in stems:
        j = idx["journals"].get(stem) or {}
        rows = []
        for o in j.get("objectives", []):
            g = (o.get("guid") or "").lower()
            if not g:
                continue
            rows.append({"guid": g, "text": stringsdb.loc(o["locid"], con) if o.get("locid") else ""})
        out[stem] = rows
    return out


def activator_files(idx, stem):
    """Files that add this quest's *own* journal entry (not an objective of it).

    questindex records every block that adds something in the journal file. The journal path is a
    chain (quest -> phase -> objective), so the GUID that identifies what a block adds is the
    *last* one, not any of them: matching anywhere would count a block that adds one objective of
    the quest as if it added the quest.
    """
    q = idx["quests"].get(stem)
    if not q:
        return []
    want = guid_of(idx, stem)
    out = Counter()
    for a in q.get("activators", []):
        guids = [g.lower() for g in a.get("guids", [])]
        if want and guids and guids[-1] == want:
            out[a["file"]] += 1
    return sorted(out)


_FACTS = None


def fact_setters():
    """fact -> [(quest file prefix, file, value, label)] from tools/fact_index.json."""
    global _FACTS
    if _FACTS is None:
        rows = load("fact_index.json", []) or []
        by = defaultdict(set)
        for r in rows:
            if r.get("kind") == "set" and r.get("fact"):
                by[r["fact"]].add((r.get("quest", ""), r.get("src", ""), str(r.get("value")),
                                   (r.get("label") or "")[:60]))
        _FACTS = {f: sorted(v) for f, v in by.items()}
    return _FACTS


def fact_links(idx, s_stem, h_stems, h_files):
    """What S's own phase files wait on, and whether H is what sets it.

    Where a quest names no other quest in an activation block, the game still shows how it starts:
    its phases test facts, and the fact layer says which file sets them. A fact set inside H's files
    means H's chain is what opens S - which is not the same as H being finished.
    """
    q = idx["quests"].get(s_stem) or {}
    setters = fact_setters()
    h_low = {f.lower() for f in h_files}
    h_pref = set(h_stems)
    out = []
    seen = set()
    for ph in q.get("phases", []):
        if ph.get("global"):
            continue
        for fact, _cls in ph.get("test", []):
            if fact in seen:
                continue
            seen.add(fact)
            who = setters.get(fact, [])
            by_h = [w for w in who if w[1].lower() in h_low or w[0] in h_pref]
            if who:
                out.append({"fact": fact, "tested_in": ph["file"],
                            "set_by": [{"quest": w[0], "file": w[1], "value": w[2], "label": w[3]} for w in who[:6]],
                            "set_by_H": [{"quest": w[0], "file": w[1], "value": w[2], "label": w[3]} for w in by_h]})
    return out


def owner_of_file(idx, path):
    """Which quests an index phase file belongs to (its own attributed files)."""
    out = []
    for stem, q in idx["quests"].items():
        for p in q.get("phases", []):
            if p["file"].lower() == path.lower():
                out.append(stem)
    return sorted(set(out))


def own_phase_files(idx, stem):
    q = idx["quests"].get(stem) or {}
    return sorted({p["file"].lower() for p in q.get("phases", []) if not p.get("global")})


def file_relation(idx, s_stem, h_stem):
    """What the files say about how S starts, relative to H."""
    s_act = activator_files(idx, s_stem)
    h_act = activator_files(idx, h_stem)
    s_files = set(own_phase_files(idx, s_stem))
    h_files = set(own_phase_files(idx, h_stem))
    shared = sorted(s_files & h_files)
    in_h = sorted(f for f in s_act if f.lower() in h_files)
    in_h_folder = sorted(f for f in s_act if h_stem in f.lower().replace("\\", "/").split("/")[-3:-1])
    in_s = sorted(f for f in h_act if f.lower() in s_files)
    links = fact_links(idx, s_stem, {h_stem}, sorted(h_files))
    return {"s_activators": s_act, "h_activators": h_act,
            "s_activator_in_h_files": in_h, "s_activator_in_h_folder": in_h_folder,
            "h_activator_in_s_files": in_s, "shared_phase_files": shared,
            "s_phase_files": sorted(s_files), "h_phase_files": sorted(h_files),
            "fact_links": links, "facts_set_by_H": sorted({f["fact"] for f in links if f["set_by_H"]})}


# --------------------------------------------------------------------------- saves

def objective_status(save_entries, objs):
    """(unfinished, finished, unknown) objectives for one quest in one save.

    `save_entries` is {guid: status}. Objectives the save never records are unknown, not unfinished:
    the game only adds the entries it uses.
    """
    seen = [o for o in objs if o["guid"] in save_entries]
    if not seen:
        return [], [], []
    done = [o for o in seen if save_entries[o["guid"]] == "JS_Success"]
    openq = [o for o in seen if save_entries[o["guid"]] in ("JS_Active", "JS_Failed")]
    return openq, done, seen


_DEEP = {}


def deep_read(idx, names, want_stems, objs, cap=DEEP_CAP):
    """Objective-level statuses for a sample of saves: {save: {stem: {...}}}.

    One read per save, kept in _DEEP so every edge shares the same parse. Sampled evenly across
    the list it is given, so neither an early nor a late part is over-represented.
    """
    if not names:
        return {}
    if len(names) > cap:
        step = len(names) / cap
        names = [names[min(len(names) - 1, int(i * step))] for i in range(cap)]
    out = {}
    for name in names:
        if name not in _DEEP:
            rec = None
            path = SAVES / name
            if path.exists():
                try:
                    raw = sr.load_raw(path)
                    ents = sr.journal(raw, sr.name_table(raw))
                    rec = {e["guid"].lower(): e["status"] for e in ents if e.get("guid")}
                except Exception:
                    rec = None
            _DEEP[name] = rec
        by = _DEEP[name]
        if by is None:
            continue
        rec = {}
        for stem in want_stems:
            openq, done, seen = objective_status(by, objs.get(stem, []))
            rec[stem] = {"quest": {"JS_Success": "Done", "JS_Active": "Active", "JS_Failed": "Failed"}
                         .get(by.get(guid_of(idx, stem), ""), "Inactive"),
                         "open": [o["text"] or o["guid"][:8] for o in openq],
                         "done": len(done), "seen": len(seen)}
        out[name] = rec
    if len(_DEEP) > 400:
        _DEEP.clear()
    return out


def save_relation(rows, s_files, h_files, deep=None, h_stems=None):
    """The save-side picture for one edge.

    Quest-level over every save, objective-level where a deep read is available: "H over" means H's
    quest entry reads Done *and* none of its objectives is left unfinished.
    """
    h_stems = h_stems or [f.split(".")[0] for f in h_files]
    c = Counter()
    s_under_way_with_h_open = 0
    h_over_s_never_again = 0
    h_over_s_failed = 0
    h_over_s_done = 0
    examples = []
    for name, _mt, st in rows:
        s_vals = [st.get(f) for f in s_files if f in st]
        h_vals = [st.get(f) for f in h_files if f in st]
        if not s_vals or not h_vals:
            continue
        s_present = any(x in PRESENT for x in s_vals)
        h_done = any(x == "Done" for x in h_vals)
        h_open = any(x in ("Active", "Failed") for x in h_vals)
        if s_present and not h_done:
            # the objective-level read can overrule a stale quest entry: H may have no work left
            if deep is not None and name in deep:
                h_obj_open = any(deep[name].get(st, {}).get("open") for st in h_stems)
                h_seen = any(deep[name].get(st, {}).get("seen") for st in h_stems)
                if h_seen and not h_obj_open:
                    c["S under way, H entry open but no objective left"] += 1
                    continue
            s_under_way_with_h_open += 1
            c["S under way while H still open"] += 1
            if len(examples) < 3:
                examples.append((name, s_vals[0], h_vals[0]))
        if h_done:
            if s_present:
                c["S under way or finished after H"] += 1
                h_over_s_done += 1
            elif any(x == "Failed" for x in s_vals):
                c["S Failed after H"] += 1
                h_over_s_failed += 1
            else:
                h_over_s_never_again += 1
                c["S never appears after H"] += 1
    return {"counts": dict(c), "s_under_way_with_h_open": s_under_way_with_h_open,
            "h_over_s_done": h_over_s_done, "h_over_s_failed": h_over_s_failed,
            "h_over_s_never_appears": h_over_s_never_again, "examples": examples}


def verdict(files, saves):
    """Turn the two lines into one decision."""
    if files["h_activator_in_s_files"] and not (files["s_activator_in_h_files"] or files["shared_phase_files"]):
        return "reverse", ""
    refuted = saves["s_under_way_with_h_open"]
    if refuted >= MIN_REFUTE:
        # refuted by observation: the edge is not a rule. Which it is instead depends on whether S
        # is still reachable once H is over. `Failed` after H is the game saying S was closed out.
        if saves["h_over_s_done"] == 0 and saves["h_over_s_failed"] > 0:
            return "lost_by_H", (f"{refuted} save(s) hold S under way while H has work left, none "
                                 f"has S under way or finished after H, and {saves['h_over_s_failed']} "
                                 f"save(s) have the game recording S as Failed once H is over")
        return "together", (f"{refuted} save(s) hold S under way while H has work left, and "
                            f"{saves['h_over_s_done']} save(s) still have S under way or finished after H")
    linked = files["s_activator_in_h_files"] or files["facts_set_by_H"]
    if linked:
        return "gate", ("H's own files add S's journal entry" if files["s_activator_in_h_files"]
                        else f"H's files set {', '.join(files['facts_set_by_H'][:3])}, which S's phases wait on")
    if refuted == 0 and saves["h_over_s_done"] + saves["h_over_s_failed"] > 0:
        return "holds", ("no save breaks the order and the files name no link from H to S, so this is "
                         "wiki-era advice the saves have not broken - nothing here shows it is a rule")
    return "unverified", ("no file link, and no save holds either quest, so nothing tests this")


def check(deep=True, verbose=True):
    idx = load("quest_index.json")
    alias = idx.get("alias", {})
    steps = route_steps()
    rows = timeline()

    def stem_of(step_id, step):
        files = step["files"]
        if len(files) == 1:
            return alias.get(files[0], files[0])
        return None

    rev = reviewed()
    edges = []
    seen = set()
    for sid, step in steps.items():
        for h in step["hard"]:
            if h not in steps:
                continue
            s_stem = stem_of(sid, step)
            h_stem = stem_of(h, steps[h])
            edges.append({"step": sid, "requires": h, "s_stem": s_stem, "h_stem": h_stem})
            seen.add((sid, h))
    # edges that were settled out of the route are still re-tested: the saves are the arbiter, and a
    # future corpus could show the edge was right after all
    for (sid, h) in sorted(rev):
        if (sid, h) in seen or sid not in steps or h not in steps:
            continue
        edges.append({"step": sid, "requires": h, "s_stem": stem_of(sid, steps[sid]),
                      "h_stem": stem_of(h, steps[h]), "settled_out": True})

    # objective tables only for the quests involved
    want = {k for e in edges for k in (e["s_stem"], e["h_stem"]) if k}
    objs = objective_guids(idx, sorted(want))

    results = []
    # first pass, quest level only: which saves actually disagree with an edge
    prepared = []
    for e in edges:
        sid, h = e["step"], e["requires"]
        if not e["s_stem"] or not e["h_stem"]:
            results.append({**e, "verdict": "unverified", "disagreements": 0,
                            "why": "a step reads more than one journal file", "files": {}, "saves": {}})
            continue
        files = file_relation(idx, e["s_stem"], e["h_stem"])
        quest_level = save_relation(rows, steps[sid]["files"], steps[h]["files"], None)
        prepared.append((e, files, quest_level))
    # the saves worth reading objective by objective: those where S is under way with H not Done.
    # A quest's own entry can stay Active after its content is done, so this is where a stale entry
    # would be mistaken for a broken rule.
    candidates = [n for n, _mt, st in rows
                  if any(st.get(e["s_stem"]) in PRESENT and st.get(e["h_stem"]) != "Done"
                         for e, _f, _q in prepared)]
    objs_for_deep = {k for e, _f, _q in prepared for k in (e["s_stem"], e["h_stem"])}
    deep = deep_read(idx, candidates, objs_for_deep, objs) if deep else None
    if verbose:
        print(f"reading {len(candidates)} saves objective by objective (of {len(rows)})", flush=True)

    # every fact that could carry one of these prerequisites, then one read of each save for them
    facts_of_interest = set()
    for e, files, _q in prepared:
        e["candidates"] = candidate_facts(idx, e["s_stem"], e["h_stem"], files)
        facts_of_interest.update(e["candidates"])
    if verbose:
        print(f"{len(facts_of_interest)} candidate gate facts across {len(prepared)} edges", flush=True)
    facts_by_save = save_facts([n for n, _m, _st in rows], facts_of_interest) if facts_of_interest else {}

    for e, files, _q in prepared:
        sid, h = e["step"], e["requires"]
        h_stems = [alias.get(f, f) for f in steps[h]["files"]]
        saves = save_relation(rows, steps[sid]["files"], steps[h]["files"], deep, h_stems)
        refuted = saves["s_under_way_with_h_open"]
        v, why = verdict(files, saves)
        signals = []
        for fact, src in sorted(e["candidates"].items()):
            signals.append({**src, "fact": fact, **signal_test(rows, facts_by_save, steps[sid]["files"], fact)})
        # usable: no save has this step under way with the fact unset. Of those, a condition on the
        # block that creates the step outranks a fact its phases merely wait on, and the tightest
        # (set in the fewest saves without the step) is the closest thing to the real moment.
        good = sorted((s for s in signals if s["refuted"] == 0),
                      key=lambda s: (s["kind"] != "chain", s["fact_set_without_s"], s["fact"]))
        # Only keep an edge as a fact gate when the game's own condition is unambiguous: one fact
        # that no save breaks. Where the files name several candidates, or none, the honest move is
        # to drop the lock instead of picking one and calling it the rule.
        chosen = good[0] if len(good) == 1 else {}
        if refuted >= MIN_REFUTE and chosen:
            # the prerequisite is real and the game names its condition; the journal status was the
            # wrong signal to test it with, which is what the saves were objecting to
            v = "gate_fact"
            why = (f"not H finished but H's progress: the game's own condition is {chosen['fact']} "
                   f"({chosen['from']}), and no save has this step under way without it - which is why "
                   f"{refuted} save(s) hold it under way while H reads unfinished")
        elif refuted >= MIN_REFUTE:
            v = "together" if saves["h_over_s_done"] else "lost_by_H"
            named = f"the files name {len(good)} conditions" if good else "the files name no condition"
            why = (f"{refuted} save(s) hold this step under way while H has work left, and {named} to "
                   f"test it with beyond H's status, so there is no single rule to lock on")
        results.append({**e, "verdict": v, "why": why, "disagreements": refuted,
                        "files": files, "saves": saves, "signals": signals, "chosen_fact": chosen,
                        "step_title": steps[sid]["title"], "requires_title": steps[h]["title"],
                        "note": steps[sid]["note"]})

    # the route and the settlement have to agree: the app locks on the route, so a decision that is
    # not in route.json - or a route edge that no longer matches its decision - is a failure
    route = json.loads(ROUTE.read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in route["nodes"]}
    problems = []
    for r in results:
        n = nodes.get(r["step"], {})
        hard = n.get("hard") or []
        facts = ((n.get("hard_facts") or {}).get(r["requires"]) or [])
        r["in_route"] = {"hard": r["requires"] in hard, "fact": facts[:]}
        item = rev.get((r["step"], r["requires"]))
        r["review"] = item or {}
        bad = []
        if item:
            want = sorted(item.get("facts") or [])
            if item["decision"] == "fact":
                if r["verdict"] != "gate_fact":
                    bad.append(f"review says test {want}, but the saves now give verdict {r['verdict']}")
                elif r["chosen_fact"].get("fact") not in want:
                    bad.append(f"review says {want}, the files now point at {r['chosen_fact'].get('fact')}")
                if r["requires"] not in hard or sorted(facts) != want:
                    bad.append(f"route.json does not carry it (hard={r['requires'] in hard}, hard_facts={facts})")
            else:
                if r["verdict"] not in ("together", "lost_by_H"):
                    bad.append(f"review says drop, but the saves now give verdict {r['verdict']}")
                if r["requires"] in hard:
                    bad.append("route.json still lists it as hard")
        r["review_problem"] = "; ".join(bad)
        if bad:
            problems.append(f"{r['step']} requires {r['requires']}: {r['review_problem']}")
    if verbose and problems:
        print(f"{len(problems)} settlement mismatch(es):", flush=True)
        for p in problems:
            print("  MISMATCH", p)
    out = {"review_problems": problems,
           "note": "Every `hard` edge in data/route.json, decided from the game's files and from the "
                   "saves (tools/prereqs.py). `gate` edges are rules the app may lock on; the other "
                   "verdicts say the edge is not a rule and what it is instead.",
           "verdicts": dict(Counter(r["verdict"] for r in results)), "edges": results}
    OUT.write_text(json.dumps(out, sort_keys=True, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    if verbose:
        for r in sorted(results, key=lambda r: (r["verdict"], r["step"])):
            s = r.get("saves") or {}
            extra = f"  <- {r['chosen_fact']['fact']}" if r.get("chosen_fact") else ""
            print(f"{r['verdict']:10s} {r['step']:16s} requires {r['requires']:16s} "
                  f"[under way with H open {s.get('s_under_way_with_h_open', 0)}, "
                  f"H over and S reachable {s.get('h_over_s_done', 0)}, "
                  f"Failed after H {s.get('h_over_s_failed', 0)}, "
                  f"gone after H {s.get('h_over_s_never_appears', 0)}]{extra}")
            if r["verdict"] in ("gate_fact", "together", "lost_by_H"):
                print(f"           {r['why'][:150]}")
        print(f"{len(results)} edges -> {OUT.name}: {out['verdicts']}")
    return out


SAVE_FACTS = HERE / "save_facts.json"
REVIEW = TRACKER / "data" / "prereqs_review.json"


def reviewed():
    """{(step, requires): item} - the reviewed decisions about edges the saves disputed.

    Kept as an input, not an output: an edge that was dropped from the route stops being a route
    edge, so without this the settlement would quietly stop being re-tested against the saves.
    """
    if not REVIEW.exists():
        return {}
    d = json.loads(REVIEW.read_text(encoding="utf-8"))
    return {(i["step"], i["requires"]): i for i in d.get("items", [])}


_FACT_NAMES = None


def fact_names():
    """Every fact name the game's own phase blocks name, from tools/fact_index.json.

    A condition's label is often prose ('Asking Cleaver for help'), so a label only counts as a
    candidate when it really is a fact the game uses - the fact index is the arbiter, not a regex.
    """
    global _FACT_NAMES
    if _FACT_NAMES is None:
        names = set()
        for r in load("fact_index.json", []) or []:
            if r.get("fact"):
                names.add(r["fact"])
        _FACT_NAMES = names
    return _FACT_NAMES


def facts_named_by(label):
    """The fact names a condition label names, if any: 'q302_whoreson_found', 'Add q302_freed_rico'."""
    lab = str(label or "").strip()
    out = []
    if lab in fact_names():
        out.append(lab)
    parts = lab.split()
    if len(parts) == 2 and parts[0].lower() in ("add", "set") and parts[1] in fact_names():
        out.append(parts[1])
    return out


def same_file(a, b):
    """'q302_mafia' and 'q302mafia' are the same quest (REDkit and bundle naming)."""
    na = re.sub(r"[^a-z0-9]", "", str(a).lower())
    nb = re.sub(r"[^a-z0-9]", "", str(b).lower())
    return bool(na) and (na in nb or nb in na)


def candidate_facts(idx, s_stem, h_stem, files):
    """The fact a prerequisite could really rest on, taken only from the game's own conditions.

    Two places name one, and both are the game stating the dependency itself:

      chain      a condition feeding the block that adds S's own journal entry, when that block
                 lives in H's files - the game's own statement of when S appears
      test       a fact S's own phases wait on that H's files set

    A condition's readable label is often the fact it waits on (the game names the condition after
    it), so labels that look like fact names count too. Nothing is invented here: if the game's
    conditions do not name a fact, there is no candidate and the edge cannot be kept as a rule.
    """
    out = {}

    def add(fact, source, kind):
        if not fact:
            return
        cur = out.get(fact)
        if cur is None or (kind == "chain" and cur["kind"] != "chain"):
            out[fact] = {"kind": kind, "from": source, "label": ""}

    for blk in entry_blocks(idx, s_stem, limit=8):
        if not same_file(blk["file"], h_stem):
            continue
        where = blk["file"].split(chr(92))[-1]
        for _d, _cls, lab, _i in blk["back"]:
            for fact in facts_named_by(lab):
                add(fact, f"condition on the block that adds this step's entry, in {where}", "chain")
        for fact, _cls in blk["facts"]:
            add(fact, f"condition on the block that adds this step's entry, in {where}", "chain")

    for link in files.get("fact_links", []):
        if link["set_by_H"]:
            add(link["fact"], f"waited on by this step's own phases ({link['tested_in'].split(chr(92))[-1]}), "
                              f"set by {link['set_by_H'][0]['file'].split(chr(92))[-1]}", "test")
    return out


def save_facts(names, interest, refresh=False):
    """{save: {fact: [values]}} for the facts of interest, cached in tools/save_facts.json.

    Read-only, like everything else: this is the same CFactsDB the app reads out of a save, kept
    for the facts the route's prerequisites could rest on.
    """
    cache = load(SAVE_FACTS.name, {}) if not refresh else {}
    have = cache.get("saves", {})
    todo = [n for n in names if n not in have]
    if todo:
        for i, name in enumerate(todo, 1):
            path = SAVES / name
            rec = {}
            if path.exists():
                try:
                    raw = sr.load_raw(path)
                    f = sr.facts(raw)
                    rec = {k: [int(x) for x in v] for k, v in f.items() if k in interest}
                except Exception:
                    rec = {}
            have[name] = rec
            if i % 100 == 0:
                SAVE_FACTS.write_text(json.dumps({"note": "facts of interest per save, for "
                                                  "tools/prereqs.py; read-only", "saves": have},
                                                 sort_keys=True), encoding="utf-8")
        SAVE_FACTS.write_text(json.dumps({"note": "facts of interest per save, for tools/prereqs.py; "
                                                  "read-only", "saves": have}, sort_keys=True), encoding="utf-8")
    return have


def signal_test(rows, facts_by_save, s_files, fact):
    """How the saves read for one candidate gate: S engaged while the fact is not set."""
    engaged = set_seen = refuted = 0
    for name, _mt, st in rows:
        if any(st.get(f) in PRESENT for f in s_files):
            engaged += 1
            if fact not in (facts_by_save.get(name) or {}):
                refuted += 1
        elif fact in (facts_by_save.get(name) or {}):
            set_seen += 1
    return {"s_engaged": engaged, "refuted": refuted, "fact_set_without_s": set_seen}


def entry_blocks(idx, stem, limit=8):
    """The blocks that add this quest's own entry, with the conditions feeding them.

    Read straight from the phase files rather than from the index: the index keeps the block and its
    file, but the chain of conditions that leads to it is what says how the quest opens.
    """
    import questgraph
    from paths import REDKIT_R4

    want = guid_of(idx, stem)
    out = []
    for f in activator_files(idx, stem)[:limit]:
        path = REDKIT_R4 / f
        if not path.exists():
            continue
        try:
            g = questgraph.G(path)
        except Exception:
            continue
        for b in g.blocks_for(stem):
            guids = [x.lower() for x in b["guids"]]
            if not guids or guids[-1] != want:
                continue
            back = [(d, cls, lab, i) for d, cls, lab, i in g.backward(b["index"]) if d <= 3]
            facts = []
            for d, cls, lab, i in g.backward(b["index"]):
                if cls == "CQuestFactsDBCondition":
                    for v in cr2w_props(g, i):
                        if v["name"].lower() in ("factid", "factid") and isinstance(v["value"], str):
                            facts.append((v["value"], cls))
            out.append({"file": f, "block": b["index"], "class": b["class"],
                        "label": b["label"], "back": back, "facts": sorted(set(facts))[:8]})
    return out


def cr2w_props(g, i):
    import cr2w
    return cr2w.props(g.p, g.p["exports"][i - 1]) if 1 <= i <= len(g.p["exports"]) else []


def pair(a, b):
    """Everything known about one edge, for reading by eye."""
    idx = load("quest_index.json")
    alias = idx.get("alias", {})
    steps = route_steps()
    con = stringsdb.con()
    rows = timeline()
    for tag, sid in ((None, a), ("requires", b)):
        step = steps.get(sid)
        if not step:
            print(f"no such step: {sid}")
            return
        stem = alias.get(step["files"][0], step["files"][0]) if step["files"] else None
        j = idx["journals"].get(stem) or {}
        print(f"\n== {sid}   \"{step['title']}\"  files={step['files']}  redkit={stem}")
        print(f"   hard={step['hard']}  note={step['note']!r}")
        print(f"   game name: {stringsdb.loc(j.get('title_locid'), con) if j.get('title_locid') else None}")
        print(f"   objectives, in quest-log order:")
        for o in objective_guids(idx, [stem]).get(stem, []):
            print(f"     {o['guid'][:12]}  {o['text']}")
        act = activator_files(idx, stem)
        print(f"   entry added by {len(act)} block(s) in:")
        for f in act:
            print(f"     {f}   (own files of: {', '.join(owner_of_file(idx, f)) or 'aggregate'})")
        for blk in entry_blocks(idx, stem, limit=6):
            print(f"     block #{blk['block']} {blk['class']} in {blk['file'].split(chr(92))[-1]}")
            for d, cls, lab, _i in blk["back"]:
                if lab or cls in ("CQuestFactsDBCondition", "CQuestConditionBlock", "CQuestScriptBlock"):
                    print(f"        d{d} {cls:30s} {lab[:80]}")
            for fact, cls in blk["facts"]:
                print(f"        fact {fact:40s} {cls}")
    if b in steps and a in steps:
        fs = alias.get(steps[a]["files"][0], steps[a]["files"][0])
        fh = alias.get(steps[b]["files"][0], steps[b]["files"][0])
        rel = file_relation(idx, fs, fh)
        print(f"\n-- file relation: shared phase files={rel['shared_phase_files']}")
        print(f"   S activator inside H's files={rel['s_activator_in_h_files']}")
        print(f"   H activator inside S's files={rel['h_activator_in_s_files']}")
        print(f"   save timeline (S then H):")
        for name, mt, st in rows:
            sv, hv = st.get(steps[a]["files"][0]), st.get(steps[b]["files"][0])
            if sv in PRESENT or hv in PRESENT:
                print(f"     {name:48s} {a}={sv:<12s} {b}={hv}")


def reading_result(n=25):
    """Is the reader attaching statuses to the right entries?

    Returns {saves, entries, unknown, statuses, mismatches}. Every journal entry carries the GUID of
    the item and the journal resource it came from; if the walk were off by one entry, statuses and
    resources would land on the wrong GUID. So the test is whether each entry's resource really is
    the file its GUID belongs to - which is what settles "is the journal status reading wrong" for
    the disputed prerequisites: a Failed in a save is the game's own record, not a misread.
    """
    idx = load("quest_index.json")
    g2 = {}
    for stem, v in idx["journals"].items():
        if v.get("entry_guid"):
            g2.setdefault(v["entry_guid"].lower(), set()).add((stem, "quest"))
        for o in v.get("objectives", []):
            if o.get("guid"):
                g2.setdefault(o["guid"].lower(), set()).add((stem, "objective"))
    names = sorted(p.name for p in SAVES.glob("*.sav"))
    if not names:
        return {"saves": 0, "entries": 0, "unknown": 0, "statuses": {}, "mismatches": [],
                "error": f"no saves found at {SAVES}"}
    random.Random(7).shuffle(names)
    names = names[:n]
    ents = 0
    unknown = 0
    mismatch = []
    statuses = Counter()
    for name in sorted(names):
        try:
            raw = sr.load_raw(SAVES / name)
            entries = sr.journal(raw, sr.name_table(raw))
        except Exception as ex:
            print(f"  {name}: unreadable ({ex})")
            continue
        for e in entries:
            if not e.get("guid"):
                continue
            ents += 1
            statuses[e["status"]] += 1
            hits = g2.get(e["guid"].lower())
            if not hits:
                unknown += 1
                continue
            res = (e.get("resource") or "").lower()
            if res and not any(stem in os.path.basename(res).replace(".journal", "") for stem, _k in hits):
                mismatch.append((name, e["guid"][:12], sorted(hits), os.path.basename(res)))
    return {"saves": len(names), "entries": ents, "unknown": unknown,
            "statuses": dict(statuses), "mismatches": mismatch}


def reading(n=25):
    """The consistency check, printed."""
    r = reading_result(n)
    if r.get("error"):
        print(r["error"])
        return 1
    print(f"{r['saves']} saves, {r['entries']} journal entries with a GUID")
    print(f"  statuses: {r['statuses']}")
    print(f"  GUIDs the journal files do not name: {r['unknown']} ({r['unknown'] / max(1, r['entries']):.1%})")
    print(f"  GUID/resource mismatches: {len(r['mismatches'])}")
    for m in r["mismatches"][:10]:
        print(f"    {m}")
    return 1 if r["mismatches"] else 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "pair":
        pair(sys.argv[2], sys.argv[3])
    elif len(sys.argv) > 1 and sys.argv[1] == "reading":
        sys.exit(reading(int(sys.argv[2]) if len(sys.argv) > 2 else 25))
    else:
        sys.exit(1 if check()["review_problems"] else 0)
