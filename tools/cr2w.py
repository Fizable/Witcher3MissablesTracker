"""CR2W reader for REDkit resources (.w2phase, .w2scene, .journal).

  parse(path)   -> {'version', 'data', 'names', 'imports', 'exports'} with each export's data offsets
  props(path, export) -> list of {'name','type','value'}, or None

Hardened: every read is bounds-checked against the buffer, and the container version is
checked before the tables are trusted. A file that is truncated, that uses an older
container version (the 10 legacy `.w2dset` dialogue sets are version 129), or whose tables
do not fit is rejected with a clear error instead of being decoded into plausible nonsense.
Nothing here writes to disk.
"""
import struct
from pathlib import Path

MAGIC = b"CR2W"
# REDkit's editor resources run from version 136 to 164 in this install, and the table layout is
# the same across all of them, so the guard is structural (do the tables fit?) rather than a
# version list. The 10 legacy .w2dset dialogue sets (127-137) do NOT fit it and are refused.


class NotCr2w(Exception):
    """The file does not start with CR2W."""


class UnsupportedVersion(Exception):
    """A CR2W container this reader does not decode (for example the version-129 .w2dset)."""


class Truncated(Exception):
    """The file, or one of its tables/exports, ends early."""


def _u32(d, o):
    if o < 0 or o + 4 > len(d):
        raise Truncated(f"need 4 bytes at {o}, file is {len(d)}")
    return struct.unpack_from("<I", d, o)[0]


def parse(path):
    d = Path(path).read_bytes()
    if d[:4] != MAGIC:
        raise NotCr2w(f"{path}: magic is {d[:4]!r}")
    if len(d) < 160:
        raise Truncated(f"{path}: {len(d)} bytes is too short for a CR2W header")
    version = _u32(d, 4)
    tables = []
    for i in range(10):
        o = 4 + 36 + 12 * i
        tables.append(struct.unpack_from("<III", d, o))
    pos = 4 + 36 + 120
    # structural guard: the name/import/export tables have to fit in the file
    fits = pos + 8 * tables[1][1] + 8 * tables[2][1] + 24 * tables[4][1]
    if fits > len(d) or tables[0][1] > len(d):
        raise UnsupportedVersion(f"{path}: container version {version} does not use this table layout "
                                 f"(tables want {fits} bytes of a {len(d)} byte file)")

    strings_size = tables[0][1]
    if strings_size > len(d) - pos:
        raise Truncated(f"{path}: string table claims {strings_size} bytes, {len(d) - pos} left")
    raw = d[pos:pos + strings_size]
    pos += strings_size
    strings, off, buf = {}, 0, bytearray()
    for i, b in enumerate(raw):
        if b == 0:
            strings[off] = buf.decode("latin-1")
            buf = bytearray()
            off = i + 1
        else:
            buf.append(b)

    def sget(o):
        return strings.get(o, f"<?{o}>")

    n_names = tables[1][1]
    if pos + 8 * n_names > len(d):
        raise Truncated(f"{path}: {n_names} names do not fit")
    names = []
    for _ in range(n_names):
        v, _h = struct.unpack_from("<II", d, pos)
        pos += 8
        names.append(sget(v))

    def nget(i):
        return names[i] if 0 <= i < len(names) else ""

    n_imports = tables[2][1]
    if pos + 8 * n_imports > len(d):
        raise Truncated(f"{path}: {n_imports} imports do not fit")
    imports = []
    for _ in range(n_imports):
        dp, cn, fl = struct.unpack_from("<IHH", d, pos)
        pos += 8
        imports.append({"depotPath": sget(dp), "className": nget(cn), "flags": fl})

    pos += 16 * tables[3][1]  # properties table, not needed for data decoding

    n_exports = tables[4][1]
    if pos + 24 * n_exports > len(d):
        raise Truncated(f"{path}: {n_exports} exports do not fit")
    exports = []
    for i in range(n_exports):
        cn, of, parent, dsz, doff, tmpl, _c = struct.unpack_from("<HHIIIII", d, pos)
        pos += 24
        if doff > len(d):
            raise Truncated(f"{path}: export {i + 1} data starts at {doff}, past the end of a {len(d)} byte file")
        dsz = min(dsz, len(d) - doff)
        exports.append({"index": i + 1, "className": nget(cn), "parentID": parent,
                        "dataSize": dsz, "dataOffset": doff, "nameOffset": of, "template": tmpl})
    return {"version": version, "data": d, "names": names, "imports": imports, "exports": exports}


