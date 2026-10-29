# Manual route steps — the 11-step audit

**Reviewed:** 2026-10-28. **Input:** the current `tools/quest_index.json` (405 `CJournalQuest`
entries), `data/route_overrides.json`, and the generated `data/route.json`.

The 1.0.0 route had 403 file-derived quest steps plus 11 hand-written bookkeeping steps (414 route
nodes). This audit tested every one of those 11 against the current journal index. Two are exact
duplicates of file-derived quests and are replaced; nine are kept and labelled
`provenance: manual_reviewed`.

This is the reviewed source for every kept row's `review_source`, and for the `manual_replaced`
rows. Manual rows are never called Tier A: they are the user's own checklist, not a journal claim.
The audited denominator is therefore **412 route nodes = 403 quests + 9 manual steps**. The Gwent
section still has 11 nodes (10 file-derived quests + the reviewed Vegelbud matches row).

| # | baseline id | decision | replacement / reason |
|---:|---|---|---|
| 1 | `wo_prologue` | kept | the prologue visit/card checklist is not a journal status |
| 2 | `wo_poi` | kept | White Orchard points of interest have no journal entry |
| 3 | `ve_forefathers` | **replaced** | exact duplicate of `q108eve`; that journal now supplies the step |
| 4 | `ve_keira_km` | kept | the Keira choice is a world state answered by the `keira_sent` flag |
| 5 | `no_vegelbud` | kept | the three Gwent matches are not separate journal quests |
| 6 | `km_save` | kept | a player checkpoint, not game progress |
| 7 | `ci_c1` | kept | a Ciri scene choice inside `q110postbattle`, not a separate journal |
| 8 | `ci_c2` | kept | a second Ciri scene choice inside `q110postbattle` |
| 9 | `ci_bald` | **replaced** | exact duplicate of `q111imlerith`; the manual row had no separate choice |
| 10 | `ci_c3` | kept | a Ciri scene choice inside `q310preparationsnovigrad` |
| 11 | `hos_shakes` | kept | the Shani/Shakeslock visit inside `q601intro` is a checkpoint, not a journal |

## Replaced rows

### ve_forefathers

The legacy title was exactly **Forefathers' Eve**, with the note "No journal file found." The current
game index now carries that quest as `q108eve` (`CJournalQuest` name locId 308555, level 7, base
`Q108 Forfather's Eve`, one bundle, a file-derived branch). The route already contains `q108eve`
with `files: ["q108eve"]`. Keeping the manual row would count the same quest twice. Replaced by
`q108eve`; no warning or choice text was removed because the manual row carried neither.

### ci_bald

The legacy row was **Bald Mountain**, with the note "No journal file identified." That is no longer
true: the journal index carries `q111imlerith` (title `Bald Mountain`, name locId 337344, level 26,
one bundle). The route already contains it, and the manual row adds no separate choice or
bookkeeping state. Replaced by `q111imlerith`; the file-derived row keeps the quest and its
dialogue-choice flag.

## Kept rows

The evidence below is why each row cannot be read from a `CJournalQuest` status. The exact title and
the reviewed source date are in `data/route_overrides.json`; this section is the source document the
checker resolves the anchor against.

### wo_prologue

The prologue is a sequence of visits, pickups and card purchases inside the prologue quests. The
journal records the quests, not the individual pickups, so a tick is the only state the tracker can
hold. The row contains no choice text and is marked manual.

### wo_poi

White Orchard's points of interest are not one `CJournalQuest` status. The save cannot distinguish
"visited this point" from "did not"; the row is a review checklist, not a file-derived quest claim.

### ve_keira_km

Sending Keira to Kaer Morhen is a world-state choice. The app asks it in **My game** as the
`keira_sent` flag, and that answer decides which of `Brothers In Arms: Velen` and `A Final Kindness`
is in the run. There is no separate journal entry for the choice itself.

### no_vegelbud

The three Vegelbud Gwent matches happen inside `A Matter of Life and Death` (`sq301triss`). The
Gwent journal entries do not record each match as a separate quest, so the row is a bookkeeping
checklist. The card ledger remains in section 4.4's data; this row does not claim a card.

### km_save

A pre-Isle of Mists save is a player checkpoint, not game progress. No journal entry can ever mark
it done. It stays as a bookkeeping row so the route can warn before the point of no return.

### ci_c1

`Blood on the Battlefield` (`q110postbattle`) is file-derived, but the individual Ciri scene choices
are not separate journal statuses. The row marks the first choice point without shipping its text;
the reviewed outcome guidance carries the exact line where one is needed.

### ci_c2

The second Ciri choice point in `q110postbattle`. Same reason as `ci_c1`; the manual row marks a
decision inside the quest, not a second quest.

### ci_c3

The Ciri choice in `Final Preparations` (`q310preparationsnovigrad`). The quest is file-derived; the
individual scene choice is not a journal status, so it stays a manual marker without its text.

### hos_shakes

The Shani/Shakeslock visit happens inside the Hearts of Stone opening (`q601intro`). It is a
checkpoint before the Temple of Lilvani, not a separate `CJournalQuest`; the row keeps that
bookkeeping point and does not claim a quest status.

## What the checker enforces

`tools/matrixcheck.py` (and `tools/test_matrix.py`) reads this file, `data/route_overrides.json`,
`data/route.json` and `tools/quest_index.json` and fails when:

- the audited denominator is not 412 (403 quest + 9 manual), or the 2 replacements are missing;
- a kept manual row lacks `provenance: manual_reviewed`, a reason, this source and its anchor, or a
  review date;
- a game-file row claims manual provenance, or a manual row claims a file;
- a replaced id is still in the route, or its replacement is not a file-derived route row;
- a `when` condition is not backed by a route flag, or a debug exclusion has no mechanism;
- the current README, package README, backend contract or route payload carries a stale route count;
- the four chosen targets are in conflicting selection groups or named by an exclusive edge.

The UI shows `MANUAL REVIEWED` on every kept manual row and its detail pane shows the reason and
source; the route payload carries the same fields. A tick on such a row is never reported as Tier A.
