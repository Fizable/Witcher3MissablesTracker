"""Stage `saves`: what actually happened in the player's real saves (the oracle).

Each .sav in the saves folder is read once (read-only) and its quest journal and fact table are
stored in common.SAVES_DB, which is incremental: a save is re-read only when its file name or
mtime changes, and rows for saves that have gone are removed.

The main db then groups the saves into playthroughs and records every change between a save
and the save it continues (journal_transitions, fact_transitions), so a claim such as "finishing quest A
fails quest B" can be checked against what the game recorded.

Playthroughs are trees, not lines, because players reload: each save's parent is the earlier save
whose done set (JS_Success guids) it contains, with at most ABSENT_LIMIT misses; see _group.
Transitions are recorded parent -> child.

Set W3_SAVES_LIMIT=N to build from the newest N saves only (for quick iteration).
"""
import concurrent.futures
import os
import sqlite3
import time

import common  # noqa: F401  (puts tools/ on sys.path and sets the output paths)
import save_reader as sr
import paths

DONE = "JS_Success"
ABSENT_LIMIT = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS saves (
    save_id    INTEGER PRIMARY KEY,
    file       TEXT,        -- save file name, e.g. AutoSave_10083c_7ea4f400_4f30d67.sav
    mtime      REAL,
    kind       TEXT,        -- AutoSave, QuickSave, ManualSave or other (CheckPoint and anything else)
    playthrough INTEGER,    -- NULL when the save could not be read
    seq        INTEGER,     -- 1-based order inside the playthrough
    parent     INTEGER,     -- the save this one continues (see _group); NULL for a playthrough's first save
    n_success  INTEGER,     -- guids with status JS_Success
    error      TEXT         -- why the save could not be read; NULL when it was
);
CREATE INDEX IF NOT EXISTS saves_playthrough ON saves(playthrough, seq);
CREATE TABLE IF NOT EXISTS playthroughs (
    playthrough INTEGER PRIMARY KEY,
    n_saves     INTEGER,
    first_file  TEXT,
    last_file   TEXT,
    first_mtime REAL,
    last_mtime  REAL
);
CREATE TABLE IF NOT EXISTS journal_transitions (
    playthrough INTEGER,
    from_save   INTEGER,
    to_save     INTEGER,
    guid        TEXT,       -- lower-case hex, the save's own byte order
    from_status TEXT,       -- '' when the guid is absent
    to_status   TEXT
);
CREATE INDEX IF NOT EXISTS journal_transitions_guid ON journal_transitions(guid);
CREATE INDEX IF NOT EXISTS journal_transitions_to ON journal_transitions(to_status);
CREATE TABLE IF NOT EXISTS fact_transitions (
    playthrough INTEGER,
    from_save   INTEGER,
    to_save     INTEGER,
    fact        TEXT,
    from_value  INTEGER,    -- first recorded value; NULL when the fact is absent
    to_value    INTEGER
);
CREATE INDEX IF NOT EXISTS fact_transitions_fact ON fact_transitions(fact);
"""

SAVES_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS saves (
    save_id INTEGER PRIMARY KEY,
    file    TEXT UNIQUE,
    mtime   REAL,
    kind    TEXT,
    error   TEXT
);
CREATE TABLE IF NOT EXISTS save_journal (save_id INTEGER, guid TEXT, status TEXT);
CREATE INDEX IF NOT EXISTS save_journal_save ON save_journal(save_id);
CREATE TABLE IF NOT EXISTS save_facts (save_id INTEGER, fact TEXT, value INTEGER, n INTEGER);
CREATE INDEX IF NOT EXISTS save_facts_save ON save_facts(save_id);
"""

NOTE = (
    "Saves form a tree, because players reload. A save's done set is the guids with status JS_Success. "
    "Its parent is the earlier save (by mtime) whose done set it contains with at most 3 misses, choosing "
    "the largest; with no parent it starts a playthrough. Transitions are parent -> child. A guid absent "
    "from a save counts as status ''; a fact absent from a save counts as NULL."
)


