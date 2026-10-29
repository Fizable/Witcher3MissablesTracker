"""Read-only probe of the game's DLC bundles, before any resource provider is written.

Answers the step-2 questions of docs/PLAN-1.0-completion.md without changing the pipeline:

  * how many .w2phase/.w2scene/.journal resources the DLC bundles contain,
  * whether those payloads parse with the same CR2W reader the toolchain uses,
  * how each virtual bundle path maps to a REDkit path (and whether the copies agree),
  * whether q704*/q705* expose real scenes with choice lines and fact-setting sections,
  * and what a DLC resource provider would actually have to read.

Nothing is extracted into data/ or the package: bundle payloads are decompressed in memory and
only handed to cr2w.parse through a temporary directory that is removed on exit. The game,
DLC and REDkit folders are opened read-only.

  py tools/probe_dlc.py            human-readable report
  py tools/probe_dlc.py --json     the same facts as JSON

POTATO70 layout used here (observed in all expansion bundles of this install):
  0x00  magic "POTATO70"
  0x08  uint64 bundle size
  0x10  uint32 table-of-contents size
  0x14  uint16 format version (5)
  0x16  uint32 first data offset
  0x20  TOC, N * 304-byte records: char name[256], uint8 hash[16], uint32 offset,
        uint32 unknown, uint32 unpacked size, uint32 stored size, uint32 crc
Entry data is 16-byte aligned; stored == unpacked means raw, otherwise zlib.
"""
import argparse
import collections
import json
import os
import struct
import sys
import tempfile
import zlib
from pathlib import Path

import cr2w
import questindex
from paths import GAME, REDKIT_R4

MAGIC = b"POTATO70"
TOC_RECORD = 304
NAME_FIELD = 256
TOC_OFFSET = 0x20
QUEST_EXTS = (".w2phase", ".w2scene", ".journal")


class BundleError(Exception):
    """A bundle that cannot be trusted: wrong magic, truncated TOC or an out-of-file entry."""


def bundle_entries(path):
    """(header, entries) for one POTATO70 bundle. Reads the TOC only, never the payloads."""
    path = Path(path)
    size = path.stat().st_size
    with path.open("rb") as f:
        head = f.read(TOC_OFFSET)
        if len(head) < TOC_OFFSET or head[:8] != MAGIC:
            raise BundleError(f"{path.name}: not a POTATO70 bundle")
        bundle_size = struct.unpack_from("<Q", head, 0x08)[0]
        toc_size = struct.unpack_from("<I", head, 0x10)[0]
        version = struct.unpack_from("<H", head, 0x14)[0]
        data_offset = struct.unpack_from("<I", head, 0x16)[0]
        if bundle_size != size:
            # A partial download is a real possibility: say so instead of reading garbage.
            raise BundleError(f"{path.name}: header says {bundle_size} bytes, file is {size}")
        if toc_size % TOC_RECORD or toc_size > size - TOC_OFFSET:
            raise BundleError(f"{path.name}: TOC of {toc_size} bytes does not fit the format")
        f.seek(TOC_OFFSET)
        toc = f.read(toc_size)
        if len(toc) != toc_size:
            raise BundleError(f"{path.name}: TOC ends early")
        entries = []
        for i in range(0, toc_size, TOC_RECORD):
            rec = toc[i:i + TOC_RECORD]
            name = rec[:NAME_FIELD].split(b"\0", 1)[0].decode("latin-1")
            if not name:
                continue
            off, unknown, unpacked, stored, crc = struct.unpack_from("<IIIII", rec, NAME_FIELD + 16)
            if off + stored > size:
                raise BundleError(f"{path.name}: {name} runs past the end of the bundle")
            entries.append({"name": name, "offset": off, "stored": stored,
                            "unpacked": unpacked, "crc": crc, "unknown": unknown})
    header = {"path": str(path), "size": size, "version": version,
              "tocSize": toc_size, "dataOffset": data_offset}
    return header, entries


def entry_bytes(path, entry):
    """The payload of one entry, decompressed when stored != unpacked."""
    with open(path, "rb") as f:
        f.seek(entry["offset"])
        raw = f.read(entry["stored"])
    if len(raw) != entry["stored"]:
        raise BundleError(f"{Path(path).name}: {entry['name']} ends early")
    if entry["stored"] == entry["unpacked"]:
        return raw
    return zlib.decompress(raw)


def cr2w_status(payload, tmpdir):
    """('ok'|'not_cr2w'|'unsupported'|'truncated'|'error', detail) for one payload."""
    p = Path(tmpdir) / "payload.bin"
    p.write_bytes(payload)
    try:
        cr2w.parse(p)
        return "ok", ""
    except cr2w.UnsupportedVersion as e:
        return "unsupported", str(e)[:160]
    except cr2w.NotCr2w as e:
        return "not_cr2w", str(e)[:160]
    except cr2w.Truncated as e:
        return "truncated", str(e)[:160]
    except Exception as e:  # report the class; never pretend a file parsed
        return "error", f"{type(e).__name__}: {e}"[:160]


