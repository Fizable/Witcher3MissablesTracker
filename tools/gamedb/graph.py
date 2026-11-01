"""Stage `graph`: the quest phase graphs in every .w2phase and .w2quest under REDkit.

A CQuestGraph export holds blocks (exports whose parentID is the graph). Other exports (conditions,
spawnsets, AI actions) hang below a block. Sockets and CGraphConnection exports become block-to-block
edges, and every ref_import / CJournalPath reference is kept per export with its owner block.
Read-only against the game: the only writes go to the graph_* tables and the shared `files` table.
"""
import json
from pathlib import Path

import common
import cr2w

GRAPH = "CQuestGraph"
SOCKET_CLASSES = frozenset({"CQuestGraphSocket", "CGraphSocket", "CQuestCutControlGraphSocket"})
CONNECTION = "CGraphConnection"
JOURNAL_PATH = "CJournalPath"
NOT_NODES = SOCKET_CLASSES | {CONNECTION, JOURNAL_PATH}
SKIP_PROPS = frozenset({"position", "sockets"})
LABEL_KEYS = ("comment", "name", "caption", "factID", "factId")
MAX_CHAIN = 12
FILES_PER_COMMIT = 50
PROGRESS_EVERY = 100

SCHEMA = """
CREATE TABLE IF NOT EXISTS graph_nodes (
    file_id      INTEGER,
    idx          INTEGER,
    class        TEXT,
    parent_idx   INTEGER,
    graph_idx    INTEGER,
    owner_block  INTEGER,
    is_block     INTEGER,
    label        TEXT,
    guid         TEXT,
    props_json   TEXT,
    PRIMARY KEY(file_id, idx)
);
CREATE INDEX IF NOT EXISTS graph_nodes_class ON graph_nodes(class);
CREATE INDEX IF NOT EXISTS graph_nodes_owner ON graph_nodes(file_id, owner_block);
CREATE TABLE IF NOT EXISTS graph_sockets (
    file_id      INTEGER,
    socket_idx   INTEGER,
    block_idx    INTEGER,
    name         TEXT,
    direction    TEXT,
    PRIMARY KEY(file_id, socket_idx)
);
CREATE INDEX IF NOT EXISTS graph_sockets_block ON graph_sockets(file_id, block_idx);
CREATE TABLE IF NOT EXISTS graph_edges (
    file_id      INTEGER,
    src_block    INTEGER,
    src_socket   TEXT,
    dst_block    INTEGER,
    dst_socket   TEXT,
    UNIQUE(file_id, src_block, src_socket, dst_block, dst_socket)
);
CREATE INDEX IF NOT EXISTS graph_edges_dst ON graph_edges(file_id, dst_block);
CREATE INDEX IF NOT EXISTS graph_edges_src ON graph_edges(file_id, src_block);
CREATE TABLE IF NOT EXISTS graph_refs (
    file_id      INTEGER,
    idx          INTEGER,
    owner_block  INTEGER,
    prop         TEXT,
    ref_path     TEXT,
    ref_class    TEXT
);
CREATE INDEX IF NOT EXISTS graph_refs_path ON graph_refs(ref_path);
CREATE TABLE IF NOT EXISTS graph_journal_refs (
    file_id      INTEGER,
    idx          INTEGER,
    owner_block  INTEGER,
    prop         TEXT,
    resource     TEXT,
    guid_chain   TEXT,
    leaf_guid    TEXT
);
CREATE INDEX IF NOT EXISTS graph_journal_refs_leaf ON graph_journal_refs(leaf_guid);
CREATE INDEX IF NOT EXISTS graph_journal_refs_resource ON graph_journal_refs(resource);
"""

INSERT = {
    "graph_nodes": "INSERT OR REPLACE INTO graph_nodes VALUES (?,?,?,?,?,?,?,?,?,?)",
    "graph_sockets": "INSERT OR REPLACE INTO graph_sockets VALUES (?,?,?,?,?)",
    "graph_edges": "INSERT OR IGNORE INTO graph_edges VALUES (?,?,?,?,?)",
    "graph_refs": "INSERT INTO graph_refs VALUES (?,?,?,?,?,?)",
    "graph_journal_refs": "INSERT INTO graph_journal_refs VALUES (?,?,?,?,?,?,?)",
}


def _jsonable(o):
    if isinstance(o, (bytes, bytearray)):
        return bytes(o).hex()
    return str(o)


def _str(v):
    return v if isinstance(v, str) else None


def _norm(path):
    return path.replace("\\", "/").lower()


def _chunk(v):
    """The export index a ref_chunk points at, or None."""
    if isinstance(v, dict) and isinstance(v.get("ref_chunk"), int):
        return v["ref_chunk"]
    return None


def _guid(pd):
    g = pd.get("guid")
    if isinstance(g, dict) and isinstance(g.get("raw_hex"), str):
        return g["raw_hex"].lower()
    return None


def _label(pd):
    for k in LABEL_KEYS:
        v = pd.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _collect(value, prefix, out):
    """Append (dotted_prop_path, ref_dict) for every ref_import / ref_chunk dict under a property value."""
    if isinstance(value, dict):
        if "ref_import" in value or "ref_chunk" in value:
            out.append((prefix, value))
            return
        for v in value.values():
            _collect(v, prefix, out)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and {"name", "type", "value"} <= item.keys():
                child = f"{prefix}.{item['name']}" if prefix else str(item["name"])
                _collect(item["value"], child, out)
            else:
                _collect(item, prefix, out)


