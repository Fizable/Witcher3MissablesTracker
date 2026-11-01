# Witcher 3 Missables Tracker 1.3.1

Released: 2026-10-30
Previous package: `dist/Witcher3MissablesTracker-1.3.0/` (left untouched)

1.3.1 is the published package for the 1.3 line. 1.3.0 rebuilt the window around a single payload
computed by the backend; 1.3.1 fixes a no-save state leak found in its post-release audit. Both are
described here, because this page publishes 1.3.1 and users coming from 1.2.2 see all of it at once.

## What is new since 1.2.2

**One NOW band, and only when it matters.** A sticky band appears only while an action can still
change the outcome: a loss that already happened, a story event that would fail a quest you still
have open, a choice that matters to the endings in play, or a missable quest or card window you can
act on now. Its tags are fixed strings: `LOST IN THIS SAVE`, `CUTOFF PASSED - CHECK NOW`,
`DO THIS NOW`, `MISSABLE` and `ENDING CHOICE AHEAD`, with `WATCH OUT` as the fallback. A card window
that is still ahead is not a warning and never enters the band; it is a row in MORE > CARDS > LATER.
When nothing is at stake the band disappears.

**UP NEXT carries only what you can act on now.** The quest you are tracking, quests already in your
log, and the one plan step that is next. Future goal steps sit under one collapsed PLAN AHEAD line;
unlocked route steps that are not in the log stay in PROGRESS. A plan step and a quest are one card,
never two, and the exact line to say appears only on the tracked goal step.

**A tick is a note, not a status.** On a step read from the game files, ticking is a note for every
journal state, including Not started: PROGRESS shows a pencil rather than a green check, the card
keeps the journal's state and the warning does not move. Manual rows still use the tick as status.

**Guidance is one line, not the plan.** Turning guidance off removes the quoted line and keeps the
plan, its chips and the selected goal.

**Detail and search give the same answer.** `check_quest` and the quest page now share one verdict
function, so search can no longer say safe while the page says careful.

**The card ledger says what the save can prove.** 224 collectible cards (202 main, 22 leaders) each
carry a source, owned / not owned / unknown, and one reviewed window: 15 Tier B community windows,
17 Tier A one-time sources, or a documented no-window reason. 200 cards are sourced and 24 are
explicit unknown-source rows, including the 16 starter-deck basics, because a deck list is not a
collection grant. Dijkstra's card is a one-time Baron source (opened by `cgnomansland` and
`cg_baron_discovered`, with the Baron's office as fallback), not a missable window. Filters are open
now, later, owned and unknown; a Tier B row shows its source and review date.

**Coverage tells a measured zero from an unmodelled pack.** Per-pack counts, and a pack with no
cards reads `not modelled` with a reason instead of a bare zero.

**PROGRESS covers the whole game.** 412 steps (403 quests plus 9 reviewed manual steps) in the
game's own five sections: Main 96, Secondary 183, Contracts 35, Treasure Hunts 87, Gwent 11. There
is no sixth section and no single completion percentage.

**The statuette turn-in names what is still missing.** The detail watch reads the save's facts and
says both, one or neither: "Both statuettes in hand - talk to Triss now", "You still need the soldier
statuette", or "Find both statuettes, then talk to Triss". The wording comes from `cutoffs.json`
facts, not a step id hardcoded in the code.

**Data generated from the game, not typed by hand.** 412 route steps from the game's own journals,
2,286 branch rows on 141 steps, 15 reviewed windows that carry their opening gate, and 17 one-time
rows with an open gate. The pipeline in `tools/` now reproduces every shipped data file byte for
byte (`py tools/regen.py --check` reports all eleven outputs matching).

## The 1.3.1 fix