def pack_of(name):
    """The DLC pack a virtual path names, from 'dlc\\<pack>\\...'; '' for a base-game path."""
    parts = name.split("\\")
    return parts[1].lower() if len(parts) > 2 and parts[0].lower() == "dlc" else ""


def discover_bundles():
    """Every game bundle under content/ and the DLC folder, in a stable order."""
    found = []
    for root in (GAME / "content", GAME / "DLC"):
        if root.is_dir():
            found.extend(sorted(root.rglob("*.bundle")))
    return found


def redkit_index():
    """Relative POSIX path -> file for every resource under r4data/dlc, exact case."""
    root = REDKIT_R4 / "dlc"
    out = {}
    if not root.is_dir():
        return out
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            p = Path(dirpath) / fn
            out[p.relative_to(REDKIT_R4).as_posix()] = p
    return out


def scan_bundles(bundles, tmpdir):
    """Inventory, CR2W counts and virtual->REDkit mapping, deduplicated by virtual path."""
    rk = redkit_index()
    rk_lower = {k.lower(): k for k in rk}
    resources = {}  # virtual path -> (bundle, entry), first occurrence wins
    duplicates = []
    bundle_rows = []
    for path in bundles:
        try:
            header, entries = bundle_entries(path)
        except BundleError as e:
            bundle_rows.append({"path": str(path), "error": str(e)})
            continue
        counts = collections.Counter()
        base_paths = collections.Counter()
        for e in entries:
            ext = os.path.splitext(e["name"])[1].lower()
            if ext not in QUEST_EXTS:
                continue
            if pack_of(e["name"]):
                counts[ext] += 1
                if e["name"] in resources:
                    duplicates.append({"path": e["name"], "alsoIn": path.name})
                else:
                    resources[e["name"]] = (path, e)
            else:
                base_paths[ext] += 1
        bundle_rows.append({"path": path.name, "entries": len(entries),
                            "questResources": dict(counts),
                            "baseQuestPaths": dict(base_paths), "header": header})

    per_pack = collections.defaultdict(collections.Counter)
    cr2w_counts = collections.defaultdict(collections.Counter)
    failures = []
    mapping = collections.Counter()
    bundle_only = []
    divergent = []
    rk_seen = set()
    for name in sorted(resources):
        bundle, e = resources[name]
        pack = pack_of(name)
        ext = os.path.splitext(name)[1].lower()
        per_pack[pack][ext] += 1
        per_pack["all"][ext] += 1
        try:
            payload = entry_bytes(bundle, e)
        except (BundleError, zlib.error) as ex:
            cr2w_counts[pack]["decompress_fail"] += 1
            failures.append({"bundle": Path(bundle).name, "name": name,
                             "kind": "decompress", "detail": str(ex)[:160]})
            continue
        if ext in (".w2phase", ".w2scene"):
            status, detail = cr2w_status(payload, tmpdir)
            cr2w_counts[pack][status] += 1
            cr2w_counts["all"][status] += 1
            if status != "ok":
                failures.append({"bundle": Path(bundle).name, "name": name,
                                 "kind": status, "detail": detail})
        rel = name.replace("\\", "/")
        hit = rk.get(rel) or rk.get(rk_lower.get(rel.lower(), ""))
        if hit is None:
            mapping["missing_in_redkit"] += 1
            bundle_only.append(rel)
            continue
        mapping["in_redkit"] += 1
        if rel in rk:
            mapping["exactCase"] += 1
        rk_seen.add(hit.relative_to(REDKIT_R4).as_posix().lower())
        if hit.read_bytes() == payload:
            mapping["identical"] += 1
        else:
            mapping["different"] += 1
            if len(divergent) < 12:
                divergent.append({"virtual": name, "redkit": str(hit),
                                  "bundleBytes": len(payload),
                                  "redkitBytes": hit.stat().st_size})

    redkit_quest = [k for k in rk if os.path.splitext(k)[1].lower() in QUEST_EXTS]
    mapping["redkitResources"] = len(redkit_quest)
    mapping["redkitOnlyCount"] = len([k for k in redkit_quest
                                      if k.lower() not in rk_seen])
    mapping["uniqueResources"] = len(resources)
    mapping["duplicateEntries"] = len(duplicates)
    report = {
        "bundles": bundle_rows,
        "totals": {e: per_pack["all"][e] for e in QUEST_EXTS},
        "totalEntries": {e: sum(r.get("questResources", {}).get(e, 0) for r in bundle_rows)
                         for e in QUEST_EXTS},
        "packs": {k: dict(v) for k, v in sorted(per_pack.items()) if k != "all"},
        "cr2w": {k: dict(v) for k, v in sorted(cr2w_counts.items())},
        "mapping": dict(mapping),
        "bundleOnly": sorted(bundle_only)[:40],
        "duplicates": duplicates[:60],
        "divergent": divergent,
    }
    report["cr2w"]["failures"] = failures[:40]
    report["cr2w"]["failureCount"] = len(failures)
    return report, resources


