"""The game's own text, straight from REDkit's string database.

`LocalEditorStringDataBaseW3_UTF8.db` is a SQLite database that ships with the game's
editor data. Every row maps a resource + property to its text in 18 languages:

    STRING_INFO(STRING_ID, RESOURCE, PROPERTY_NAME, VOICEOVER_NAME, STRING_KEY)
    STRINGS(STRING_ID, LANG, VERSION, TEXT)

RESOURCE is `CClassName "depot\\path"`, and PROPERTY_NAME is what part of the resource
the string belongs to: 'Line text' and 'Choice line' for story scenes, journal text for
the quest log (see `journal`). The IDs are the same numbers the resources carry: a
`CStorySceneChoiceLine.choiceLine` locId (for example 504749) is a STRING_ID here, so a
choice read out of a scene resolves to the exact words the game shows.

Read-only, always: the database is opened immutable.

  py stringsdb.py info                       what is in it
  py stringsdb.py journal <journal file>     the quest log text of one .journal (any name fragment)
  py stringsdb.py journallist [--all]        every journal resource that has text
  py stringsdb.py scene <name fragment>      the lines and choices of one scene
  py stringsdb.py locid <id> [...]           the text of one or more string ids
  py stringsdb.py find <substring> [limit]   search every English string
"""
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import STRING_DB

EN = 2  # LANGUAGES: 1 PL, 2 EN, 3 DE, ...


def con(path=None):
    """A read-only connection. Any error says what is missing rather than failing inside sqlite3."""
    p = Path(path) if path else STRING_DB
    if not p.exists():
        raise SystemExit(f"string database not found: {p}\nset W3_STRINGDB to LocalEditorStringDataBaseW3_UTF8.db")
    return sqlite3.connect(f"file:{p}?mode=ro&immutable=1", uri=True)


def path_of(resource):
    """'CJournalQuest "gameplay\\journal\\quests\\q203_him.journal"' -> the path inside the quotes."""
    if not resource:
        return ""
    q = resource.find('"')
    return resource[q + 1:-1] if q >= 0 else resource


def cls_of(resource):
    """'CStoryScene "quests\\...\\x.w2scene"' -> 'CStoryScene'."""
    return resource.split(" ", 1)[0] if resource else ""


def loc(locid, conn=None, lang=EN):
    """The English text of one string id, or '' when the database does not have it."""
    c = conn or con()
    r = c.execute("select TEXT from STRINGS where STRING_ID=? and LANG=?", (int(locid), lang)).fetchone()
    if r and r[0]:
        return r[0]
    # some ids only exist in the source language
    r = c.execute("select TEXT from STRINGS where STRING_ID=? order by LANG", (int(locid),)).fetchone()
    return (r[0] or "") if r else ""


def locs(locids, conn=None, lang=EN):
    """{locid: text} for many ids at once."""
    c = conn or con()
    out = {}
    ids = [int(i) for i in locids]
    for i in range(0, len(ids), 400):
        chunk = ids[i:i + 400]
        q = "select STRING_ID, TEXT from STRINGS where LANG=? and STRING_ID in (%s)" % ",".join("?" * len(chunk))
        for sid, text in c.execute(q, [lang] + chunk):
            out[sid] = text or ""
        missing = [x for x in chunk if x not in out]
        if missing:
            q2 = "select STRING_ID, TEXT from STRINGS where STRING_ID in (%s)" % ",".join("?" * len(missing))
            for sid, text in c.execute(q2, missing):
                out.setdefault(sid, text or "")
    return out


def journal_text(fragment, conn=None):
    """The quest log text of a journal resource: [(property, text)] for a name fragment like 'q203_him'."""
    c = conn or con()
    frag = fragment.lower().replace(".journal", "")
    rows = c.execute(
        """select si.RESOURCE, si.PROPERTY_NAME, s.TEXT
           from STRING_INFO si join STRINGS s on s.STRING_ID = si.STRING_ID and s.LANG = ?
           where si.RESOURCE like '%journal"%' and lower(si.RESOURCE) like ?
           order by si.STRING_ID""",
        (EN, f"%{frag}%"),
    ).fetchall()
    return [(path_of(r[0]), r[1], r[2] or "") for r in rows]


def scene_text(fragment, conn=None):
    """Every line and choice of one story scene, in file order: [(locid, property, text)]."""
    c = conn or con()
    rows = c.execute(
        """select si.STRING_ID, si.RESOURCE, si.PROPERTY_NAME, s.TEXT
           from STRING_INFO si join STRINGS s on s.STRING_ID = si.STRING_ID and s.LANG = ?
           where lower(si.RESOURCE) like ? and si.PROPERTY_NAME in ('Line text','Choice line')
           order by si.STRING_ID""",
        (EN, f"%{fragment.lower()}%"),
    ).fetchall()
    return [(r[0], r[2], r[3] or "") for r in rows]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    c = con()
    if cmd == "info":
        for name, sql in c.execute("select name, sql from sqlite_master where type='table'"):
            print(name, ":", sql)
        print("rows:", c.execute("select count(*) from STRING_INFO").fetchone()[0], "string_info,",
              c.execute("select count(*) from STRINGS").fetchone()[0], "strings")
        print("\nresource kinds:")
        for e, n in c.execute("""select case when instr(RESOURCE,'"')>0
                                   then replace(substr(RESOURCE, instr(RESOURCE,' ')+2), ' '||quote(''), '')
                                   else RESOURCE end, count(*) from STRING_INFO group by 1 order by 2 desc limit 5"""):
            print("  ", e, n)
        print("\nby class:")
        for e, n in c.execute("select substr(RESOURCE,1,instr(RESOURCE,' ')-1), count(*) from STRING_INFO group by 1 order by 2 desc limit 12"):
            print(f"   {e:24s} {n}")
    elif cmd == "journal":
        for res, prop, text in journal_text(sys.argv[2], c):
            print(f"{prop:22s} {text}")
    elif cmd == "journallist":
        seen = {}
        for sid, res in c.execute("""select STRING_ID, RESOURCE from STRING_INFO where RESOURCE like '%journal"%'"""):
            seen.setdefault(path_of(res), 0)
            seen[path_of(res)] += 1
        for k in sorted(seen):
            print(f"{seen[k]:4d}  {k}")
        print(len(seen), "journal resources")
    elif cmd == "scene":
        for locid, prop, text in scene_text(sys.argv[2], c):
            print(f"{locid:8d} {prop:12s} {text}")
    elif cmd == "locid":
        m = locs(sys.argv[2:], c)
        for i in sys.argv[2:]:
            print(f"{i:>9s}  {m.get(int(i), '')}")
    elif cmd == "find":
        needle = sys.argv[2]
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 20
        for sid, res, prop, text in c.execute(
            """select si.STRING_ID, si.RESOURCE, si.PROPERTY_NAME, s.TEXT
               from STRING_INFO si join STRINGS s on s.STRING_ID=si.STRING_ID and s.LANG=?
               where s.TEXT like ? limit ?""", (EN, f"%{needle}%", limit)):
            print(f"{sid:8d} {cls_of(res):22s} {prop:12s} {str(text)[:120]}")


if __name__ == "__main__":
    main()