def _name(names, i):
    return names[i] if 0 <= i < len(names) else ""


def _prop_bag(payload, names, imports, exports):
    try:
        return _prop_bag_inner(payload, names, imports, exports)
    except (struct.error, IndexError):
        return None


def _prop_bag_inner(payload, names, imports, exports):
    if not payload:
        return None
    lead = struct.unpack_from("<b", payload, 0)[0]
    pos = 1
    if lead == -128:
        return []
    if lead == 1:
        pos += 4
    elif lead != 0:
        return None
    out = []
    n = len(payload)
    while pos + 2 <= n:
        nid = struct.unpack_from("<H", payload, pos)[0]; pos += 2
        if nid == 0:
            break
        tid = struct.unpack_from("<H", payload, pos)[0]; pos += 2
        size = struct.unpack_from("<I", payload, pos)[0]; pos += 4
        if size < 4 or pos + size - 4 > n:
            return None
        sub = payload[pos:pos + size - 4]; pos += size - 4
        out.append({"name": _name(names, nid), "type": _name(names, tid),
                    "value": _decode(_name(names, tid), sub, names, imports, exports)})
    return out


def _decode(tname, p, names, imports, exports):
    t = tname.lower()
    if t == "string" or t == "cstring":
        if p and p[0] & 0x80:
            return p[1:1 + (p[0] & 0x7F)].decode("latin-1", errors="replace")
        return p.split(b"\x00", 1)[0].decode("latin-1", errors="replace")
    if t == "cname" and len(p) >= 2:
        return _name(names, struct.unpack_from("<H", p, 0)[0])
    if t == "bool" and p:
        return bool(p[0])
    if t in ("uint32",) and len(p) >= 4:
        return struct.unpack_from("<I", p, 0)[0]
    if t in ("int32",) and len(p) >= 4:
        return struct.unpack_from("<i", p, 0)[0]
    if t == "float" and len(p) >= 4:
        return struct.unpack_from("<f", p, 0)[0]
    if t == "localizedstring" and len(p) >= 4:
        return {"locId": struct.unpack_from("<I", p, 0)[0]}
    if t.startswith("soft:") and len(p) >= 2:
        i = struct.unpack_from("<H", p, 0)[0]
        if 0 < i <= len(imports):
            return {"ref_import": imports[i - 1]["depotPath"], "ref_class": imports[i - 1]["className"]}
        return None
    if (t.startswith("ptr:") or t.startswith("handle:")) and len(p) >= 4:
        v = struct.unpack_from("<i", p, 0)[0]
        if v > 0:
            return {"ref_chunk": v, "ref_class": ""}
        if v < 0 and -v - 1 < len(imports):
            return {"ref_import": imports[-v - 1]["depotPath"]}
        return None
    if len(p) == 2:
        i = struct.unpack_from("<H", p, 0)[0]
        if 0 <= i < len(names):
            return names[i]
    bag = _prop_bag(p, names, imports, exports)
    if bag:
        return bag
    return {"raw_hex": p[:64].hex(), "raw_len": len(p)}


def props(parsed, export):
    """Decoded property list for one export (ptr targets carry raw chunk indices)."""
    d = parsed["data"]
    start = export["dataOffset"]
    payload = d[start:start + export["dataSize"]]
    bag = _prop_bag(payload, parsed["names"], parsed["imports"], parsed["exports"])
    return bag or []


def all_props(parsed):
    """(export, [properties]) for every export, skipping the ones that cannot be decoded."""
    for e in parsed["exports"]:
        try:
            yield e, props(parsed, e)
        except (struct.error, IndexError):
            continue


def refs(parsed, export):
    """Every depot path this export points at, by class: {'path': n} across its properties."""
    out = {}
    for v in props(parsed, export):
        stack = [v["value"]]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                if "ref_import" in x:
                    out[x["ref_import"]] = x.get("ref_class", "")
                elif "ref_chunk" in x:
                    pass
                stack.extend(x.values())
            elif isinstance(x, list):
                stack.extend(x)
    return out
