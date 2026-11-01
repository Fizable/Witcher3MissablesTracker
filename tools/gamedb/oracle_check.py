"""Score the database's quest-loss paths against the player's saves.

    py tools/gamedb/oracle_check.py [--list]

Every row of `fail_paths` (for a quest's own entry) is a full condition: all of its block tests must
come out as required for the game to fail quest B on that path. A save does not say where inside a
quest the game is, so a path that only tests B's own facts and journal (an internal timer, a "did
you finish before leaving" check) cannot be scored. A cross-quest path tests at least one fact
written only by other quests or another quest's journal status: that is a cutoff. It is
contradicted when B finished at a save step whose parent save already satisfied the whole path while
B was active (and, for a path in another quest A's files, A was already finished, since A's own
flow decides when the path runs), and confirmed when B failed at a step whose child save satisfies it.

Most paths are untested: one player rarely walks into a cutoff. Read-only.
"""
import json
import sqlite3
import sys
from collections import defaultdict

import common
from semantic import fact_test_holds

GROUPS = {"LO_And": all, "LO_Or": any, "LO_Nand": lambda xs: not all(xs), "LO_Nor": lambda xs: not any(xs),
          "LO_Xor": lambda xs: sum(xs) % 2 == 1}


def path_holds(trail, facts, journal):
    """True when every block test on the path comes out as the path requires on this save."""
    for step in trail:
        results = []
        for t in step["tests"]:
            if t["kind"] == "journal":
                results.append(journal.get(t.get("entry"), "JS_Inactive") == t.get("status"))
            else:
                results.append(fact_test_holds(t, facts.get(t.get("fact"), 0) or 0))
        group = step["tests"][0].get("group", "LO_And") if step["tests"] else "LO_And"
        if GROUPS.get(group, all)(results) != step["require"]:
            return False
    return True


def main(argv):
    c = sqlite3.connect(f"file:{common.DB}?mode=ro", uri=True)
    sv = sqlite3.connect(f"file:{common.SAVES_DB}?mode=ro", uri=True)
    cache = {}

    def state(sid):
        if sid not in cache:
            if len(cache) > 200:
                cache.clear()
            cache[sid] = (dict(sv.execute("SELECT fact, value FROM save_facts WHERE save_id=?", (sid,))),
                          dict(sv.execute("SELECT guid, status FROM save_journal WHERE save_id=?", (sid,))))
        return cache[sid]

    def title(g):
        r = c.execute("SELECT COALESCE(s.text, q.stem) FROM journal_quests q LEFT JOIN strings s "
                      "ON s.loc_id=q.title_loc_id WHERE guid=?", (g,)).fetchone()
        return r[0] if r else g

    paths = defaultdict(list)
    writers = defaultdict(set)
    for fact, owner in c.execute("SELECT DISTINCT fact, owner_quest FROM fact_ops WHERE op IN ('set','add')"):
        writers[fact].add(owner)

    def external(t, quest):
        if t["kind"] == "journal":
            return t.get("quest") not in (None, quest)
        w = writers.get(t.get("fact"), set())
        return bool(w) and quest not in w

    internal = 0
    for fid, fb, entry, quest, owner, n, cut, tj in c.execute(
            """SELECT p.file_id, p.fail_block, p.entry_guid, p.quest_guid, p.owner_quest, p.path, p.truncated,
                      p.tests_json
               FROM fail_paths p JOIN journal_entries e ON e.guid=p.entry_guid
               WHERE e.class='CJournalQuest' AND p.n_tests > 0"""):
        trail = json.loads(tj)
        if not any(external(t, quest) for st in trail for t in st["tests"]):
            internal += 1
            continue
        paths[entry].append((fid, fb, n, cut, trail, owner if owner != quest else None))
    out = {"contradicted": [], "confirmed": []}
    tested = set()
    for entry, plist in paths.items():
        steps = c.execute("SELECT from_save, to_save, to_status FROM journal_transitions "
                          "WHERE guid=? AND to_status IN ('JS_Success','JS_Failed')", (entry,)).fetchall()
        for frm, to, status in steps:
            facts, journal = state(frm if status == "JS_Success" else to)
            for fid, fb, n, cut, trail, owner in plist:
                if status == "JS_Success" and journal.get(entry) != "JS_Active":
                    continue
                # a path in another quest's files runs inside that quest's flow: only once that quest
                # is finished is it certain the game went past the failure point
                if status == "JS_Success" and owner and journal.get(owner) != "JS_Success":
                    continue
                tested.add((entry, fid, fb, n))
                if path_holds(trail, facts, journal):
                    key = "contradicted" if status == "JS_Success" else "confirmed"
                    out[key].append((title(entry), fid, fb, n, bool(cut), frm, to))
    total = sum(len(v) for v in paths.values())
    print(f"{internal} paths test only the failed quest's own state and are not scored")
    print(f"{total} cross-quest failure paths over {len(paths)} quests; {len(tested)} were reached in a save step "
          f"in the saves; contradicted {len({r[:4] for r in out['contradicted']})}, "
          f"confirmed {len({r[:4] for r in out['confirmed']})}")
    if "--list" in argv or out["contradicted"]:
        seen = set()
        for key in ("contradicted", "confirmed"):
            for name, fid, fb, n, cut, frm, to in out[key]:
                if (key, name, fid, fb, n) in seen:
                    continue
                seen.add((key, name, fid, fb, n))
                path = c.execute("SELECT path FROM files WHERE file_id=?", (fid,)).fetchone()[0]
                print(f"  {key}: {name} - block {fb} path {n}{' (truncated)' if cut else ''} in {path}")


if __name__ == "__main__":
    main(sys.argv[1:])
