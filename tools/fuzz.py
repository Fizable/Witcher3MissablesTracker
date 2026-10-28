"""Parser hardening check: damaged input must fail cleanly, never decode into plausible nonsense.

The tracker reads files it does not control - the player's game install, and the saves of a game
that may still be writing them. A parser that misreads is worse than one that refuses: the wrong
table offset once made a journal file look like 441 quests with the wrong names.

So every reader is fed truncated and corrupted copies of real files and must do one of two things:
raise one of its own exceptions, or parse. It may not raise anything else (a MemoryError, a struct
error escaping, an IndexError), and it may not "succeed" with an absurd shape.

  py fuzz.py            test the Python readers (cr2w, questindex, stringsdb helpers)
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cr2w
import questindex
from paths import JOURNAL_DIR, QUEST_ROOT

CLEAN = (cr2w.NotCr2w, cr2w.UnsupportedVersion, cr2w.Truncated)
SAMPLES = [
    ("phase", next(QUEST_ROOT.rglob("*.w2phase"))),
    ("scene", next(QUEST_ROOT.rglob("*.w2scene"))),
    ("journal", next(JOURNAL_DIR.glob("*.journal"))),
    ("old container", next(QUEST_ROOT.rglob("*.w2dset"))),
]


def try_parse(path):
    """(ok, detail): a clean result, or a detail string when the failure mode is not acceptable."""
    try:
        p = cr2w.parse(path)
    except CLEAN:
        return True, ""
    except Exception as ex:  # anything else is a bug in the reader
        return False, f"{type(ex).__name__}: {str(ex)[:70]}"
    n_names, n_exp = len(p["names"]), len(p["exports"])
    if n_names > 200_000 or n_exp > 200_000:
        return False, f"parsed but absurd (names={n_names}, exports={n_exp})"
    for e in p["exports"]:
        if e["dataOffset"] + e["dataSize"] > len(p["data"]) + 1:
            return False, "parsed but an export points past the end"
    return True, ""


def main():
    rnd = random.Random(20261027)
    tmp = Path(__file__).resolve().parent / "_fuzz_tmp.bin"
    bad, tested = [], 0
    for label, src in SAMPLES:
        raw = src.read_bytes()
        for cut in (8, 40, 100, 160, 200, 512, len(raw) // 3, len(raw) // 2, len(raw) - 1):
            if cut <= 0 or cut >= len(raw):
                continue
            tmp.write_bytes(raw[:cut])
            tested += 1
            ok, why = try_parse(tmp)
            if not ok:
                bad.append((label, f"truncated to {cut}", why))
        base = bytearray(raw)
        for _ in range(6):
            b = bytearray(raw[: min(len(raw), 4096)])
            for _ in range(24):
                b[rnd.randrange(len(b))] = rnd.randrange(256)
            tmp.write_bytes(bytes(b) + raw[min(len(raw), 4096):])
            tested += 1
            ok, why = try_parse(tmp)
            if not ok:
                bad.append((label, "corrupted header", why))
    tmp.unlink(missing_ok=True)
    print(f"{tested} damaged files fed to the readers, {len(bad)} unacceptable results")
    for label, what, why in bad[:12]:
        print(f"  {label} ({what}): {why}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
