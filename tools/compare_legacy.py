"""Compare the frozen 0.1.9 route with the generated 0.2 route.

One-shot, read-only. Nothing here is loaded by the app. It answers a single question for the release
notes: where did the hand-written route say something the generated route does not?

  py compare_legacy.py                 write legacy_comparison.md and print a summary
  py compare_legacy.py --print         print the report instead of writing it

For every legacy node the live ids are its journal files (all of them exist as route ids on this
install). The report lists a changed suggested level, a title that is no longer the hand-written
editorial title, and the hand-written note that the generated route no longer carries. The 25 legacy
events are reported from data/quest_graph.json: replaced by a file edge, or dropped with the reason.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import HERE, TRACKER

OUT = HERE / "legacy_comparison.md"
TAG = re.compile(r"<[^>]+>")
SPACE = re.compile(r"\s+")


def clean(text):
    return SPACE.sub(" ", TAG.sub(" ", text or "")).strip()


def load(name):
    return json.loads((TRACKER / "data" / name).read_text(encoding="utf-8"))


def main():
    route = load("route.json")
    graph = load("quest_graph.json")
    legacy = load("legacy_route.json")
    byid = {n["id"]: n for n in route["nodes"]}

    rows, changed_level, changed_title = [], 0, 0
    for old in legacy.get("nodes", []):
        live = sorted({f.split("|")[0].split("#")[0].lower() for f in old.get("files", [])})
        row = {"legacy": old["id"], "live": live, "old_title": old.get("title", ""),
               "old_lv": old.get("lv", ""), "note": old.get("note", ""), "level": [], "title": []}
        for qid in live:
            new = byid.get(qid)
            if not new:
                row["level"].append(f"{qid}: missing from the generated route")
                continue
            if (old.get("lv") or "") != (new.get("lv") or ""):
                changed_level += 1
                row["level"].append(f"{qid}: {old.get('lv') or '-'} -> {new.get('lv') or '-'}")
            old_title = clean(old.get("title", ""))
            new_title = clean(new.get("title", ""))
            if old_title and new_title and old_title != new_title:
                changed_title += 1
                row["title"].append(f"{qid}: {old_title} -> {new_title}")
        if row["level"] or row["title"] or row["note"]:
            rows.append(row)

    events = graph.get("legacy_events", [])
    replaced = [e for e in events if e.get("status") == "replaced"]
    dropped = [e for e in events if e.get("status") == "dropped"]

    lines = ["# Legacy 0.1.9 route vs the generated 0.2 route", "",
             f"{len(legacy.get('nodes', []))} legacy route nodes, {len(route['nodes'])} generated route nodes. "
             f"{len(rows)} legacy nodes carry a note, a changed level or a changed title.", "",
             "## Suggested levels", "",
             f"{changed_level} live step(s) changed level. Every level in `route.json` now comes from the "
             "game's own `quest_levels.csv`; the old levels were hand-typed.", ""]
    for row in rows:
        if not row["level"]:
            continue
        lines.append(f"- `{row['legacy']}` -> {', '.join(row['live']) or '(manual)'}")
        lines += [f"  - {x}" for x in row["level"]]

    lines += ["", "## Titles", "",
              f"{changed_title} live step(s) use the game's own quest-log name instead of the old editorial "
              "title. The old title often carried the note; that note is no longer part of the route.", ""]
    for row in rows:
        if not row["title"]:
            continue
        lines.append(f"- `{row['legacy']}`")
        lines += [f"  - {x}" for x in row["title"]]

    lines += ["", "## Notes removed from the route", "",
              "Every 0.1.9 hand-written `note` is gone. Where the note contained a rule, it is either a "
              "reviewed cutoff (`data/cutoffs.json`), a reviewed prerequisite (`data/prereqs_review.json`) "
              "or it is not shipped. This is the full list for comparison.", ""]
    for row in rows:
        if not row["note"]:
            continue
        lines.append(f"- `{row['legacy']}` -> {', '.join(row['live']) or '(manual)'}: {clean(row['note'])}")

    lines += ["", "## The 25 legacy events", "",
              f"{len(replaced)} replaced by a reviewed `CDeactivateSpawnset` edge, {len(dropped)} dropped "
              "with the reason recorded. Nothing from `legacy_events.json` is a rule in 0.2.", ""]
    for e in replaced:
        lines.append(f"- replaced: **{e.get('name', e.get('id'))}** by `{e.get('replaced_by')}`")
    for e in dropped:
        lines.append(f"- dropped: **{e.get('name', e.get('id'))}** - {e.get('why', '')}")

    text = "\n".join(lines) + "\n"
    if "--print" in sys.argv:
        print(text)
    else:
        OUT.write_text(text, encoding="utf-8")
        print(f"wrote {OUT.name}: {len(rows)} legacy nodes with a difference; "
              f"{len(replaced)} events replaced, {len(dropped)} dropped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
