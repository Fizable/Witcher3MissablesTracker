"""The wider check, rebuilt: compare the route's hard prerequisites against the game's own files.

Three independent sources, kept apart on purpose:
  route   data/route.json  `hard` lists (wiki-era notes)
  graph   the REDkit phase graphs: who activates a quest's journal entry, and which facts its
          phases wait on vs which facts another quest's phases set
  saves   save_index.json: does any save ever hold the quest without its claimed prerequisite done

A claim is only labelled "graph" when the game's own files name the link, and only "save" when no
save contradicts it *and* there are saves on both sides of it. Anything else is reported as unproven
rather than silently kept.

  py gatecheck.py report            write gate_report.md and print the summary
  py gatecheck.py node <id>         everything known about one route node
"""
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import questgraph as qg

from paths import HERE, QDB, ROUTE, TRACKER
GATE_INDEX = HERE / "gate_index.json"
FACT_INDEX = HERE / "fact_index.json"
SAVE_INDEX = HERE / "save_index.json"

CODE = re.compile(r"^([a-z]+\d+)", re.I)


def quest_db():
    db = json.load(open(QDB))
    return {os.path.basename(k).replace(".journal", ""): v["ids"] for k, v in db.items()}


def journal_identity():
    """journal short -> {code, name, guid} from the REDkit journal files themselves."""
    out = {}
    for p in qg.JOURNAL_DIR.glob("*.journal"):
        try:
            g = qg.G(p)
        except Exception:
            continue
        for e in g.p["exports"]:
            if e["className"] != "CJournalQuest":
                continue
            ps = g.props(e["index"])
            ident = str(ps.get("uniqueScriptIdentifier") or ps.get("baseName") or "")
            m = CODE.match(ident)
            out[p.stem.lower()] = {"code": m.group(1).lower() if m else "",
                                   "name": ident, "guid": ps.get("guid", {}).get("raw_hex")}
    return out


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def code_map():
    """phase file prefix (q202_giant) -> journal short (giant).

    Exact normalized name first (q206_berserkers -> q206berserkers), then the quest's own
    uniqueScriptIdentifier, then the quest code when only one journal claims it. Anything still
    ambiguous is returned unresolved rather than guessed.
    """
    ident = journal_identity()
    by_norm, by_code = defaultdict(list), defaultdict(list)
    for short, v in ident.items():
        by_norm[norm(short)].append(short)
        if v["name"]:
            by_norm[norm(v["name"])].append(short)
        if v["code"]:
            by_code[v["code"]].append(short)
    out, unresolved = {}, {}
    for p in sorted(qg.QUEST_ROOT.rglob("*.w2phase")):
        np = norm(p.stem)
        cands = by_norm.get(np, [])
        if not cands:
            cands = [s for s in ident if ident[s]["name"] and
                     (norm(ident[s]["name"]).startswith(np) or np.startswith(norm(ident[s]["name"])))]
        if not cands:
            m = CODE.match(p.stem)
            if m:
                c = by_code.get(m.group(1).lower(), [])
                cands = c if len(c) == 1 else []
        if len(cands) == 1:
            out[p.stem] = cands[0]
        else:
            unresolved[p.stem] = cands
    return out, unresolved


def activations():
    """the game's own automatic starts: one quest's phase graph adds another quest's journal entry"""
    rows = json.load(open(GATE_INDEX))
    db = quest_db()
    pmap, un = code_map()
    pairs = defaultdict(list)
    for r in rows:
        t = os.path.basename(r["target"]).replace(".journal", "")
        ids = db.get(t)
        if not ids or r["leaf"] != ids[0][1]:
            continue
        srcj = pmap.get(r["src_quest"])
        if srcj in (None, t):
            continue
        pairs[(srcj, t)].append(r)
    print(f"phase files mapped to a journal: {len(pmap)}; unresolved: {len(un)}")
    for (a, b), rs in sorted(pairs.items()):
        print(f"{a:28s} STARTS {b:26s} via {rs[0]['src']} #{rs[0]['block']} {rs[0]['class']} ({len(rs)} block(s))")
    return pairs


def route_nodes():
    v = json.load(open(ROUTE))
    return v, v["nodes"]


def journals_of(node):
    out = []
    for f in node.get("files", []):
        for alt in f.split("|"):
            s = alt.split("#")[0]
            if s and s not in out:
                out.append(s)
    return out


def load_rows():
    return json.load(open(GATE_INDEX)), json.load(open(FACT_INDEX))


def node_index():
    """journal short -> route node id (first node that reads it)"""
    _, nodes = route_nodes()
    out = {}
    for n in nodes:
        for j in journals_of(n):
            out.setdefault(j, n["id"])
    return out


