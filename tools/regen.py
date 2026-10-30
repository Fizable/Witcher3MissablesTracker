"""Regenerate everything from the game's files and prove it came out the same.

The pipeline is data, not a one-off: `questindex` reads the game's resources, `cutoffs` turns them
into candidates and judges them on the saves, `review_cutoffs` applies the review rule, `questgraph`
builds the quest graph, `routegen` writes the route from it, `branchgen` writes the branch graph
from the index's scene choices, `coverage` writes the per-pack counts, `derive` writes what the app
shows, and `contradictions` tests the result. This runs that chain in order and compares the bytes
of every output against `tools/goldens.json`, so a change that silently moves a warning is visible
as a different hash rather than a surprise in game.

  py regen.py            regenerate, compare, exit 1 on any difference
  py regen.py --update   regenerate and record the hashes (do this when the difference is wanted)
  py regen.py --check    compare only, do not regenerate

Timings on the machine this was built on: questindex ~1 min, cutoffs ~2 min, derive ~15s, the save
index ~4 min the first time and cached after (run `saveindex.py build` separately if it is stale).
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import HERE, TRACKER

GOLDENS = HERE / "goldens.json"
OUTPUTS = [
    HERE / "quest_index.json",
    HERE / "cutoff_index.json",
    HERE / "contradiction_report.md",
    TRACKER / "data" / "cutoffs.json",
    TRACKER / "data" / "quest_graph.json",
    TRACKER / "data" / "route.json",
    TRACKER / "data" / "branches.json",
    TRACKER / "data" / "coverage.json",
    TRACKER / "data" / "derived.json",
    TRACKER / "data" / "route_disputes.json",
    TRACKER / "data" / "prereq_relations.json",
    # cards.py owns the ledger and cardwindows.py its windows; neither is a step in this chain, so
    # the hash is the guard that the shipped card data did not move unnoticed.
    TRACKER / "data" / "gwent_cards.json",
]
STEPS = [
    # --all: the route is every CJournalQuest in the game, not just the ones the old route named
    ("quest_index.json", [sys.executable, "questindex.py", "build", "--all"]),
    ("cutoff_index.json", [sys.executable, "cutoffs.py", "build"]),
    ("cutoffs.json", [sys.executable, "review_cutoffs.py", "build"]),
    ("quest_graph.json", [sys.executable, "questgraph.py", "build"]),
    ("route.json", [sys.executable, "routegen.py", "build"]),
    # the branch graph and the pack coverage read the route and the index; both must run after
    # routegen and before the app payload is derived
    ("branches.json", [sys.executable, "branchgen.py", "build"]),
    ("coverage.json", [sys.executable, "coverage.py", "build"]),
    ("derived.json", [sys.executable, "derive.py"]),
    # the settlement of the route's prerequisites: the app locks on data/route.json, so how each
    # edge was decided (and against which saves) has to be reproduced and recorded too
    ("prereq_relations.json", [sys.executable, "prereqs.py", "check"]),
    ("contradiction_report.md", [sys.executable, "contradictions.py"]),
]


def digest(p):
    if not p.exists():
        return "missing"
    # Git may check text files out with CRLF on Windows; hash the canonical LF content so the
    # check stays about what the pipeline wrote, not the local checkout format.
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:16]

def run(steps):
    for label, cmd in steps:
        print(f"  running {label} ...", flush=True)
        r = subprocess.run(cmd, cwd=str(HERE), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        tail = [l for l in r.stdout.splitlines() if l.strip()][-1:] or [""]
        print(f"    {r.returncode} {tail[0][:110]}")
        if r.returncode != 0:
            raise SystemExit(f"{label} failed")


def main():
    check_only = "--check" in sys.argv
    update = "--update" in sys.argv
    if not check_only:
        run(STEPS)
    now = {p.name: digest(p) for p in OUTPUTS}
    if update:
        GOLDENS.write_text(json.dumps({"note": "sha256 (first 16) of the LF-normalized pipeline outputs; "
                                               "py regen.py compares against these", "hashes": now},
                                      indent=1, sort_keys=True), encoding="utf-8")
        print(f"recorded {len(now)} hashes in {GOLDENS.name}")
        return 0

    before = json.loads(GOLDENS.read_text(encoding="utf-8"))["hashes"] if GOLDENS.exists() else {}
    diff = {k: (before.get(k, "-"), v) for k, v in now.items() if before.get(k) != v}
    if diff:
        print(f"{len(diff)} output(s) changed:")
        for k, (a, b) in sorted(diff.items()):
            print(f"  {k}: {a} -> {b}")
        print("if the change is wanted, record it with: py regen.py --update")
        return 1
    print(f"all {len(now)} outputs match the recorded hashes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
