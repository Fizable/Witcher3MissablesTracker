"""Stage `journal`: every CJournal* export in every REDkit .journal file (base game and DLC).

A .journal is a CR2W resource whose exports form a tree through parentID (1-based export index, 0 = none):
CJournalResource -> CJournalQuest -> CJournalQuestPhase -> CJournalQuestObjective -> CJournalQuestMapPin,
with description groups beside them, and the bestiary, characters, glossary, tutorials, story book and
places files built from the same classes. GUIDs are stored as the lower-case raw hex the resource and the
saves use (never reformatted). Text is stored as locIds only; the strings themselves come from `strings`.
"""
import json
from collections import defaultdict
from pathlib import Path

import cr2w
import common

SCHEMA = """
CREATE TABLE IF NOT EXISTS journal_entries (
    file_id       INTEGER,
    idx           INTEGER,    -- 1-based export index inside the file
    guid          TEXT,       -- lower-case raw hex; NULL when the export has no guid
    class         TEXT,       -- CJournalQuest, CJournalQuestObjective, CJournalCreature, ...
    parent_idx    INTEGER,    -- parent export index, 0 = none
    parent_guid   TEXT,       -- guid of the nearest ancestor that has one
    root_guid     TEXT,       -- guid of the topmost ancestor that has one (own guid when no ancestor does)
    base_name     TEXT,
    ord           INTEGER,    -- the order prop; 1-based position among siblings when there is none
    title_loc_id  INTEGER,    -- locId of title, else name, text, caption
    desc_loc_id   INTEGER,    -- locId of description
    props_json    TEXT,       -- every property of the export: {name: decoded value}
    PRIMARY KEY (file_id, idx)
);
CREATE INDEX IF NOT EXISTS journal_entries_guid  ON journal_entries(guid);
CREATE INDEX IF NOT EXISTS journal_entries_root  ON journal_entries(root_guid);
CREATE INDEX IF NOT EXISTS journal_entries_class ON journal_entries(class);

CREATE TABLE IF NOT EXISTS journal_quests (
    guid          TEXT PRIMARY KEY,   -- the CJournalQuest guid, lower-case raw hex
    file_id       INTEGER,
    stem          TEXT,               -- file name without extension, lower case
    title_loc_id  INTEGER,
    type          TEXT,               -- Chapter, Side, MonsterHunt, TreasureHunt, ...
    content_type  TEXT,               -- EJCT_EP1, EJCT_EP2, ... when set
    world         TEXT,
    ord           INTEGER,
    base_name     TEXT,
    category      TEXT                -- 'quest' for journal/quests/, else the folder under journal/
);

CREATE TABLE IF NOT EXISTS journal_objectives (
    guid          TEXT,               -- CJournalQuestObjective guid
    quest_guid    TEXT,               -- guid of the nearest CJournalQuest ancestor
    phase_guid    TEXT,               -- guid of the nearest CJournalQuestPhase ancestor
    file_id       INTEGER,
    base_name     TEXT,
    title_loc_id  INTEGER,
    ord           INTEGER,            -- the order prop; 1-based position among siblings when there is none
    counter       INTEGER,            -- the count prop (or counter), NULL when absent
    is_mandatory  INTEGER,            -- isMandatory prop as 0/1, NULL when absent
    pins          INTEGER             -- number of CJournalQuestMapPin children
);
CREATE INDEX IF NOT EXISTS journal_objectives_quest ON journal_objectives(quest_guid);
"""

TITLE_PROPS = ("title", "name", "text", "caption")   # in priority order
COUNTER_PROPS = ("count", "counter")


def _loc(v):
    if isinstance(v, dict) and isinstance(v.get("locId"), int) and not isinstance(v.get("locId"), bool):
        return v["locId"]
    return None


def _guid(v):
    if isinstance(v, dict) and isinstance(v.get("raw_hex"), str) and v["raw_hex"]:
        return v["raw_hex"].lower()
    return None


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _category(relpath):
    """'quest' under journal/quests/, else the folder after 'journal/' (characters, bestiary, ...)."""
    if "/journal/quests/" in "/" + relpath:
        return "quest"
    parts = relpath.split("/")
    if "journal" in parts:
        i = parts.index("journal")
        if i + 2 < len(parts):          # journal/<folder>/<file>
            return parts[i + 1]
    return "journal"


def _props_json(pairs):
    out = {}
    for name, value in pairs:
        key, n = name, 2
        while key in out:               # a repeated prop name keeps every value
            key = f"{name}#{n}"
            n += 1
        out[key] = value
    return json.dumps(out, ensure_ascii=False, default=str)


def _decode_file(jf):
    """Parse one journal and decode every export once. Returns (version, exports, pairs-per-export)."""
    p = cr2w.parse(jf)
    exports = p["exports"]
    pairs = {}
    for e in exports:
        pairs[e["index"]] = [(v["name"], v["value"]) for v in cr2w.props(p, e)]
    return p["version"], exports, pairs


