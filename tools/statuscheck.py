"""Old vs new quest-status reading, over every save. Read-only.

old: quest_db.json's first id for the journal file (what the tracker shipped, and what bundles.rs
     derived from the first "name GUID" string it saw)
new: the journal file's own CJournalQuest entry, falling back to the most advanced entry of the same
     file when the game leaves that entry inactive (what the fixed tracker does)

  py statuscheck.py
"""
import glob
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import save_reader as sr
import saveindex as si

RANK = {"JS_Success": 3, "JS_Active": 2, "JS_Failed": 1}
NAME = {"JS_Success": "Done", "JS_Active": "Active", "JS_Failed": "Failed"}


def both_rules(table, db, save):
    raw = sr.load_raw(save)
    by = {}
    for e in sr.journal(raw, sr.name_table(raw)):
        if e["guid"]:
            by[e["guid"].lower()] = e["status"]
    out = {}
    for short, guids in table.items():
        if not guids:
            continue
        ids = db.get(short) or []
        old = by.get(si.guid_raw(ids[0][1]), "") if ids else ""
        own = by.get(guids[0].lower(), "")
        if own not in RANK:
            own = max((g for g in guids[1:]), key=lambda g: RANK.get(by.get(g.lower(), ""), 0), default="")
            own = by.get(own.lower(), "")
        out[short] = (NAME.get(old, "Inactive"), NAME.get(own, "Inactive"))
    return out


def main():
    table = si.quest_table()
    db = si.quest_db()
    saves = si.save_files()
    reg_old, reg_new, diffs = Counter(), Counter(), Counter()
    for i, f in enumerate(saves, 1):
        for short, (old, new) in both_rules(table, db, f).items():
            if old != "Inactive":
                reg_old[short] += 1
            if new != "Inactive":
                reg_new[short] += 1
            if old != new:
                diffs[short] += 1
        if i % 100 == 0:
            print(f"  {i}/{len(saves)}", flush=True)
    print(f"\nquests where the new rule registers in FEWER saves (regressions):")
    lost = [(s, reg_old[s], reg_new[s]) for s in reg_old if reg_new[s] < reg_old[s]]
    print("  none" if not lost else "")
    for s, a, b in sorted(lost, key=lambda x: x[1] - x[2], reverse=True)[:20]:
        print(f"     {s:28s} {a} -> {b}")
    print(f"\nquests gained:")
    for s in sorted(reg_new, key=lambda s: reg_new[s] - reg_old.get(s, 0), reverse=True)[:10]:
        gain = reg_new[s] - reg_old.get(s, 0)
        if gain > 0:
            print(f"     {s:28s} {reg_old.get(s,0)} -> {reg_new[s]}")
    print(f"\nquests whose status differs in more than 10% of saves:")
    n = len(saves)
    for s, c in diffs.most_common():
        if c > n * 0.1:
            print(f"     {s:28s} {c}/{n} saves differ ({reg_old[s]} -> {reg_new[s]} registered)")


if __name__ == "__main__":
    main()
