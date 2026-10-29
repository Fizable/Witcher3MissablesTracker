"""The one set of game roots the quest readers use.

REDkit ships the base game under `r4data\\quests` and every expansion/free DLC under
`r4data\\dlc\\<pack>\\data`. The bundles carry the same resources (the DLC probe measured 2229
unique paths, all already present in REDkit), so this module never reads a bundle: it returns the
REDkit files, one copy per virtual path, with the DLC pack as a first-class root rather than an
overlay.

The DLC-scoped filters stay here too, so the index and the coverage generator cannot disagree about
which root a file came from:

  phase_files()    every quest `.w2phase`, base plus DLC, without living-world POIs
  journal_files()  every `.journal` in a `journal\\quests` folder, base plus DLC
  is_dlc_path()    a resource under `r4data\\dlc`
  is_dlc_journal() a journal's relative path under `dlc\\`
  pack_of_journal() base / ep1 / bob / other_dlc, from the journal path

`gwent` is a content pack in coverage.json, not a quest-file root: its cards and decks live in the
gameplay XML, and its route steps are journalled by the base/B&W packs.
"""
from pathlib import Path

from paths import QUEST_ROOT, REDKIT_R4

DLC_ROOT = REDKIT_R4 / "dlc"
PACKS = ("base", "ep1", "bob", "other_dlc", "gwent")


def dlc_data_roots():
    """One root per DLC pack that ships a `data` tree, in stable order."""
    if not DLC_ROOT.is_dir():
        return []
    return sorted(p / "data" for p in DLC_ROOT.iterdir() if (p / "data").is_dir())


def phase_roots():
    """The base quest root followed by every DLC data root."""
    return [QUEST_ROOT, *dlc_data_roots()]


def phase_files():
    """Every quest phase file, base plus DLC, deduplicated and sorted.

    DLC living-world phases are POIs and prefab encounters, not route quests. They are excluded
    here, the same rule the index has used since the DLC attribution fix. A phase that appears
    under more than one root is returned once.
    """
    out = set()
    for root in phase_roots():
        for path in root.rglob("*.w2phase"):
            if root != QUEST_ROOT and "living_world" in {part.lower() for part in path.parts}:
                continue
            out.add(path)
    return sorted(out)


def journal_files():
    """Every `.journal` in a `journal\\quests` folder, base plus DLC, deduplicated and sorted."""
    roots = [p for p in REDKIT_R4.rglob("journal") if p.is_dir() and (p / "quests").is_dir()]
    return sorted({jf for root in roots for jf in (root / "quests").rglob("*.journal")})


def is_dlc_path(path):
    """True for a resource under `r4data/dlc`, false for the base game."""
    try:
        Path(path).relative_to(DLC_ROOT)
        return True
    except ValueError:
        return False


def is_dlc_journal(value):
    """True when a journal's relative file path starts with the DLC tree."""
    return str(value).lower().replace("/", "\\").startswith("dlc\\")


def pack_of_journal(value):
    """The coverage pack a journal path belongs to."""
    path = str(value or "").lower().replace("/", "\\")
    if path.startswith("dlc\\ep1\\"):
        return "ep1"
    if path.startswith("dlc\\bob\\"):
        return "bob"
    if path.startswith("dlc\\"):
        return "other_dlc"
    return "base"