def scan_redkit_dlc(tmpdir):
    """Counts and CR2W results for every quest resource under r4data/dlc."""
    root = REDKIT_R4 / "dlc"
    counts = collections.Counter()
    per_pack = collections.defaultdict(collections.Counter)
    failures = []
    if not root.is_dir():
        return {"counts": {}, "packs": {}, "failures": [], "failureCount": 0}
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in QUEST_EXTS:
            continue
        rel = p.relative_to(root).as_posix()
        pack = rel.split("/", 1)[0].lower()
        ext = p.suffix.lower()
        counts[ext] += 1
        per_pack[pack][ext] += 1
        if ext == ".journal":
            continue
        status, detail = cr2w_status(p.read_bytes(), tmpdir)
        counts[status] += 1
        per_pack[pack][status] += 1
        if status != "ok":
            failures.append({"path": rel, "kind": status, "detail": detail})
    return {"counts": dict(counts), "packs": {k: dict(v) for k, v in sorted(per_pack.items())},
            "failures": failures[:40], "failureCount": len(failures)}


def q704_q705(resources, tmpdir):
    """Evidence for the specific Blood and Wine quests the plan's step-2 check names."""
    out = {"phases": [], "companionPhases": [], "scenes": 0, "journals": 0,
           "scenesWithChoices": 0, "choiceLines": 0, "oneShotChoices": 0,
           "choicesWithSectionSets": 0, "scenesWithFactSettingChoices": 0,
           "phasesParsed": 0, "factSets": 0, "factTests": 0, "factRefs": 0,
           "bundleOnlyPhases": [], "sceneFiles": []}
    rk = redkit_index()
    rk_lower = {k.lower(): k for k in rk}
    for name in sorted(resources):
        base = os.path.basename(name).lower()
        named = base.startswith("q704") or base.startswith("q705")
        in_family = "q704" in name.lower() or "q705" in name.lower()
        ext = os.path.splitext(name)[1].lower()
        if in_family and ext == ".w2phase" and not named:
            out["companionPhases"].append(name.replace("\\", "/"))
            continue
        if not named or ext not in QUEST_EXTS:
            continue
        bundle, e = resources[name]
        rel = name.replace("\\", "/")
        hit = rk.get(rel) or rk.get(rk_lower.get(rel.lower(), ""))
        if ext == ".w2phase":
            out["phases"].append(rel)
            source = hit
            if source is None:
                out["bundleOnlyPhases"].append(rel)
                p = Path(tmpdir) / "phase.w2phase"
                p.write_bytes(entry_bytes(bundle, e))
                source = p
            try:
                facts = questindex.phase_facts(source)
            except Exception:
                continue
            out["phasesParsed"] += 1
            out["factSets"] += len(facts["set"])
            out["factTests"] += len(facts["test"])
            out["factRefs"] += len(facts["ref"])
        elif ext == ".w2scene":
            out["scenes"] += 1
            source = hit
            if source is None:
                p = Path(tmpdir) / "scene.w2scene"
                p.write_bytes(entry_bytes(bundle, e))
                source = p
            choices = questindex.scene_choices(source)
            if choices:
                out["scenesWithChoices"] += 1
            out["choiceLines"] += len(choices)
            out["oneShotChoices"] += sum(1 for c in choices if c["one_shot"])
            sets = sum(1 for c in choices if c["section_sets"])
            out["choicesWithSectionSets"] += sets
            if sets:
                out["scenesWithFactSettingChoices"] += 1
            if len(out["sceneFiles"]) < 8:
                out["sceneFiles"].append(rel)
        else:
            out["journals"] += 1
    bob = REDKIT_R4 / "dlc" / "bob"
    out["redkitPhases"] = len([p for p in bob.rglob("*.w2phase")
                               if p.name.lower().startswith(("q704", "q705"))])
    out["redkitScenes"] = len([p for p in bob.rglob("*.w2scene")
                               if p.name.lower().startswith(("q704", "q705"))])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="print the facts as JSON")
    args = ap.parse_args()

    missing = [str(p) for p in (GAME, REDKIT_R4) if not p.is_dir()]
    if missing:
        print("missing game or REDkit folder: " + ", ".join(missing))
        return 2
    bundles = discover_bundles()
    if not bundles:
        print("no .bundle files found under content/ or DLC/")
        return 2
    with tempfile.TemporaryDirectory(prefix="w3-dlc-probe-") as tmpdir:
        report, resources = scan_bundles(bundles, tmpdir)
        report["redkitDlc"] = scan_redkit_dlc(tmpdir)
        report["q704q705"] = q704_q705(resources, tmpdir)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    print("DLC bundles")
    for b in report["bundles"]:
        if "error" in b:
            print(f"  {b['path']}: ERROR {b['error']}")
            continue
        q = b.get("questResources", {})
        extra = b.get("baseQuestPaths", {})
        if not q and not extra:
            continue
        tail = ""
        if extra:
            tail = " (also base-game paths: " + ", ".join(
                f"{n} {e}" for e, n in sorted(extra.items())) + ")"
        print(f"  {b['path']}: {q.get('.w2phase', 0)} .w2phase, "
              f"{q.get('.w2scene', 0)} .w2scene, {q.get('.journal', 0)} .journal{tail}")
    t = report["totals"]
    te = report["totalEntries"]
    print(f"  unique DLC resources: {t.get('.w2phase', 0)} .w2phase, "
          f"{t.get('.w2scene', 0)} .w2scene, {t.get('.journal', 0)} .journal")
    print(f"  entries including {report['mapping']['duplicateEntries']} duplicates: "
          f"{te.get('.w2phase', 0)} / {te.get('.w2scene', 0)} / {te.get('.journal', 0)}")
    print("  per pack (unique):")
    for pack, c in report["packs"].items():
        print(f"    {pack:8s} {c.get('.w2phase', 0):4d} phase  {c.get('.w2scene', 0):5d} scene  "
              f"{c.get('.journal', 0):4d} journal")

    print("\nCR2W, DLC bundle payloads (phases and scenes, unique)")
    for pack, c in report["cr2w"].items():
        if pack in ("failures", "failureCount"):
            continue
        print(f"  {pack:8s} ok={c.get('ok', 0):4d} unsupported={c.get('unsupported', 0)} "
              f"truncated={c.get('truncated', 0)} not_cr2w={c.get('not_cr2w', 0)} "
              f"error={c.get('error', 0)} zlib_fail={c.get('decompress_fail', 0)}")
    print(f"  failures: {report['cr2w']['failureCount']}")
    for f in report["cr2w"]["failures"][:7]:
        print(f"    {f['kind']}: {f['name']} - {f['detail']}")

    rk = report["redkitDlc"]
    print("\nCR2W, REDkit r4data/dlc files")
    print(f"  {rk['counts'].get('.w2phase', 0)} phases, {rk['counts'].get('.w2scene', 0)} scenes, "
          f"{rk['counts'].get('.journal', 0)} journals; ok={rk['counts'].get('ok', 0)} "
          f"fail={rk['failureCount']}")
    for f in rk["failures"][:7]:
        print(f"    {f['kind']}: {f['path']} - {f['detail']}")

    m = report["mapping"]
    print("\nVirtual paths -> REDkit")
    print(f"  unique DLC resources: {m['uniqueResources']}; REDkit quest resources: "
          f"{m['redkitResources']}")
    print(f"  matched: {m.get('in_redkit', 0)} (exact case {m.get('exactCase', 0)}); "
          f"bundle only: {m.get('missing_in_redkit', 0)}; REDkit only: {m['redkitOnlyCount']}")
    print(f"  bytes: identical {m.get('identical', 0)}, different {m.get('different', 0)}")
    for d in m.get("divergent", [])[:5]:
        print(f"    different: {d['virtual']} (bundle {d['bundleBytes']} B, "
              f"REDkit {d['redkitBytes']} B)")
    for b in report["bundleOnly"][:8]:
        print(f"    bundle only: {b}")
    for d in report["duplicates"][:5]:
        print(f"    duplicate: {d['path']} (also in {d['alsoIn']})")

    q = report["q704q705"]
    print("\nq704/q705")
    print(f"  phases {len(q['phases'])} (REDkit {q['redkitPhases']}), scenes {q['scenes']} "
          f"(REDkit {q['redkitScenes']}), journals {q['journals']}")
    print(f"  companion phase files in the same folders: {len(q['companionPhases'])}")
    print(f"  scenes with choices {q['scenesWithChoices']}, choice lines {q['choiceLines']}, "
          f"one-shot {q['oneShotChoices']}")
    print(f"  choice lines with fact-setting sections {q['choicesWithSectionSets']} in "
          f"{q['scenesWithFactSettingChoices']} scenes")
    print(f"  phases parsed {q['phasesParsed']}, fact sets {q['factSets']}, tests {q['factTests']}, "
          f"refs {q['factRefs']}")
    for p in q["bundleOnlyPhases"]:
        print(f"    bundle only phase: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