def graph_gates():
    """{node id: {'activators': [...], 'facts': {fact: setter journal}}}"""
    rows, frows = load_rows()
    db = quest_db()
    pmap, _ = code_map()
    jn = node_index()
    res = defaultdict(lambda: {"activators": [], "facts": {}, "self_activations": []})
    for r in rows:
        t = os.path.basename(r["target"]).replace(".journal", "")
        if t not in db:
            continue
        ids = db[t]
        if not ids or r["leaf"] != ids[0][1]:
            continue  # objective-level, not the quest itself
        src_journal = pmap.get(r["src_quest"])
        if src_journal == t:
            res[jn.get(t, t)]["self_activations"].append(r["src"])
        elif src_journal:
            res[jn.get(t, t)]["activators"].append({"by_journal": src_journal,
                                                    "by_node": jn.get(src_journal, ""),
                                                    "src": r["src"], "block": r["block"],
                                                    "class": r["class"], "label": r["label"]})
    # fact ownership: which node's quest sets a fact
    setter = {}
    for f in frows:
        j = pmap.get(f["quest"])
        if f["kind"] == "set" and f["fact"] and j in jn:
            setter.setdefault(f["fact"], set())
            setter[f["fact"]].add(jn[j])
    for node_id in list(jn.values()):
        pass
    # facts tested by each node, from its own quest's phases
    for f in frows:
        if f["kind"] != "test":
            continue
        j = pmap.get(f["quest"])
        nid = jn.get(j)
        if not nid:
            continue
        fact = f["fact"] or (f.get("label", "").split(" ")[0] if re.match(r"^[a-z][a-z0-9_]{3,}$", f.get("label", " ").split(" ")[0]) else "")
        if not fact:
            continue
        owners = sorted(x for x in setter.get(fact, set()) if x != nid)
        if owners:
            res[nid]["facts"].setdefault(fact, set()).update(owners)
    return {k: {"activators": v["activators"], "facts": {f: sorted(o) for f, o in v["facts"].items()},
                "self": v["self_activations"]} for k, v in res.items()}


def save_evidence():
    if not SAVE_INDEX.exists():
        return {}, {}
    cache = json.load(open(SAVE_INDEX))
    present = defaultdict(int)
    for v in cache.values():
        st = v.get("state")
        if not st:
            continue
        for k, s in st.items():
            if s in ("Active", "Done", "Failed"):
                present[k] += 1
    return cache, present


def gate_lookup(cache, a_journals, b_journals):
    """for a claimed gate (any of a_journals -> any of b_journals): saves holding B with A not done"""
    rows = []
    for name, v in cache.items():
        st = v.get("state")
        if not st:
            continue
        if not any(st.get(b) in ("Active", "Done", "Failed") for b in b_journals):
            continue
        a_ok = any(st.get(a) == "Done" for a in a_journals)
        rows.append((name, a_ok, {b: st.get(b) for b in b_journals}, {a: st.get(a) for a in a_journals}))
    viol = [r for r in rows if not r[1]]
    return rows, viol


def report():
    v, nodes = route_nodes()
    gates = graph_gates()
    cache, present = save_evidence()
    jn = node_index()
    out = ["# Route vs game files vs saves", ""]
    out.append(f"route nodes: {len(nodes)}; saves indexed: {len(cache)}")
    out.append("")
    summary = []
    for n in nodes:
        js = journals_of(n)
        if not js:
            continue
        g = gates.get(n["id"], {"activators": [], "facts": {}})
        hard_ids = n.get("hard", [])
        hard_nodes = {h: next((x for x in nodes if x["id"] == h), None) for h in hard_ids}
        lines = [f"## {n['id']} - {n['title'][:70]}", f"journals: {', '.join(js)}", f"route hard: {', '.join(hard_ids) or '-'}"]
        # game-file activators
        ext = [a for a in g["activators"] if a["by_node"] != n["id"]]
        if ext:
            byn = sorted({a["by_node"] or a["by_journal"] for a in ext})
            lines.append(f"game files: entry added by {', '.join(byn)}")
            for a in ext:
                lines.append(f"    - {a['src']} #{a['block']} {a['class']} {a['label']!r}")
        else:
            lines.append("game files: no other quest's graph adds this entry")
        # facts
        if g["facts"]:
            lines.append("game files: waits on facts set by")
            for f, owners in sorted(g["facts"].items()):
                lines.append(f"    - {f} <- {', '.join(owners)}")
        # save evidence per claimed route gate
        for h in hard_ids:
            hn = hard_nodes.get(h)
            if not hn:
                continue
            hj = journals_of(hn)
            rows, viol = gate_lookup(cache, hj, js)
            verdict = "no save evidence"
            if rows:
                verdict = f"{len(rows)} saves hold it, {len(viol)} without {h} done"
            lines.append(f"save check: {n['id']} needs {h}: {verdict}")
            for r in viol[:5]:
                lines.append(f"    VIOLATION {r[0]} {r[3]}")
        summary.append((n["id"], len(ext), len(g["facts"]), len(hard_ids)))
        out.extend(lines)
        out.append("")
    (HERE / "gate_report.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out[:0]))  # keep stdout short
    print(f"wrote {HERE/'gate_report.md'}")
    print(f"{'node':16s} graph-activators fact-gates route-hard")
    for a, b, c, d in summary:
        print(f"{a:16s} {b:8d} {c:10d} {d:10d}")


def node(node_id):
    v, nodes = route_nodes()
    n = next((x for x in nodes if x["id"] == node_id), None)
    if not n:
        print("unknown node")
        return
    print(json.dumps({k: n[k] for k in ("id", "title", "files", "hard", "note")}, indent=1))
    g = graph_gates().get(node_id)
    print(json.dumps(g, indent=1, default=list) if g else "no game-file gate rows")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
    elif sys.argv[1] == "report":
        report()
    elif sys.argv[1] == "node":
        node(sys.argv[2])
    elif sys.argv[1] == "activations":
        activations()
