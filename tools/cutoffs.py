"""Cutoffs worked out from the game's own files, then tested against the saves.

A **cutoff** is content you can no longer reach. The game states these in its files: a quest's
story-phase setter switches off a spawnset or community (`CDeactivateSpawnset`), and another
quest's phases or scenes reference that same resource - so once the first quest is over, the
second cannot be done. Nothing here is a wiki rule.

Two questions, one per source:

  files   which quest E switches off resource R (its own phase file, named keys), and which
          quests X reference R at all (their phase files and their scenes, via `ref_import`).
  saves   what actually followed: of the saves where E is finished with X still open, does any
          LATER save have X finished? If none does, the cutoff holds in practice; if several do,
          the pair is refuted and kept only so it is not warned about.

Output `cutoff_index.json` (git-ignored): one row per (E, X, R) with the save counts and a
verdict of `confirmed`, `refuted`, `thin` (too few saves to say) or `untested`.

  py cutoffs.py build          build/update the index
  py cutoffs.py report [quest] one line per cutoff, grouped by the quest that is lost
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cr2w
import questindex
from paths import HERE, REDKIT_R4, QUEST_ROOT

INDEX = HERE / "cutoff_index.json"
SAVES_CACHE = HERE / "save_index.json"
PRESENT = ("Active", "Done", "Failed")


def quest_refs(entry):
    """Every resource a quest references, from its own phase files and scenes. Name -> how often.

    Global phase files (bugfixing_phase, additional_game_elements, ...) are left out: they belong to
    the build, reference half the game, and treating them as a quest's own files turns every other
    quest into a cutoff candidate.
    """
    out = defaultdict(int)
    files = [p["file"] for p in entry.get("phases", []) if not p.get("global")] + [s["file"] for s in entry.get("scenes", [])]
    for f in files:
        path = REDKIT_R4 / f
        try:
            p = cr2w.parse(path)
        except Exception:
            continue
        for e in p["exports"]:
            for res in cr2w.refs(p, e):
                out[res] += 1
    return out


def deactivation_map(idx):
    """E quest -> {resource: phase file that switches it off}.

    `switches` comes from the index, where only non-global phase files are listed for a quest.
    """
    out = defaultdict(dict)
    for stem, q in idx["quests"].items():
        for sw in q.get("switches", []):
            for res in sw["deactivates"]:
                out[stem].setdefault(res, sw["file"])
    return out


def save_timeline():
    """[(save name, mtime, {quest: status})] in the order the saves were written."""
    if not SAVES_CACHE.exists():
        return []
    cache = json.loads(SAVES_CACHE.read_text(encoding="utf-8"))
    rows = [(name, v.get("mtime", 0), v.get("state") or {}) for name, v in cache.items() if v.get("state")]
    rows.sort(key=lambda r: r[1])
    return rows


def judge(timeline, e, x):
    """What the saves show about E finishing while X was in progress.

    A save where the player never touched X says nothing about a cutoff, so the test looks only
    at the saves where X was already under way when E got finished, and asks whether any save
    written later has X finished anyway. That is a consistency check on the files, not a proof:
    it can refute the files (X does complete afterwards) and it can show no contradiction, but
    it cannot demonstrate that stopping was impossible.
    """
    with_from, open_before = 0, 0
    later_finished, later_still_open = 0, 0
    ever_open = False
    seen_open = False
    for _name, _mt, st in timeline:
        xs = st.get(x, "")
        if xs in ("Active", "Failed"):
            ever_open = True
        if st.get(e) == "Done":
            with_from += 1
            if xs in ("Active", "Failed"):
                open_before += 1
                seen_open = True
            if seen_open:
                if xs == "Done":
                    later_finished += 1
                elif xs in ("Active", "Not started", "Inactive", ""):
                    later_still_open += 1
    verdict = "untested"
    if open_before or later_finished:
        if later_finished >= 2:
            verdict = "refuted"
        elif open_before >= 3 and later_finished == 0:
            verdict = "consistent"
        else:
            verdict = "thin"
    return {"with_from": with_from, "open_before": open_before,
            "later_finished": later_finished, "later_still_open": later_still_open,
            "ever_open": ever_open, "verdict": verdict}


def build(verbose=True):
    idx = json.loads((HERE / "quest_index.json").read_text(encoding="utf-8"))
    alias = idx.get("alias", {})
    # a quest the route knows by its bundled name is the same quest as its REDkit name
    rev = defaultdict(set)
    for bundle, rk in alias.items():
        rev[rk].add(bundle)

    refs = {}
    for stem, q in idx["quests"].items():
        r = quest_refs(q)
        if r:
            refs[stem] = r
    if verbose:
        print(f"  references collected for {len(refs)} quests", flush=True)

    # how many quests reference each resource: a resource many quests touch is not specific
    freq = defaultdict(int)
    for stem, r in refs.items():
        for res in r:
            freq[res] += 1

    off = deactivation_map(idx)
    # a global phase file switches things off for the whole build, not on behalf of one quest
    off = {e: {r: w for r, w in resources.items() if not questindex.is_global(w)} for e, resources in off.items()}
    rows = []
    for e, resources in off.items():
        for res, where in resources.items():
            for x, r in refs.items():
                if x == e or res not in r:
                    continue
                rows.append({"from": e, "from_names": sorted(rev.get(e, [e])), "to": x,
                             "to_names": sorted(rev.get(x, [x])), "resource": res,
                             "kind": Path(res).suffix.lower(), "specificity": freq[res],
                             "deactivated_in": where})
    if verbose:
        print(f"  {len(rows)} candidate cutoffs from the files", flush=True)

    # a community that some other phase switches back on is not gone for good: the candidate is
    # kept, but marked, so a reviewer can tell a permanent cutoff from a phase transition
    back_on = defaultdict(set)
    for stem, q in idx["quests"].items():
        for sw in q.get("switches", []):
            for res in sw.get("activates", []):
                back_on[res].add(sw["file"])

    timeline = save_timeline()
    if verbose:
        print(f"  testing {len(rows)} candidates against {len(timeline)} saves", flush=True)
    for r in rows:
        e = r["from_names"][0] if r["from_names"] else r["from"]
        x = r["to_names"][0] if r["to_names"] else r["to"]
        r["saves"] = judge(timeline, e, x) if timeline else {}
        r["verdict"] = (r["saves"] or {}).get("verdict", "untested")
        if r["verdict"] in ("consistent", "thin"):
            again = sorted(back_on.get(r["resource"], ()))[:5]
            if again:
                r["reactivated_in"] = again

    rows.sort(key=lambda r: ({"consistent": 0, "thin": 1, "untested": 2, "refuted": 3}[r["verdict"]],
                             r["specificity"], r["to"], r["resource"]))
    out = {"note": "cutoff candidates: what one quest switches off that another quest references, "
                   "judged against the order the saves were written. Read-only.",
           "candidates": rows}
    INDEX.write_text(json.dumps(out, sort_keys=True, indent=1), encoding="utf-8")
    if verbose:
        counts = defaultdict(int)
        for r in rows:
            counts[r["verdict"]] += 1
        print(f"wrote {INDEX.name}: {len(rows)} candidates {dict(counts)}")
    return out


def report(only=None, consistent=False, limit=None):
    out = json.loads(INDEX.read_text(encoding="utf-8"))
    rows = out["candidates"]
    if only:
        rows = [r for r in rows if only in r["to_names"] or only in r["from_names"]]
    if consistent:
        rows = [r for r in rows if r["verdict"] == "consistent"]
    if limit:
        rows = rows[:limit]
    for r in rows:
        s = r.get("saves") or {}
        print(f"{r['verdict']:10s} spec{r['specificity']:<4d} {r['from_names'][0]:24s} -> {r['to_names'][0]:24s} "
              f"via {Path(r['resource']).name:34s} "
              f"[E done {s.get('with_from', 0)}, X open before {s.get('open_before', 0)}, "
              f"finished later {s.get('later_finished', 0)}, still open {s.get('later_still_open', 0)}]")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        consistent = "--consistent" in sys.argv
        args = [a for a in sys.argv[2:] if not a.startswith("--")]
        limit = int(args[1]) if len(args) > 1 else None
        report(args[0] if args else None, consistent=consistent, limit=limit)
    else:
        build()
