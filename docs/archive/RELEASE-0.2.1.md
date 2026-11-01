# Release 0.2.1 - a quieter interface

2026-10-28. 0.2.0 made the rules come from the game's files. This release makes the screen say them
in the player's terms instead of the tracker's.

## What changed

- **The top section is now `WHAT IS AT STAKE`.** Each card is a label plus one sentence: what is
  lost, or what is still winnable, and which quest caused it. The file mechanism, the save-status
  transcript and the duplicate action line are gone from the card. Clicking anywhere on the card
  opens the quest.
- **The quest page is for the quest.** It now leads with the one-line description, the warning (if
  any), and the objective the save itself marks active. When there are more objectives, they sit
  behind `Show all N objectives` instead of filling the page.
- **Source detail is optional.** `CJournalQuestBlock`, phase paths, the activation block, the fact
  conditions and the save transcript are under a collapsed `Technical details` section. The
  former `Added to your quest log by ...` line no longer appears in the page itself.
- **Labels say what to do, not what the tracker calls it.** `CUTOFF NOW - YOU ARE INSIDE IT` became
  `DO THIS NOW`; lost entries say `LOST IN THIS SAVE`; a lost quest no longer also carries the
  redundant `missable` chip.
- **No data changed.** `route.json`, `derived.json`, the reviewed cutoffs and the route
  prerequisites are byte-identical to 0.2.0.

## Checks run

```
cargo test
  15 passed, 0 failed
```

The interface was rendered against the mid-game `--view` payload and its `get_detail` data: three
top-section entries, the lost warning, four active objectives, the collapsed full objective list and
the collapsed technical section. The empty, failed, manual-tick and no-warning pages are unchanged
flows covered by the same renderer and the backend tests.

The packaged exe was built by `package.ps1`, and its `--view` output was checked against the release's
own `data/`.