def _file_rows(fid, relpath, exports, pairs, missing):
    """Rows for one decoded file: (entries, quests, objectives). Pure: touches no database.
    A CJournalQuest without a guid is not returned; its location is appended to `missing`."""
    by_idx = {e["index"]: e for e in exports}
    pmap, guid = {}, {}
    for i, pl in pairs.items():
        pm = {}
        for name, value in pl:
            pm.setdefault(name, value)  # first occurrence wins for the typed lookups
        pmap[i] = pm
        guid[i] = _guid(pm.get("guid"))

    kids = defaultdict(list)
    for e in exports:
        kids[e["parentID"]].append(e["index"])
    pos = {}
    for lst in kids.values():
        for n, i in enumerate(lst, 1):
            pos[i] = n

    def ancestors(i):
        out, seen, cur = [], set(), by_idx[i]["parentID"]
        while cur in by_idx and cur not in seen:
            seen.add(cur)
            out.append(cur)
            cur = by_idx[cur]["parentID"]
        return out

    def nearest(anc, cls):
        for a in anc:
            if by_idx[a]["className"] == cls:
                return guid.get(a)
        return None

    entries, quests, objectives = [], [], []
    for e in exports:
        i, cls, pm = e["index"], e["className"], pmap[e["index"]]
        anc = ancestors(i)
        with_guid = [guid[a] for a in anc if guid.get(a)]
        parent_guid = with_guid[0] if with_guid else None
        root_guid = with_guid[-1] if with_guid else guid.get(i)
        base = pm.get("baseName") if isinstance(pm.get("baseName"), str) else None
        order = _int(pm.get("order"))
        ord_ = order if order is not None else pos[i]
        title = next((_loc(pm.get(n)) for n in TITLE_PROPS if _loc(pm.get(n)) is not None), None)
        desc = _loc(pm.get("description"))
        entries.append((fid, i, guid.get(i), cls, e["parentID"], parent_guid, root_guid, base, ord_,
                        title, desc, _props_json(pairs[i])))

        if cls == "CJournalQuest":
            if not guid.get(i):
                missing.append(f"{relpath} export {i}")   # a PK row needs a guid
                continue
            typ = pm.get("type") if isinstance(pm.get("type"), str) else None
            ctype = pm.get("contentType") if isinstance(pm.get("contentType"), str) else None
            world = _int(pm.get("world"))
            quests.append((relpath, (guid[i], fid, Path(relpath).stem.lower(), title, typ, ctype,
                                     None if world is None else str(world), ord_, base, _category(relpath))))

        elif cls == "CJournalQuestObjective":
            counter = next((_int(pm.get(n)) for n in COUNTER_PROPS if _int(pm.get(n)) is not None), None)
            mand = pm.get("isMandatory")
            pins = sum(1 for k in kids.get(i, []) if by_idx[k]["className"] == "CJournalQuestMapPin")
            objectives.append((guid.get(i), nearest(anc, "CJournalQuest"), nearest(anc, "CJournalQuestPhase"),
                               fid, base, title, ord_, counter,
                               int(mand) if isinstance(mand, bool) else None, pins))
    return entries, quests, objectives


def build(con, verbose=True):
    files = sorted(common.R4.rglob("*.journal"))
    all_entries, all_quests, all_objectives = [], [], []
    failed = []
    no_guid = []
    for jf in files:
        relpath = common.rel(jf)
        size = jf.stat().st_size
        fid = common.file_id(con, relpath, "journal", size)
        try:
            version, exports, pairs = _decode_file(jf)
            entries, quests, objectives = _file_rows(fid, relpath, exports, pairs, no_guid)
        except Exception as ex:
            msg = f"{type(ex).__name__}: {ex}"[:300]
            common.file_id(con, relpath, "journal", size, error=msg)
            failed.append((relpath, msg))
            continue
        common.file_id(con, relpath, "journal", size, version=version)
        all_entries.extend(entries)
        all_quests.extend(quests)
        all_objectives.extend(objectives)

    # one row per quest guid: keep the first (files are sorted), report the rest
    kept, seen, dups = [], {}, []
    for relpath, row in all_quests:
        g = row[0]
        if g in seen:
            dups.append((g, seen[g], relpath))
            continue
        seen[g] = relpath
        kept.append(row)

    con.executemany("INSERT INTO journal_entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", all_entries)
    con.executemany("INSERT INTO journal_quests VALUES (?,?,?,?,?,?,?,?,?,?)", kept)
    con.executemany("INSERT INTO journal_objectives VALUES (?,?,?,?,?,?,?,?,?,?)", all_objectives)

    if verbose:
        print(f"  {len(files)} journal files, {len(failed)} not decoded", flush=True)
        for relpath, msg in failed:
            print(f"    skipped {relpath}: {msg}", flush=True)
        print(f"  {len(all_entries)} entries, {len(kept)} quests, {len(all_objectives)} objectives", flush=True)
        for g, a, b in dups:
            print(f"  WARNING duplicate quest guid {g}: kept {a}, dropped {b}", flush=True)
        for where in no_guid:
            print(f"  WARNING CJournalQuest without guid skipped: {where}", flush=True)
