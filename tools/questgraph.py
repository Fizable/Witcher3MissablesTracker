"""Read the game's own quest phase graphs (.w2phase) to find how a quest really starts.

This is the strict rule the tracker should use, instead of guessing a start gate from save
ordering. A quest's journal entry is activated by a block inside some quest phase's graph
(CJournalQuestBlock = add the entry; CJournalQuestTrackBlock = put it in the log / track it).
Walk backwards from that block to the phase entry and you get the game's own conditions.

  index(root)                 -> {journal_resource_lower: [phase files that mention it]}
  parse(path)                 -> lightweight wrapper around cr2w.parse with lookups
  G.blocks_for(journal)       -> [(block_export, journal_resource, guid_chain)]  who activates it
  G.backward(block_index)     -> [(depth, class, label)] from the phase entry down to the block

CLI:
  py questgraph.py build                        write ../../data/quest_graph.json (the quest graph)
  py questgraph.py starters <journal name>     who activates that quest's journal entry
  py questgraph.py gates <phase file> <journal>  the condition chain feeding its start block
  py questgraph.py index <journal>             which phase files mention it at all
"""
import json
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cr2w

from paths import JOURNAL_DIR, QUEST_ROOT, REDKIT_R4 as R4

# blocks that make a journal entry appear / become active in the quest log
START_BLOCKS = {"CJournalQuestBlock", "CJournalQuestTrackBlock"}
# blocks worth naming in a condition walk
NOTABLE = {
    "CQuestConditionBlock", "CQuestPauseConditionBlock", "CQuestFactsDBCondition", "CQuestAndBlock",
    "CQuestOrBlock", "CQuestXorBlock", "CSceneBlock", "CQuestSceneBlock", "CQuestPhaseInputBlock",
    "CQuestPhaseOutputBlock", "CQuestPauseBlock", "CQuestFactsDBChangingBlock", "CQuestScriptBlock",
    "CQuestInteractionDialogBlock", "CQuestStoryPhaseSetterBlock",
}


def journal_files():
    """journal file stem (e.g. 'q206berserkers') -> path"""
    out = {}
    for p in JOURNAL_DIR.glob("*.journal"):
        out[p.stem.lower()] = p
    return out


def index(needle):
    """Fast byte-level prefilter: which .w2phase mention this journal resource."""
    b = needle.encode() if isinstance(needle, str) else needle
    hits = []
    for p in QUEST_ROOT.rglob("*.w2phase"):
        try:
            if b in p.read_bytes():
                hits.append(p)
        except OSError:
            continue
    return hits