1.3.0 treated an empty journal as every quest being `Not started`. With no save, `--detail
mq3012noblestatuette` returned `warn` and "Find both statuettes...", and `check_quest` shared that
path. `save_is_ready` now requires a found save whose last read succeeded. Without one,
`live_watch_for` returns no warning and `verdict_for` returns `info` ("Load a save to see this quest
in your game") with no details and no game-file claim. `detail_json` also clears the
`derived.watch` fallback, so the detail pane cannot paint a red statuette row on a clean profile.
The earliest real save still gets its "Find both" warning, because that save is loaded and the facts
are absent.

The post-release cleanup committed the statuette turn-in source (`data/cutoff_windows.json` and
`tools/review_cutoffs.py`) alongside the ledger it produces and re-recorded the pipeline hashes, so a
fresh checkout can reproduce this package's data. The zip was rebuilt for that one review input; the
executable is unchanged.

## Gate evidence

| gate | result |
|---|---|
| `cargo test --locked` | 57 passed, 0 failed |
| `py tools/regen.py --check` | all 11 outputs match the recorded hashes |
| clean `--view` | `top=[]`, `todo=[]`, `target=null`, `tradeoffs=[]` |
| clean `--detail mq3012noblestatuette` | `info` / "Load a save to see this quest in your game"; `derived.watch=[]`; 0 "Find both" |
| clean `--cards` | 224 cards, 0 owned / 0 not owned / 224 unknown |
| newest save `--view` | `top=2` (`card`, `missable`); `todo=65` |
| newest save `--detail` | `warn` / "Both statuettes in hand - talk to Triss now" |
| newest save `--cards` | 129 owned / 94 not owned / 1 unknown |
| median save `--view` | `top=3` (`failed`, `card`, `missable`); `todo=52` |
| median save `--detail` | `warn` / "You still need the soldier statuette" |
| median save `--cards` | 114 owned / 109 not owned / 1 unknown |
| earliest save `--view` | `top=[]`; `todo=2` |
| earliest save `--detail` | `warn` / "Find both statuettes, then talk to Triss" |
| earliest save `--cards` | 27 owned / 196 not owned / 1 unknown |
| `--dump` vs `--view` | top equal on all three saves |
| `py tools/cardwindows.py check` | 224 = 15 missable (15 Tier B) + 17 one-time + 192 no-window; 23 unknown-source rows |
| `py tools/test_cardwindows.py` | 13 tests, OK |
| `py tools/cards.py check` | 200 sourced / 24 unknown; newest save 129/94/1 |
| `py tools/contradictions.py` | 0 contradicted, 0 disputed |
| `package.ps1 -Bump patch` | built `dist/Witcher3MissablesTracker-1.3.1/` and `.zip`; packaged exe re-run |

The three real saves were copied into temporary profiles; the originals were never written. The
clean profile has an empty saves folder. The game was not launched for this release. The native
Tauri WebView was not driven by automation.

## Artifact

- `dist/Witcher3MissablesTracker-1.3.1/Witcher3MissablesTracker.exe`
  SHA-256 `175005d1e78a3eaa939e012ca54a5d612552a3219a5db29c7d1d0ab5682a33d5`
- `dist/Witcher3MissablesTracker-1.3.1.zip`
  SHA-256 `045c63d354aef601bca74a8fcbe5f6028df5a7c420e889ac2e9f723f7b621b74`
- Repo-root `Witcher3MissablesTracker.exe`
  SHA-256 `175005d1e78a3eaa939e012ca54a5d612552a3219a5db29c7d1d0ab5682a33d5`
- Zip entries: `22`; `testzip()` reports no damage.
- All 16 shipped `data/*.json` files in the dist folder are byte-identical to the checkout files
  that passed the gates.

## Still open

- The native Tauri WebView was not driven by automation.
- No corpus save has Dijkstra unowned after the Baron line, so the active/check/fallback states are
  Rust fixtures; the real saves cover owned and `not_yet`.
- The 24 explicit unknown-source cards and the 3 unknown route nodes remain visible data gaps; the
  app shows them as unknown rather than inventing a source.
