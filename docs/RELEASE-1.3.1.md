# Witcher 3 Missables Tracker 1.3.1

Released: 2026-10-30
Previous package: `dist/Witcher3MissablesTracker-1.3.0/` (left untouched)

## What changed

1.3.1 fixes a no-save state leak found in the 1.3.0 post-release audit.

- **No save, no live verdict.** With an empty saves folder, or a newest save that could not be
  read, the empty journal was treated as every quest being `Not started`. `--detail
  mq3012noblestatuette` returned `warn` and "Find both statuettes..." even though no save had been
  read; `check_quest` shared the same path. `save_is_ready` now requires a found save whose last
  read succeeded. Without one, `live_watch_for` returns no warning and `verdict_for` returns
  `info`: "Load a save to see this quest in your game", with no details and no `from_game_files`
  claim.
- **The detail pane, not just the verdict.** `renderDetail` falls back to `derived.watch` when the
  NOW band has no item for the step, so the static statuette row would still render as a red
  warning on a clean profile. `detail_json` now clears that watch array when no usable save is
  loaded; the rest of the game-file evidence remains. The clean detail payload has no "Find both"
  text and no live watch.
- **Test.** `top_tests::a_missing_or_unreadable_save_is_not_a_live_state` proves a missing path or a
  failed read is not ready, and that the no-save answer has no details or game-file claim. The
  packaged clean profile is checked for `derived.watch == []` and zero "Find both" occurrences.

No data, route, card or UI layout changes. The three-save matrix is unchanged; the earliest save
still gets its "Find both statuettes" warning because that save is loaded and the facts are absent.

## Gate evidence

| gate | result |
|---|---|
| `cargo test --locked` | 57 passed, 0 failed |
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
| `package.ps1 -Bump patch` | built `dist/Witcher3MissablesTracker-1.3.1/` and `.zip`; packaged exe re-run |

The three real saves were copied into temporary profiles; the originals were never written. The
clean profile has an empty saves folder. The game was not launched for this release. The native
Tauri WebView was not driven by automation.

## Artifact

- `dist/Witcher3MissablesTracker-1.3.1/Witcher3MissablesTracker.exe`
  SHA-256 `175005d1e78a3eaa939e012ca54a5d612552a3219a5db29c7d1d0ab5682a33d5`
- `dist/Witcher3MissablesTracker-1.3.1.zip`
  SHA-256 `7db068f31a45e17a765ae837debbbf2375725a804a5f5b772cf540725fd4ba51`
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
