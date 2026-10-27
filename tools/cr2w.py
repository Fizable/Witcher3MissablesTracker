"""CR2W reader for REDkit resources (.w2phase, .w2scene, .journal).

  parse(path)   -> {'names', 'imports', 'exports'} with each export's data offsets
  props(path, export, names, imports, exports) -> list of {'name','type','value'}, or None
"""
import struct
from pathlib import Path

MAGIC = b"CR2W"


def parse(path):
    d = Path(path).read_bytes()
    if d[:4] != MAGIC:
        raise ValueError("not CR2W")
    version = struct.unpack_from("<I", d, 4 + 0)[0]
    tables = [struct.unpack_from("<III", d, 4 + 36 + 12 * i) for i in range(10)]
    pos = 4 + 36 + 120
    strings_size = tables[0][1]
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

    names = []
    for _ in range(tables[1][1]):
        v, _h = struct.unpack_from("<II", d, pos); pos += 8
        names.append(sget(v))

    def nget(i):
        return names[i] if 0 <= i < len(names) else ""

    imports = []
    for _ in range(tables[2][1]):
        dp, cn, fl = struct.unpack_from("<IHH", d, pos); pos += 8
        imports.append({"depotPath": sget(dp), "className": nget(cn), "flags": fl})

    pos += 16 * tables[3][1]  # properties table, not needed for data decoding

    exports = []
    for i in range(tables[4][1]):
        cn, of, parent, dsz, doff, tmpl, _c = struct.unpack_from("<HHIIIII" if False else "<HHIIIII", d, pos)
        pos += 24
        exports.append({"index": i + 1, "className": nget(cn), "parentID": parent,
                        "dataSize": dsz, "dataOffset": doff})
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
