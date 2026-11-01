"""Stage `strings`: every English string the editor string database has, keyed by locId.

A locId in any CR2W property (`{"locId": n}`) or an XML localisation key resolves here.
"""
import stringsdb
from common import R4  # noqa: F401  (paths are set up by importing common)

SCHEMA = """
CREATE TABLE IF NOT EXISTS strings (
    loc_id    INTEGER PRIMARY KEY,
    text      TEXT,       -- English (LANG 2), newest VERSION
    key       TEXT,       -- STRING_KEY, used by XML item and UI definitions
    resource  TEXT,       -- the owning resource as the editor names it, e.g. CJournalQuest "gameplay\\journal\\..."
    property  TEXT        -- which part of the resource: 'Line text', 'Choice line', journal title, ...
);
CREATE INDEX IF NOT EXISTS strings_key ON strings(key);
"""


def build(con, verbose=True):
    src = stringsdb.con()
    rows = src.execute(
        """
        SELECT i.STRING_ID, s.TEXT, NULLIF(TRIM(i.STRING_KEY), ''), i.RESOURCE, i.PROPERTY_NAME
        FROM STRING_INFO i
        LEFT JOIN (SELECT STRING_ID, TEXT, MAX(VERSION) FROM STRINGS WHERE LANG = ? GROUP BY STRING_ID) s
               ON s.STRING_ID = i.STRING_ID
        """,
        (stringsdb.EN,),
    )
    con.executemany("INSERT OR REPLACE INTO strings VALUES (?,?,?,?,?)", rows)
    n = con.execute("SELECT COUNT(*), COUNT(text) FROM strings").fetchone()
    if verbose:
        print(f"  {n[0]} strings, {n[1]} with English text")
