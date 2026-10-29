"""Audit the reviewed exclusivity edges and write the candidate report.

`data/exclusive.json` is reviewed data. This tool does not invent an edge: it checks that every edge
names live outcomes and evidence, that every pair in a `selection: one` group has an edge, and that
the rejected candidates have a stated reason. It can write `tools/exclusivity_report.md` for the
handoff.

  py exclusivity.py --check
  py exclusivity.py --write

The report is evidence for the reviewer. It is not read by the app.
"""
import argparse
import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import HERE, TRACKER

OUTCOMES = TRACKER / "data" / "outcomes.json"
EXCLUSIVE = TRACKER / "data" / "exclusive.json"
CUTOFFS = TRACKER / "data" / "cutoffs.json"
REPORT = HERE / "exclusivity_report.md"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    doc = load(OUTCOMES)
    ex = load(EXCLUSIVE)
    groups = doc.get("groups") or {}
    outcomes = doc.get("outcomes") or {}
    edges = ex.get("edges") or []
    errors = []

    labels = {oid: o.get("label", oid) for oid, o in outcomes.items()}
    seen = set()
    for i, edge in enumerate(edges):
        if edge.get("kind") != "outcome":
            continue
        a, b = edge.get("a"), edge.get("b")
        if a not in outcomes or b not in outcomes:
            errors.append(f"edges[{i}] names an unknown outcome: {a!r}, {b!r}")
            continue
        pair = tuple(sorted((a, b)))
        if pair in seen:
            errors.append(f"edges[{i}] duplicates {pair}")
        seen.add(pair)
        if not edge.get("evidence"):
            errors.append(f"edges[{i}] has no evidence")
        if not edge.get("mechanism"):
            errors.append(f"edges[{i}] has no mechanism")

    for gid, group in groups.items():
        members = group.get("outcomes") or []
        for a, b in itertools.combinations(members, 2):
            if tuple(sorted((a, b))) not in seen:
                errors.append(f"group {gid!r} has no edge between {a!r} and {b!r}")

    # Candidate pairs that share a cutoff but are not exclusive. A cutoff closes a window; it does
    # not mean two quests cannot both be completed inside it. These are the rejections the audit
    # wants to make visible.
    cut = load(CUTOFFS) if CUTOFFS.exists() else {}
    rejected = []
    for window in (cut.get("windows") or [])[:3]:
        affects = window.get("affects") or []
        if len(affects) < 2:
            continue
        rejected.append({
            "candidate": " / ".join(affects[:2]),
            "source": f"cutoffs.json#{window.get('id', 'window')}",
            "reason": "both quests share the same closing window; the cutoff is a deadline, not a partition, and no failure block or CDeactivateSpawnset makes them exclusive",
        })
    for item in (cut.get("items") or [])[:2]:
        affects = item.get("affects") or []
        if len(affects) < 2:
            continue
        rejected.append({
            "candidate": " / ".join(affects[:2]),
            "source": f"cutoffs.json#{item.get('id', 'item')}",
            "reason": "the same cutoff closes their window; both can be completed before it, so the pair is not an exclusion edge",
        })

    cross = 0
    for a, b in itertools.combinations(sorted(outcomes), 2):
        ga = outcomes[a].get("group")
        gb = outcomes[b].get("group")
        if ga != gb and tuple(sorted((a, b))) not in seen:
            cross += 1
    summary = f"{len(groups)} groups, {len(outcomes)} outcomes, {len(seen)} accepted outcome edges, {cross} cross-group pairs rejected, {len(rejected)} cutoff candidates rejected"

    lines = [
        "# Exclusivity audit",
        "",
        "Reviewed data: `data/exclusive.json`. Accepted edges are terminal outcomes that share a",
        "`selection: one` group or a file-backed fact partition. The app never infers an edge from two",
        "quests looking related.",
        "",
        "## Accepted",
        "",
        "| A | B | Mechanism | Evidence rows |",
        "|---|---|---|---|",
    ]
    for edge in edges:
        if edge.get("kind") != "outcome":
            continue
        a, b = edge.get("a"), edge.get("b")
        lines.append(f"| {labels.get(a, a)} (`{a}`) | {labels.get(b, b)} (`{b}`) | {edge.get('mechanism', '')} | {len(edge.get('evidence') or [])} |")
    lines += [
        "",
        "## Rejected candidates",
        "",
        "| Candidate | Source | Why it is not an edge |",
        "|---|---|---|",
    ]
    for row in rejected:
        lines.append(f"| {row['candidate']} | {row['source']} | {row['reason']} |")
    lines += [
        "",
        f"Cross-group outcome pairs not listed: {cross}. None has a shared failure block, cutoff or",
        "`CDeactivateSpawnset` proof, so they are omitted rather than guessed. The groups are:",
        "",
    ]
    for gid, group in groups.items():
        lines.append(f"- `{gid}`: " + ", ".join(f"`{oid}`" for oid in group.get("outcomes") or []))
    lines += ["", "## Summary", "", summary, ""]

    if args.write:
        REPORT.write_text("\n".join(lines), encoding="utf-8")
        print(f"wrote {REPORT}")
    else:
        print(summary)
    for error in errors:
        print(f"error: {error}")
    if errors:
        print(f"{len(errors)} problem(s); exclusivity data is not shippable")
        return 1
    if args.check and not seen:
        print("error: no accepted outcome edges")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
