"""Score the database's loss claims against the player's saves.

    py tools/gamedb/oracle_check.py [max_hops]

For every `fail_when_fact` relation (within max_hops, default 6) the claim is "once fact F is set,
quest B can no longer finish". A save step where B became JS_Success while F was already set in the
parent save contradicts it; a step where B became JS_Failed with F set supports it. Most claims are
untested: one player rarely runs into a cutoff. Read-only.
"""
import json
import sqlite3
import sys

import common


def main(max_hops=6):
    c = sqlite3.connect(f"file:{common.DB}?mode=ro", uri=True)
    c.execute(f"ATTACH 'file:{common.SAVES_DB}?mode=ro' AS sv")

    def title(g):
        r = c.execute("SELECT COALESCE(s.text, q.stem) FROM journal_quests q LEFT JOIN strings s "
                      "ON s.loc_id=q.title_loc_id WHERE guid=?", (g,)).fetchone()
        return r[0] if r else g

    pairs = {}
    for a, b, ev in c.execute("SELECT a_guid, b_guid, evidence FROM quest_relations WHERE kind='fail_when_fact'"):
        for e in json.loads(ev):
            if e.get("hops", 99) <= max_hops and e.get("fact"):
                pairs.setdefault((b, e["fact"]), a)
    q = """SELECT COUNT(*) FROM journal_transitions t JOIN sv.save_facts f
           ON f.save_id=t.from_save AND f.fact=? AND f.value>=1 WHERE t.guid=? AND t.to_status=?"""
    out = {"contradicted": [], "confirmed": [], "untested": []}
    for (b, fact), a in sorted(pairs.items()):
        bad = c.execute(q, (fact, b, "JS_Success")).fetchone()[0]
        good = c.execute(q, (fact, b, "JS_Failed")).fetchone()[0]
        key = "contradicted" if bad else "confirmed" if good else "untested"
        out[key].append((title(b), fact, title(a), bad or good))
    print(f"{len(pairs)} fact-triggered loss claims within {max_hops} hops: "
          + ", ".join(f"{k} {len(v)}" for k, v in out.items()))
    for k in ("contradicted", "confirmed"):
        for row in out[k]:
            print(f"  {k}: {row[0]} lost once {row[1]} is set (written by {row[2]}), {row[3]} save step(s)")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 6)