class G:
    """A parsed quest phase with graph lookups."""

    def __init__(self, path):
        self.path = Path(path)
        self.p = cr2w.parse(self.path)
        self._props = {}

    def props(self, i):
        if i not in self._props:
            if 1 <= i <= len(self.p["exports"]):
                self._props[i] = {x["name"]: x["value"] for x in cr2w.props(self.p, self.p["exports"][i - 1])}
            else:
                self._props[i] = {}
        return self._props[i]

    def cls(self, i):
        return self.p["exports"][i - 1]["className"] if 1 <= i <= len(self.p["exports"]) else ""

    def label(self, i):
        ps = self.props(i)
        for k in ("comment", "name", "caption", "factID", "factId"):
            v = ps.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    # ---- journal path resolution -------------------------------------------------
    def path_chain(self, chunk):
        """CJournalPath chain -> (root_resource, leaf_resource, [guids])"""
        res, guids, i, guard = None, [], chunk, 0
        while i and 1 <= i <= len(self.p["exports"]) and guard < 12:
            ps = self.props(i)
            r = ps.get("resource")
            r = r.get("ref_import") if isinstance(r, dict) else r
            if r:
                res = r
            g = ps.get("guid")
            if isinstance(g, dict) and g.get("raw_hex"):
                guids.append(g["raw_hex"])
            ch = ps.get("child")
            i = ch.get("ref_chunk") if isinstance(ch, dict) else None
            guard += 1
        return res, guids

    def blocks_for(self, journal_stem):
        """Blocks that activate this journal file. journal_stem e.g. 'q206berserkers'."""
        needle = journal_stem.lower()
        out = []
        for e in self.p["exports"]:
            if e["className"] not in START_BLOCKS:
                continue
            ps = self.props(e["index"])
            qe = ps.get("questEntry")
            chain = qe.get("ref_chunk") if isinstance(qe, dict) else None
            if not chain:
                continue
            res, guids = self.path_chain(chain)
            if res and needle in res.lower():
                out.append({"index": e["index"], "class": e["className"], "resource": res,
                            "guids": guids, "label": self.label(e["index"])})
        return out

    def failure_sockets(self, blocks):
        """The `Failure` inputs attached to a quest's journal blocks.

        A quest that can be lost does not merely lose an actor's community: its own phase graph has a
        `CJournalQuestBlock` whose input socket is named `Failure`. That is the game saying the quest
        can end here, and it is the only evidence strong enough to call a loss later on.

        This deliberately returns every attached socket, connected or not. Use `failure_sources()`
        when the question is whether the failure path is actually wired into a phase.
        """
        wanted = {b["index"] for b in blocks}
        out = []
        for i, s in self._sockets().items():
            if s["block"] in wanted and s["name"] == "Failure" and s["dir"] != "LSD_Output":
                out.append({"block": s["block"], "socket": i, "name": "Failure"})
        return out

    # ---- failure evidence -------------------------------------------------------
    def _sockets(self):
        """socket export -> {block, name, direction}; cached for one file."""
        if getattr(self, "_sock_cache", None) is None:
            out = {}
            for e in self.p["exports"]:
                if e["className"] not in ("CGraphSocket", "CQuestGraphSocket"):
                    continue
                ps = self.props(e["index"])
                b = ps.get("block")
                out[e["index"]] = {
                    "block": b.get("ref_chunk") if isinstance(b, dict) else None,
                    "name": ps.get("name", ""),
                    "dir": ps.get("direction", ""),
                }
            self._sock_cache = out
        return self._sock_cache

    def _connections(self):
        """[(source socket, destination socket)] for every graph connection in the file."""
        if getattr(self, "_conn_cache", None) is None:
            out = []
            for e in self.p["exports"]:
                if e["className"] != "CGraphConnection":
                    continue
                ps = self.props(e["index"])
                s = ps.get("source")
                d = ps.get("destination")
                s = s.get("ref_chunk") if isinstance(s, dict) else None
                d = d.get("ref_chunk") if isinstance(d, dict) else None
                if s and d:
                    out.append((s, d))
            self._conn_cache = out
        return self._conn_cache

    def failure_sources(self, block):
        """The blocks feeding this block's `Failure` input; empty means the socket is decorative."""
        socks = self._sockets()
        out = []
        for i, s in socks.items():
            if s["block"] != block or s["name"] != "Failure" or s["dir"] == "LSD_Output":
                continue
            for src, dst in self._connections():
                if dst == i and src in socks and socks[src]["block"]:
                    out.append(socks[src]["block"])
        return out

    def incoming_blocks(self, block):
        """Blocks connected to an input socket of `block` (outputs are followed backwards only)."""
        socks = self._sockets()
        out = []
        for i, s in socks.items():
            if s["block"] != block or s["dir"] == "LSD_Output":
                continue
            for src, dst in self._connections():
                if dst == i and src in socks and socks[src]["block"]:
                    out.append(socks[src]["block"])
        return out

    @staticmethod
    def ref_list(value):
        """A CR2W count-prefixed chunk-reference list, or a single chunk reference."""
        if not isinstance(value, dict):
            return []
        if value.get("ref_chunk"):
            return [value["ref_chunk"]]
        raw = value.get("raw_hex")
        if not raw:
            return []
        try:
            buf = bytes.fromhex(raw)
            if len(buf) < 4:
                return []
            n = struct.unpack_from("<I", buf, 0)[0]
            if 4 + 4 * n > len(buf):
                return []
            return [struct.unpack_from("<I", buf, 4 + 4 * i)[0] for i in range(n)]
        except (ValueError, struct.error):
            return []

    def _condition(self, i, out, seen, depth):
        """Collect journal/fact conditions from one condition export, following nested logic."""
        if i in seen or depth > 12 or not (1 <= i <= len(self.p["exports"])):
            return
        seen.add(i)
        cls = self.cls(i)
        ps = self.props(i)
        if cls == "CQuestJournalStatusCondition":
            ent = ps.get("entry")
            ref = ent.get("ref_chunk") if isinstance(ent, dict) else None
            res, guids = self.path_chain(ref) if ref else (None, [])
            out.append({"kind": "journal", "resource": res or "", "status": ps.get("status", ""),
                        "guids": guids})
            return
        if cls == "CQuestFactsDBCondition":
            out.append({"kind": "fact", "fact": ps.get("factId", ""),
                        "query": ps.get("queryFact", ""), "value": ps.get("value")})
            return
        for key in ("questCondition", "condition"):
            ref = ps.get(key)
            if isinstance(ref, dict) and ref.get("ref_chunk"):
                self._condition(ref["ref_chunk"], out, seen, depth + 1)
        for ref in self.ref_list(ps.get("conditions")):
            self._condition(ref, out, seen, depth + 1)

    def journal_conditions_upstream(self, block):
        """Every journal/fact condition that gates `block`, walking the graph backwards.

        This is what a reviewed loss window is checked against: a `Failure` input is evidence only
        when it is connected and its upstream conditions name the journal phase the window claims.
        A dangling `Failure` socket, or one gated by an unrelated quest, is not enough.
        """
        out = []
        seen_blocks = set()
        seen_conditions = set()

        def walk(b, depth):
            if b in seen_blocks or depth > 12 or not (1 <= b <= len(self.p["exports"])):
                return
            seen_blocks.add(b)
            ps = self.props(b)
            for key in ("questCondition", "condition"):
                ref = ps.get(key)
                if isinstance(ref, dict) and ref.get("ref_chunk"):
                    self._condition(ref["ref_chunk"], out, seen_conditions, 0)
            for ref in self.ref_list(ps.get("conditions")):
                self._condition(ref, out, seen_conditions, 0)
            for pred in self.incoming_blocks(b):
                walk(pred, depth + 1)

        walk(block, 0)
        return out

    # ---- graph ------------------------------------------------------------------
    def _socket(self, i):
        ps = self.props(i)
        b = ps.get("block")
        return {"index": i, "block": b.get("ref_chunk") if isinstance(b, dict) else None,
                "name": ps.get("name", ""), "dir": ps.get("direction", "")}

    def incoming(self, block):
        """[[(from_block, socket_name), ...]] predecessors of a block."""
        out = []
        for e in self.p["exports"]:
            if e["className"] != "CGraphConnection":
                continue
            ps = self.props(e["index"])
            d = ps.get("destination")
            d = d.get("ref_chunk") if isinstance(d, dict) else None
            if not d:
                continue
            if self._socket(d)["block"] != block:
                continue
            s = ps.get("source")
            s = s.get("ref_chunk") if isinstance(s, dict) else None
            if s:
                so = self._socket(s)
                out.append((so["block"], so["name"]))
        return out

    def backward(self, block, depth=0, seen=None, trail=None):
        """Walk back from a block to the phase entry, naming the conditions between."""
        seen = seen if seen is not None else set()
        trail = trail if trail is not None else []
        if depth > 12 or block in seen:
            return trail
        seen.add(block)
        preds = self.incoming(block)
        trail.append((depth, self.cls(block), self.label(block), block))
        for pb, sname in preds:
            if pb is None:
                continue
            self.backward(pb, depth + 1, seen, trail)
        return trail


