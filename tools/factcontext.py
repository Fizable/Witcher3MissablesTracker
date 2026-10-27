"""Story context around a fact: where the game sets it, and what sits next to that in the graph.

  py factcontext.py <fact name> [depth]

Prints, per phase file that sets the fact, the labelled blocks within <depth> graph hops (default 2),
which is how you see the story beat a fact belongs to without reading the whole quest.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cr2w

from paths import REDKIT_R4 as R4


def walk(v, out):
    if isinstance(v, dict):
        out.append(v)
        for x in v.values():
            walk(x, out)
    elif isinstance(v, list):
        for x in v:
            walk(x, out)


def label(G, i):
    ps = G.props(i)
    for k in ("comment", "name", "caption"):
        v = ps.get(k)
        if isinstance(v, str) and v.strip() and not v.strip().isdigit():
            return v.strip()
    if G.cls(i) == "CQuestFactsDBChangingBlock":
        return f"{ps.get('factID')} = {ps.get('value')}"
    return ""


def neighbourhood(path, fact, depth=2):
    p = cr2w.parse(path)
    cache = {}

    def props(i):
        if i not in cache:
            cache[i] = {x["name"]: x["value"] for x in cr2w.props(p, p["exports"][i - 1])} if 1 <= i <= len(p["exports"]) else {}
        return cache[i]

    cls = lambda i: p["exports"][i - 1]["className"] if 1 <= i <= len(p["exports"]) else ""
    starts = []
    for e in p["exports"]:
        if e["className"] == "CQuestFactsDBChangingBlock" and any(
            x.get("factID") == fact or x.get("factId") == fact for x in [props(e["index"])]
        ):
            starts.append(e["index"])
    if not starts:
        return []

    edges = {}
    socks = {}
    for e in p["exports"]:
        if e["className"] == "CGraphConnection":
            ps = props(e["index"])
            s = ps.get("source"); d = ps.get("destination")
            s = s.get("ref_chunk") if isinstance(s, dict) else None
            d = d.get("ref_chunk") if isinstance(d, dict) else None
            if s and d:
                edges.setdefault(s, []).append(d)
        elif e["className"] in ("CQuestGraphSocket", "CGraphSocket", "CQuestGraphSocket"):
            ps = props(e["index"])
            b = ps.get("block")
            socks[e["index"]] = (b.get("ref_chunk") if isinstance(b, dict) else None, str(ps.get("name") or ""),
                                 ps.get("direction"))
    out = []
    for s in starts:
        out.append((s, cls(s), label(None, s) if False else "starts here"))
    return out


def context(fact, depth=2):
    for p in sorted((R4 / "quests").rglob("*.w2phase")):
        try:
            if fact.encode() not in p.read_bytes():
                continue
        except OSError:
            continue
        import questgraph as qg
        G = qg.G(p)
        hit = [e["index"] for e in G.p["exports"]
               if e["className"] == "CQuestFactsDBChangingBlock"
               and (G.props(e["index"]).get("factID") == fact or G.props(e["index"]).get("factId") == fact)]
        if not hit:
            continue
        print(f"===== {p.relative_to(R4)}  sets {fact} at {hit}")
        seen, frontier = set(), list(hit)
        for d in range(depth + 1):
            nxt = []
            for b in frontier:
                if b in seen:
                    continue
                seen.add(b)
                lab = G.label(b)
                if lab and not lab.isdigit():
                    print(f"   d{d} {'<*>' if b in hit else '   '} {G.cls(b):30s} {lab[:80]!r}")
                for pb, _ in G.incoming(b):
                    if pb and pb not in seen:
                        nxt.append(pb)
            frontier = nxt


if __name__ == "__main__":
    context(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 2)
