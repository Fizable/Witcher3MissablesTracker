"""Where the toolchain looks for things. Read the rest of this file once if you are on another machine.

Every path can be overridden with an environment variable, so nothing here is tied to one install:

  W3_GAME_DIR     the game install (same variable the Rust side's index test uses)
  W3_REDKIT_DIR   the REDkit r4data folder (game files to read the quest graphs from)
  W3_SAVES_DIR    your saves folder (read-only, ever)
  W3_TRACKER_DIR  the tracker repo root (for data/route.json)
  W3_QDB          quest_db.json: the journal-file index the tracker's own build also produces.
                  Only needed for the old-vs-new comparisons; defaults to the research copy.
  W3_STRINGDB     REDkit's LocalEditorStringDataBaseW3_UTF8.db: the game's own text for every
                  resource and property, including quest-log text and dialogue choices.
"""
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent

GAME = Path(os.environ.get("W3_GAME_DIR", r"C:\Steam\steamapps\common\The Witcher 3"))
REDKIT_R4 = Path(os.environ.get("W3_REDKIT_DIR", r"F:\SteamLibrary\steamapps\common\The Witcher 3 REDkit\r4data"))
SAVES = Path(os.environ.get("W3_SAVES_DIR", r"C:\Users\Desktop-Isac\Documents\The Witcher 3\gamesaves"))
TRACKER = Path(os.environ.get("W3_TRACKER_DIR", str(HERE.parent)))
QDB = Path(os.environ.get("W3_QDB", str(GAME / "w3check" / "quest_db.json")))
STRING_DB = Path(os.environ.get("W3_STRINGDB", str(REDKIT_R4 / "LocalEditorStringDataBaseW3_UTF8.db")))

QUEST_ROOT = REDKIT_R4 / "quests"
JOURNAL_DIR = REDKIT_R4 / "gameplay" / "journal" / "quests"

ROUTE = TRACKER / "data" / "route.json"


def missing():
    """(name, path) for every path that is not there, so a script can say so plainly."""
    for name, p in (("game", GAME), ("redkit r4data", REDKIT_R4), ("saves", SAVES),
                    ("quest_db.json", QDB), ("route.json", ROUTE), ("string database", STRING_DB)):
        if not p.exists():
            yield name, p