GRAPH = Path(__file__).resolve().parent.parent / "data" / "quest_graph.json"
DATA = Path(__file__).resolve().parent.parent / "data"


def _json(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _primary(n, alias, allow, quests):
    """The bundle journal name a legacy route node reads first, or None for a manual node."""
    for f in n.get("files") or []:
        stem = f.split("|")[0].split("#")[0].lower()
        if stem in allow:
            return stem
        if alias.get(stem) in quests:
            return stem
    return None


def build():
    """Write data/quest_graph.json from the files, the frozen route and the reviewed settlements.

    The graph is the build source for the app's route: `starts` from the journal-activation blocks,
    `requires` from the reviewed fact edges (data/prereqs_review.json), `lost_when` from the reviewed
    cutoffs (data/cutoffs.json). The 25 hand-written hold-off events in data/legacy_events.json are
    the acceptance corpus: each is either matched to a lost_when edge by the quests it names, or
    recorded as dropped with the reason. Nothing from the legacy file is shipped as a rule.
    """
    idx = json.loads((Path(__file__).resolve().parent / "quest_index.json").read_text(encoding="utf-8"))
    alias = idx.get("alias", {})
    # bundle journal name -> REDkit stem (the index is keyed by the REDkit stem)
    redkit = {b: r for b, r in alias.items()}
    def rk(stem):
        return redkit.get(stem, stem)
    quests = idx["quests"]
    legacy = _json("legacy_route.json")
    nodes = {n["id"]: n for n in legacy["nodes"]}
    allow = set(alias) | set(quests)

    # -- starts: the block that adds each quest's own journal entry
    starts = {}
    for stem, q in sorted(quests.items()):
        acts = q.get("activators") or []
        if not acts:
            continue
        bundle = (q.get("bundle_names") or [stem])[0]
        starts[bundle] = [{"kind": "journal_entry", "block": a.get("block"), "class": a.get("class"),
                           "resource": a.get("resource"), "file": a.get("file"),
                           "source": {"kind": "file", "value": a.get("file")}}
                          for a in acts]

    # -- requires: only the reviewed fact gates. Every other legacy hard edge is dropped: it was a
    # hand-written ordering, and a quest with no positively named gate is 'available', not locked.
    requires, dropped_requires = {}, []
    rev = _json("prereqs_review.json")
    for item in rev.get("items", []):
        # the review was written against the 0.1.9 step ids; the live ids are the journal stems
        src = nodes.get(item.get("legacy_step", item["step"]))
        dst = nodes.get(item.get("legacy_requires", item["requires"]))
        s = _primary(src, alias, allow, quests) if src else None
        d = _primary(dst, alias, allow, quests) if dst else None
        if not s or not d:
            dropped_requires.append({"step": item["step"], "requires": item["requires"],
                                     "why": "one side is a manual step, so there is no journal file to key a route lock on"})
            continue
        if item["decision"] == "fact":
            requires.setdefault(s, []).append({
                "requires": d, "mechanism": "fact", "facts": item.get("facts", []),
                "file": item.get("files", ""), "why": item.get("why", ""),
                "source": {"kind": "file", "value": item.get("files", "")}})
        else:
            dropped_requires.append({"step": s, "requires": d, "why": item.get("why", "")})

    # -- lost_when: the reviewed cutoffs, each naming the resource and the file that switches it off
    cut = _json("cutoffs.json")
    lost_when, dropped_cutoffs = [], []
    for item in cut.get("items", []):
        files = item.get("files") or []
        mech = next((f for f in files if "CDeactivateSpawnset" in f), "")
        if not files or not mech:
            dropped_cutoffs.append({"id": item.get("id"), "why": "no CDeactivateSpawnset file named"})
            continue
        lost_when.append({"id": item["id"], "event_name": item.get("event_name", item["id"]), "affected": item["affects"], "closed_by": item["closed_by"],
                          "resource": item["resource"], "mechanism": "CDeactivateSpawnset",
                          "file": mech.split(" switches off ")[0],
                          "source": {"kind": "file", "value": mech}})

    # -- the legacy events, as an acceptance corpus
    legacy_events = _json("legacy_events.json").get("events", {})
    by_event = {}
    for n in legacy["nodes"]:
        s = _primary(n, alias, allow, quests)
        for e in n.get("by") or []:
            if s:
                by_event.setdefault(e, set()).add(s)
    acceptance = []
    for eid, ev in sorted(legacy_events.items()):
        fires = sorted({f.split("#")[0].lower() for f, _sts in ev.get("fires", [])})
        affected = sorted(by_event.get(eid, set()))
        hit = next((l for l in lost_when
                    if set(l["closed_by"]) & set(fires) and set(l["affected"]) & set(affected)), None)
        if hit:
            acceptance.append({"id": eid, "name": ev.get("name", ""), "status": "replaced",
                               "replaced_by": hit["id"], "fires": fires, "affected": affected})
        else:
            why = ("no reviewed CDeactivateSpawnset edge names both the closing and the affected quest"
                   if fires and affected else
                   "the event names no journal trigger this install can read" if not fires else
                   "the event's affected steps are not journal quests")
            acceptance.append({"id": eid, "name": ev.get("name", ""), "status": "dropped",
                               "why": why, "fires": fires, "affected": affected})

    out = {
        "note": "The quest graph the app's route is built from. `starts` is the game's own journal-activation block; `requires` is the reviewed fact edges (data/prereqs_review.json), with every hand-written ordering dropped unless the files name the condition; `lost_when` is the reviewed cutoff set (data/cutoffs.json), each naming the CDeactivateSpawnset file. `legacy_events` is the acceptance corpus: the 25 hand-written 0.1.9 events, each replaced by a file edge or dropped with its reason. Nothing wiki-sourced is loaded at run time.",
        "sources": {"index": "tools/quest_index.json", "route": "data/legacy_route.json",
                    "prereqs": "data/prereqs_review.json", "cutoffs": "data/cutoffs.json",
                    "legacy_events": "data/legacy_events.json"},
        "frontier": {
            "states": {
                "done": "journal Done/Assumed/N/A, or a tick the journal does not contradict",
                "in_log": "journal Active or Failed",
                "gated": "not in the log and the route names an unmet prerequisite",
                "available": "not in the log, no unmet prerequisite, and a start block is known",
                "unknown": "not in the log and no start block is known; shown as available, never suppressed",
            },
            "rule": "A quest is hidden from DO NEXT only when the route names the gate; no activator never means cannot start.",
        },
        "starts": starts,
        "requires": requires,
        "lost_when": lost_when,
        "dropped_requires": dropped_requires,
        "dropped_cutoffs": dropped_cutoffs,
        "legacy_events": acceptance,
    }
    GRAPH.write_text(json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    counts = {}
    for a in acceptance:
        counts[a["status"]] = counts.get(a["status"], 0) + 1
    print(f"wrote {GRAPH.name}: {len(starts)} quests with a start block, {sum(len(v) for v in requires.values())} "
          f"reviewed prerequisites, {len(lost_when)} loss edges; legacy events {counts}")
    return out


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "build":
        build()
        return
    if len(sys.argv) < 3:
        print(__doc__)
        return
    cmd, arg = sys.argv[1], sys.argv[2]
    if cmd == "index":
        for p in index(arg):
            print(p.relative_to(R4))
    elif cmd == "starters":
        print(f"# phase files mentioning {arg}:")
        for p in index(arg):
            g = G(p)
            bl = g.blocks_for(arg)
            tag = "  <-- activates it" if bl else ""
            print(f"  {p.relative_to(R4)}{tag}")
            for b in bl:
                print(f"      #{b['index']} {b['class']} via {b['resource']} label={b['label']!r}")
    elif cmd == "gates":
        g = G(sys.argv[2])
        journal = sys.argv[3]
        for b in g.blocks_for(journal):
            print(f"start block #{b['index']} {b['class']} label={b['label']!r}")
            for d, cls, lab, idx in g.backward(b["index"]):
                if cls in NOTABLE or d < 2:
                    print(f"    d{d} {cls:32s} {lab[:90]}")


if __name__ == "__main__":
    main()
