"""Which journal objectives a reviewed ending scene can play under, from the game database.

Reads db/w3db.sqlite (read-only) and data/outcomes.json, and writes data/scene_objectives.json:

  {"version": 1, "note": "...", "scenes": {"<scene path, lower case, forward slashes>": ["<dashed guid>", ...]}}

Scenes come from every `source.file` in the outcome `guidance` and `requires` rows that is a .w2scene
(phase and journal files are not conversations and cannot have an objective row). A scene with no
rows in the database is written with an empty list: it is named, and the app treats it as unknown.

Guids: the database holds the raw 32-hex bytes. The app reads the save's JHighlightedObjective with
`save::guid_str`, which takes each 4-byte group as a little-endian u32 printed as 8 upper-case hex
digits, joined by dashes. `dashed_guid` below does the same, so the two can be compared directly.

Run:  py tools/gamedb/export_scene_objectives.py

Prints a coverage report: each guidance line, its scene, and the titles of the objectives the scene
can play under. A line with no objective rows is listed as such; the app shows no "say this now"
state for it.
"""
import json
import sqlite3
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402  (DB path: W3_GAMEDB_OUT or <tracker>/db)
import paths  # noqa: E402

OUTCOMES = paths.TRACKER / "data" / "outcomes.json"
OUT = paths.TRACKER / "data" / "scene_objectives.json"
NOTE = "generated from db/w3db.sqlite by tools/gamedb/export_scene_objectives.py"


def connect():
    uri = "file:" + common.DB.resolve().as_posix() + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


def scene_key(path):
    """The key every table and the app use: lower case, forward slashes."""
    return path.replace("\\", "/").lower()


def dashed_guid(raw_hex):
    """Mirror of save::guid_from_hex: four little-endian u32 groups, upper-case, dashed."""
    raw = bytes.fromhex(raw_hex.strip())
    if len(raw) != 16:
        raise ValueError(f"not a 16-byte guid: {raw_hex!r}")
    return "-".join(f"{struct.unpack('<I', raw[4 * k:4 * k + 4])[0]:08X}" for k in range(4))


def guidance_lines(outcomes):
    """(outcome id, step, instruction, scene key or None) for every guidance row. A row whose file is
    not a scene (a journal objective, say) has no conversation, so its scene key is None."""
    rows = []
    for oid, o in outcomes.get("outcomes", {}).items():
        for g in o.get("guidance", []):
            f = g.get("source", {}).get("file", "")
            scene = scene_key(f) if f.lower().endswith(".w2scene") else None
            rows.append((oid, g.get("step", ""), g.get("instruction", ""), scene))
    return rows


def scene_files(outcomes):
    names = set()
    for o in outcomes.get("outcomes", {}).values():
        for g in o.get("guidance", []) + o.get("requires", []):
            f = g.get("source", {}).get("file", "")
            if f.lower().endswith(".w2scene"):
                names.add(scene_key(f))
    return sorted(names)


def main():
    outcomes = json.loads(OUTCOMES.read_text(encoding="utf-8"))
    con = connect()
    scenes = {}
    raw_of = {}
    for scene in scene_files(outcomes):
        raws = [r[0] for r in con.execute(
            "SELECT DISTINCT objective_guid FROM scene_objectives WHERE scene = ? ORDER BY objective_guid", (scene,))]
        raws = [r for r in raws if r]
        scenes[scene] = sorted({dashed_guid(r) for r in raws})
        for r in raws:
            raw_of.setdefault(dashed_guid(r), r)

    doc = {"version": 1, "note": NOTE, "scenes": scenes}
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def titles(guid_dashed):
        raw = raw_of.get(guid_dashed)
        if raw is None:
            return []
        rows = con.execute(
            "SELECT DISTINCT s.text FROM journal_entries e JOIN strings s ON s.loc_id = e.title_loc_id "
            "WHERE e.guid = ?", (raw,)).fetchall()
        return sorted({r[0] for r in rows if r[0]})

    lines = guidance_lines(outcomes)
    covered = 0
    print(f"wrote {OUT} with {len(scenes)} scenes "
          f"({sum(1 for v in scenes.values() if v)} with objectives)")
    print()
    print("Guidance lines (scene = the line's own scene file):")
    for oid, step, instruction, scene in lines:
        if scene is None:
            print(f"  NOT A SCENE  {oid} / {step} / {instruction!r} (no conversation; the app shows no state)")
            continue
        objs = scenes.get(scene, [])
        if objs:
            covered += 1
            print(f"  COVERED   {oid} / {step} / {instruction!r}")
            print(f"            scene {scene}")
            for g in objs:
                t = titles(g)
                print(f"            objective {g}: {' | '.join(t) if t else '(no title row)'}")
        else:
            print(f"  NOT COVERED  {oid} / {step} / {instruction!r}")
            print(f"            scene {scene} (no objective rows)")
    print()
    print(f"{covered} of {len(lines)} guidance lines have at least one objective "
          f"({sum(1 for l in lines if l[3] is None)} are not scene files).")
    con.close()


if __name__ == "__main__":
    main()
