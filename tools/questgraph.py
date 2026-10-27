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
  py questgraph.py starters <journal name>     who activates that quest's journal entry
  py questgraph.py gates <phase file> <journal>  the condition chain feeding its start block
  py questgraph.py index <journal>             which phase files mention it at all
"""
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


def main():
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
