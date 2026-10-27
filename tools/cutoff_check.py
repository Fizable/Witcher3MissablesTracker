"""Cutoff check: does finishing quest E deactivate something quest X still needs?

  cutoff_check.py <E_phase_file> <X_phase_file>
  cutoff_check.py --find <E_phase_file>       list every quest phase whose references overlap E's deactivations

Uses the graph only. E's deactivations are the spawnsets/communities named by
CDeactivateSpawnset blocks under CQuestStoryPhaseSetterBlock blocks in E's file.
X's needs are every resource X references. An overlap means E can shut off something
X depends on. Overlaps are candidates: verify against saves before warning.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cr2w

from paths import QUEST_ROOT as ROOT


def deactivations(p):
    out = set()
    kids = {}
    for c in p["exports"]:
        kids.setdefault(c["parentID"], []).append(c)
    for e in p["exports"]:
        if e["className"] != "CQuestStoryPhaseSetterBlock":
            continue
        for c in kids.get(e["index"], []):
            if c["className"] == "CDeactivateSpawnset":
                for v in cr2w.props(p, c):
                    if isinstance(v["value"], dict) and "ref_import" in v["value"]:
                        out.add(v["value"]["ref_import"])
    return out


def references(p):
    out = set()
    for e in p["exports"]:
        for v in cr2w.props(p, e):
            if isinstance(v["value"], dict) and "ref_import" in v["value"]:
                out.add(v["value"]["ref_import"])
    return out


def check_pair(e_path, x_path):
    e = cr2w.parse(e_path)
    x = cr2w.parse(x_path)
    d = deactivations(e)
    r = references(x)
    return sorted(d & r), sorted(d), sorted(r)


if __name__ == "__main__":
    if sys.argv[1] == "--find":
        e_path = Path(sys.argv[2])
        d = deactivations(cr2w.parse(e_path))
        for f in sorted(ROOT.rglob("*.w2phase")):
            if f == e_path:
                continue
            try:
                shared = sorted(d & references(cr2w.parse(f)))
            except Exception:
                continue
            if shared:
                print(f.relative_to(ROOT.parent), shared)
    else:
        overlap, d, r = check_pair(Path(sys.argv[1]), Path(sys.argv[2]))
        print(f"E deactivates {len(d)}; X references {len(r)}; overlap {len(overlap)}")
        for o in overlap:
            print("  OVERLAP", o)