def _follow(start, cls, pdict):
    """Walk a CJournalPath chain from `start` to its leaf: (last resource, [guids root..leaf])."""
    res, guids, seen, i = None, [], set(), start
    for _ in range(MAX_CHAIN):
        if cls.get(i) != JOURNAL_PATH or i in seen:
            break
        seen.add(i)
        pd = pdict[i]
        r = pd.get("resource")
        if isinstance(r, dict):
            r = r.get("ref_import")
        if isinstance(r, str) and r.strip():
            res = _norm(r.strip())
        g = _guid(pd)
        if g:
            guids.append(g)
        i = _chunk(pd.get("child"))
    return res, guids


def _process(con, path, buf, stats):
    relpath = common.rel(path)
    kind = path.suffix.lower().lstrip(".")
    size = path.stat().st_size
    try:
        parsed = cr2w.parse(path)
    except Exception as exc:
        common.file_id(con, relpath, kind, size, None, str(exc) or type(exc).__name__)
        stats["error_files"].append(relpath)
        return
    fid = common.file_id(con, relpath, kind, size, parsed["version"])

    n = len(parsed["exports"])
    cls, parent, plists, pdict = {}, {}, {}, {}
    for e in parsed["exports"]:
        i = e["index"]
        cls[i] = e["className"]
        parent[i] = e["parentID"]
        try:
            plist = cr2w.props(parsed, e)
        except Exception:
            plist = []
            stats["decode_failures"] += 1
        plists[i] = plist
        pdict[i] = {p["name"]: p["value"] for p in plist}

    def ancestors(i):
        seen = {i}
        p = parent[i]
        while 1 <= p <= n and p not in seen:
            seen.add(p)
            yield p
            p = parent[p]

    is_block = {i: cls.get(parent[i]) == GRAPH for i in cls}
    graph_of, owner_of = {}, {}
    for i in cls:
        anc = list(ancestors(i))
        graph_of[i] = next((a for a in anc if cls[a] == GRAPH), None)
        owner_of[i] = i if is_block[i] else next((a for a in anc if is_block[a]), None)

    for i, c in cls.items():
        if c in NOT_NODES:
            continue
        pd = pdict[i]
        p = parent[i]
        props_json = json.dumps({k: v for k, v in pd.items() if k not in SKIP_PROPS}, default=_jsonable)
        buf["graph_nodes"].append((fid, i, c, p if 1 <= p <= n else None, graph_of[i], owner_of[i],
                                   int(is_block[i]), _label(pd), _guid(pd), props_json))

    socks = {}
    for i, c in cls.items():
        if c not in SOCKET_CLASSES:
            continue
        pd = pdict[i]
        blk = _chunk(pd.get("block"))
        name, direction = _str(pd.get("name")), _str(pd.get("direction"))
        socks[i] = (blk, name, direction)
        buf["graph_sockets"].append((fid, i, blk, name, direction))

    for i, c in cls.items():
        if c != CONNECTION:
            continue
        s = _chunk(pdict[i].get("source"))
        d = _chunk(pdict[i].get("destination"))
        if s not in socks or d not in socks:
            stats["skipped_edges"] += 1
            continue
        sb, sn, sd = socks[s]
        db, dn, dd = socks[d]
        if sb is None or db is None:
            stats["skipped_edges"] += 1
            continue
        # input sockets carry no direction prop at all (only outputs say LSD_Output), and every
        # connection is stored once on each of its two sockets, so half arrive input->output
        if sd != "LSD_Output" and dd == "LSD_Output":
            sb, sn, db, dn = db, dn, sb, sn
        buf["graph_edges"].append((fid, sb, sn, db, dn))

    for i, c in cls.items():
        if c == JOURNAL_PATH:
            continue
        hits = []
        for p in plists[i]:
            _collect(p["value"], p["name"], hits)
        for prop, d in hits:
            if "ref_import" in d:
                ref = _str(d["ref_import"])
                if ref:
                    buf["graph_refs"].append((fid, i, owner_of[i], prop, _norm(ref),
                                              _str(d.get("ref_class")) or None))
            else:
                target = d["ref_chunk"]
                if cls.get(target) == JOURNAL_PATH:
                    res, guids = _follow(target, cls, pdict)
                    buf["graph_journal_refs"].append((fid, i, owner_of[i], prop, res, json.dumps(guids),
                                                      guids[-1] if guids else None))


def _flush(con, buf):
    for table, rows in buf.items():
        if rows:
            con.executemany(INSERT[table], rows)
            rows.clear()


def build(con, verbose=True):
    root = Path(common.R4)
    files = sorted(set(root.rglob("*.w2phase")) | set(root.rglob("*.w2quest")))
    buf = {t: [] for t in INSERT}
    stats = {"error_files": [], "decode_failures": 0, "skipped_edges": 0}
    total = len(files)
    for k, path in enumerate(files, 1):
        _process(con, path, buf, stats)
        if k % FILES_PER_COMMIT == 0 or k == total:
            _flush(con, buf)
            con.commit()
        if verbose and k % PROGRESS_EVERY == 0:
            print(f"  {k}/{total} files", flush=True)
    if verbose:
        for t in INSERT:
            print(f"  {t}: {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]} rows")
        print(f"  {total} files, {len(stats['error_files'])} with parse errors, "
              f"{stats['decode_failures']} exports undecodable, {stats['skipped_edges']} connections skipped")
        for r in stats["error_files"]:
            print(f"    error: {r}")
