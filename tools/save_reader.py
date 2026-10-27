"""Read-only Witcher 3 save reader (Python port of w3tracker/src/save.rs).

  load_raw(path)       -> decompressed save bytes
  name_table(raw)      -> the save's own string table
  journal(raw, names)  -> [{'guid': hex, 'status': str, 'resource': str}]
  facts(raw)           -> {fact_name: [recorded values]}
"""
import re, struct
from pathlib import Path


def lz4_block(src, hint):
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        t = src[i]; i += 1
        ln = t >> 4
        if ln == 15:
            while True:
                b = src[i]; i += 1
                ln += b
                if b != 255:
                    break
        out += src[i:i + ln]
        i += ln
        if i >= n:
            break
        off = src[i] | (src[i + 1] << 8); i += 2
        ml = t & 15
        if ml == 15:
            while True:
                b = src[i]; i += 1
                ml += b
                if b != 255:
                    break
        ml += 4
        if off == 0 or off > len(out):
            raise ValueError("lz4: bad back-reference")
        start = len(out) - off
        for k in range(ml):
            out.append(out[start + k])
    return bytes(out)


def load_raw(path):
    d = Path(path).read_bytes()
    if len(d) < 16 or d[:8] != b"SNFHFZLC":
        raise ValueError("not a Witcher 3 save")
    n, pos = struct.unpack_from("<II", d, 8)
    out = bytearray()
    for k in range(n):
        comp, unc = struct.unpack_from("<II", d, 16 + 12 * k)
        out += lz4_block(d[pos:pos + comp], unc)
        pos += comp
    return bytes(out)


def name_table(r):
    h = r.find(b"NMMANU")
    count = struct.unpack_from("<I", r, h + 6)[0]
    p = r.find(b"\x06Entity")
    names = []
    while len(names) < count:
        l = r[p]
        names.append(r[p + 1:p + 1 + l].decode("latin-1"))
        p += 1 + l
    return names


def _vint(r, q):
    b = r[q]; q += 1
    ln = b & 0x3F
    if b & 0x40:
        sh = 6
        while True:
            c = r[q]; q += 1
            ln |= (c & 0x7F) << sh
            sh += 7
            if not c & 0x80:
                break
    return ln, q


TYPE_SIZE = {"Bool": 1, "Uint8": 1, "Int8": 1, "Uint16": 2, "Int16": 2,
             "Uint32": 4, "Int32": 4, "Float": 4, "Uint64": 8, "Int64": 8,
             "Double": 8, "CGUID": 16}


def journal(r, names):
    ix = {n: i + 1 for i, n in enumerate(names)}
    nm = lambda i: names[i - 1] if 0 < i <= len(names) else ""
    jm, ses = ix["CJournalManager"], ix["SJournalEntryStatus"]
    q = r.find(b"BS" + struct.pack("<H", jm)) + 4
    entries, cur = [], False
    while True:
        t = r[q:q + 2]
        if t == b"BS":
            i = struct.unpack_from("<H", r, q + 2)[0]
            if i == ses:
                entries.append({"guid": None, "status": "", "resource": None})
                cur = True
            elif nm(i) == "CWitcherJournalManager":
                break
            q += 4
            continue
        if t != b"VL":
            raise ValueError(f"unexpected token at {q}")
        name = nm(struct.unpack_from("<H", r, q + 2)[0])
        tn = nm(struct.unpack_from("<H", r, q + 4)[0])
        q += 6
        if tn in TYPE_SIZE:
            sz = TYPE_SIZE[tn]
            if cur and name == "guid" and sz == 16:
                entries[-1]["guid"] = r[q:q + 16].hex()
            q += sz
        elif tn == "String":
            ln, q = _vint(r, q)
            if cur and name == "resource":
                entries[-1]["resource"] = r[q:q + ln].decode("latin-1")
            q += ln
        elif tn == "CName" or tn.startswith("E"):
            v = nm(struct.unpack_from("<H", r, q)[0])
            if cur and name == "status":
                entries[-1]["status"] = v
            q += 2
        else:
            raise ValueError(f"unknown journal type {tn} ({name})")
    return entries


_FACT_RE = re.compile(rb"([\x81-\xff])([A-Za-z0-9_.\-]+)\x00\x00(.)\x00", re.DOTALL)


def facts(r):
    out = {}
    for m in _FACT_RE.finditer(r):
        name = m.group(2)
        if len(name) != m.group(1)[0] - 0x80:
            continue
        count = m.group(3)[0]
        p, vals = m.end(), []
        for _ in range(count):
            if p + 2 > len(r):
                break
            vals.append(struct.unpack_from("<H", r, p)[0])
            p += 10
        out[name.decode("latin-1")] = vals
    return out