def kind_of(name):
    for k in ("AutoSave", "QuickSave", "ManualSave"):
        if name.startswith(k):
            return k
    return "other"


def _read_one(path):
    """Worker (runs in a child process): returns (error, journal rows, fact rows). Read-only."""
    try:
        raw = sr.load_raw(path)
        names = sr.name_table(raw)
        jr = {}
        for e in sr.journal(raw, names):
            if e["guid"]:
                jr[e["guid"]] = e["status"]
        fa = sr.facts(raw)
    except Exception as ex:  # any unreadable save is recorded, not fatal
        return f"{type(ex).__name__}: {ex}", None, None
    return None, list(jr.items()), [(k, v[0] if v else None, len(v)) for k, v in fa.items()]


def _open_saves_db():
    common.OUT.mkdir(parents=True, exist_ok=True)
    sdb = sqlite3.connect(common.SAVES_DB)
    sdb.execute("PRAGMA journal_mode=WAL")
    sdb.execute("PRAGMA synchronous=OFF")
    sdb.executescript(SAVES_DB_SCHEMA)
    return sdb


def _list_saves(limit):
    """(mtime, file name, full path) for every .sav in the saves folder, oldest first."""
    out = []
    with os.scandir(paths.SAVES) as it:
        for de in it:
            if de.is_file() and de.name.lower().endswith(".sav"):
                out.append((os.path.getmtime(de.path), de.name, de.path))
    out.sort()
    return out[-limit:] if limit else out


def _sync(sdb, limit, verbose):
    """Bring the per-save store up to date with the saves folder (incremental)."""
    files = _list_saves(limit)
    present = {name for _, name, _ in files}
    existing = {f: (sid, mt) for sid, f, mt in sdb.execute("SELECT save_id, file, mtime FROM saves")}
    stale = [sid for f, (sid, _) in existing.items() if f not in present]
    todo = []
    for mt, name, path in files:
        e = existing.get(name)
        if e and e[1] == mt:
            continue
        if e:
            stale.append(e[0])
        todo.append((mt, name, path))
    for sid in stale:
        sdb.execute("DELETE FROM save_journal WHERE save_id=?", (sid,))
        sdb.execute("DELETE FROM save_facts WHERE save_id=?", (sid,))
        sdb.execute("DELETE FROM saves WHERE save_id=?", (sid,))
    sdb.commit()
    if verbose:
        print(f"  {len(files)} saves in folder, {len(todo)} to read, {len(stale)} stale rows removed", flush=True)
    if not todo:
        return
    t0 = time.time()
    with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        results = ex.map(_read_one, [p for _, _, p in todo], chunksize=4)
        for i, ((mt, name, _path), (err, jrows, frows)) in enumerate(zip(todo, results), 1):
            cur = sdb.execute("INSERT INTO saves(file, mtime, kind, error) VALUES (?,?,?,?)",
                              (name, mt, kind_of(name), err))
            sid = cur.lastrowid
            if jrows:
                sdb.executemany("INSERT INTO save_journal VALUES (?,?,?)", ((sid, g, s) for g, s in jrows))
            if frows:
                sdb.executemany("INSERT INTO save_facts VALUES (?,?,?,?)", ((sid, f, v, n) for f, v, n in frows))
            if i % 50 == 0 or i == len(todo):
                sdb.commit()
                if verbose:
                    print(f"  {i}/{len(todo)}  {time.time() - t0:.0f}s", flush=True)
    sdb.commit()


