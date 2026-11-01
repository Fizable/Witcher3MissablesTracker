"""Shared helpers for the game database builders.

Every builder module in this package exposes:

    SCHEMA: str          CREATE TABLE / CREATE INDEX statements for the tables it owns
    build(con, verbose)  fills those tables; never touches another module's tables

Paths come from tools/paths.py, so the environment variables documented there apply here too.
Read-only against the game, REDkit and the saves: the only files written are under OUT.
"""
import os
import sqlite3
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import cr2w  # noqa: E402
import paths  # noqa: E402

R4 = paths.REDKIT_R4
OUT = Path(os.environ.get("W3_GAMEDB_OUT", str(paths.TRACKER / "db")))
DB = OUT / "w3db.sqlite"
SAVES_DB = OUT / "w3saves.sqlite"


def rel(p):
    """REDkit-relative path, forward slashes, lower case: the key every table uses for a file."""
    return Path(p).resolve().relative_to(R4.resolve()).as_posix().lower()


def pack_of(relpath):
    """'base', 'ep1' (Hearts of Stone), 'bob' (Blood and Wine) or 'dlcN' for a REDkit-relative path."""
    parts = relpath.split("/")
    if parts[0] == "dlc" and len(parts) > 1:
        return parts[1]
    return "base"


def connect(path=DB):
    OUT.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=OFF")
    return con


def file_id(con, relpath, kind, size=None, version=None, error=None):
    """Row id in `files` for a REDkit-relative path, inserting it on first sight."""
    row = con.execute("SELECT file_id FROM files WHERE path=?", (relpath,)).fetchone()
    if row:
        if error is not None or version is not None:
            con.execute("UPDATE files SET cr2w_version=COALESCE(?, cr2w_version), error=COALESCE(?, error) "
                        "WHERE file_id=?", (version, error, row[0]))
        return row[0]
    cur = con.execute("INSERT INTO files(path, kind, pack, size, cr2w_version, error) VALUES (?,?,?,?,?,?)",
                      (relpath, kind, pack_of(relpath), size, version, error))
    return cur.lastrowid


FILES_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    file_id      INTEGER PRIMARY KEY,
    path         TEXT UNIQUE NOT NULL,   -- REDkit r4data-relative, forward slashes, lower case
    kind         TEXT NOT NULL,          -- extension without the dot: w2phase, w2quest, journal, xml, w2scene
    pack         TEXT NOT NULL,          -- base, ep1, bob, dlcN
    size         INTEGER,
    cr2w_version INTEGER,
    error        TEXT                    -- why the file could not be read; NULL when it was
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""