def _group(rows, done):
    """Arrange the readable saves as a tree. rows: (save_id, file, mtime, kind, error).

    A player reloads older saves, so a playthrough is not a line: each save's parent is the earlier
    save (by mtime) whose done set it contains, allowing ABSENT_LIMIT misses, with the largest done
    set. A save with no such parent starts a new playthrough; the playthrough is its tree's root.
    Returns ({save_id: (playthrough, seq, parent)}, {playthrough: [save_ids in mtime order]}).
    """
    assign, members, earlier = {}, {}, []
    for sid, _file, _mt, _kind, err in rows:
        if err is not None:
            continue
        d = done.get(sid, set())
        parent = None
        for e in earlier:
            if len(done.get(e, set()) - d) <= ABSENT_LIMIT and (
                    parent is None or len(done.get(e, set())) >= len(done.get(parent, set()))):
                parent = e
        pt = assign[parent][0] if parent is not None else len(members) + 1
        members.setdefault(pt, []).append(sid)
        assign[sid] = (pt, len(members[pt]), parent)
        earlier.append(sid)
    return assign, members


def _oracle(con, sdb, verbose):
    """Fill the main-db oracle tables from the per-save store."""
    for t in ("saves", "playthroughs", "journal_transitions", "fact_transitions"):
        con.execute(f"DELETE FROM {t}")
    rows = sdb.execute("SELECT save_id, file, mtime, kind, error FROM saves ORDER BY mtime, file").fetchall()
    done = {}
    for sid, g in sdb.execute("SELECT save_id, guid FROM save_journal WHERE status=?", (DONE,)):
        done.setdefault(sid, set()).add(g)
    assign, members = _group(rows, done)
    info = {sid: (f, mt) for sid, f, mt, _k, _e in rows}

    for sid, file, mt, kind, err in rows:
        pt, seq, parent = assign.get(sid, (None, None, None))
        n = len(done.get(sid, set())) if err is None else None
        con.execute("INSERT INTO saves VALUES (?,?,?,?,?,?,?,?,?)", (sid, file, mt, kind, pt, seq, parent, n, err))

    for pt, ms in members.items():
        first, last = ms[0], ms[-1]
        con.execute("INSERT INTO playthroughs VALUES (?,?,?,?,?,?)",
                    (pt, len(ms), info[first][0], info[last][0], info[first][1], info[last][1]))

    cache = {}

    def state(sid):
        if sid not in cache:
            if len(cache) > 64:
                cache.clear()
            cache[sid] = (dict(sdb.execute("SELECT guid, status FROM save_journal WHERE save_id=?", (sid,))),
                          dict(sdb.execute("SELECT fact, value FROM save_facts WHERE save_id=?", (sid,))))
        return cache[sid]

    jt = ft = 0
    for sid, _file, _mt, _kind, err in rows:
        if err is not None or assign[sid][2] is None:
            continue
        pt, _seq, psid = assign[sid]
        pj, pf = state(psid)
        jmap, fmap = state(sid)
        jrows = [(pt, psid, sid, g, pj.get(g, ""), jmap.get(g, ""))
                 for g in pj.keys() | jmap.keys() if pj.get(g, "") != jmap.get(g, "")]
        frows = [(pt, psid, sid, f, pf.get(f), fmap.get(f))
                 for f in pf.keys() | fmap.keys() if pf.get(f) != fmap.get(f)]
        con.executemany("INSERT INTO journal_transitions VALUES (?,?,?,?,?,?)", jrows)
        con.executemany("INSERT INTO fact_transitions VALUES (?,?,?,?,?,?)", frows)
        jt += len(jrows)
        ft += len(frows)

    con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", ("saves:note", NOTE))
    n_err = sum(1 for r in rows if r[4] is not None)
    if verbose:
        print(f"  {len(rows)} saves ({n_err} unreadable), {len(members)} playthroughs, "
              f"{jt} journal transitions, {ft} fact transitions", flush=True)


def build(con, verbose=True):
    limit = int(os.environ.get("W3_SAVES_LIMIT") or 0)
    if verbose and limit:
        print(f"  W3_SAVES_LIMIT={limit}: newest {limit} saves only", flush=True)
    sdb = _open_saves_db()
    try:
        _sync(sdb, limit, verbose)
        _oracle(con, sdb, verbose)
        sdb.commit()
    finally:
        sdb.close()
