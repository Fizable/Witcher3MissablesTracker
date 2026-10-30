# Witcher 3 Missables Tracker 1.3.0

Released: 2026-10-30
Previous package: `dist/Witcher3MissablesTracker-1.2.2/` (left untouched)

## What changed

1.3.0 completes the card-source audit and the two availability cases behind it.

- **A deck list is no longer treated as ownership.** `starter_deck` split into `deck_definition`
  (weak evidence) and `collection_grant` (native `OnGwintSetupNewgame` /
  `UnlockSkelligeGwentDeck`). The 16 basic Northern Kingdoms cards whose only evidence was the
  `north` deck list now carry an explicit `unknown source` row; the save still decides
  owned/not-owned. 200 cards are sourced, 24 are explicit unknown.
- **Dijkstra is a reviewed one-time source, not `none`.** `cg100_no_mans_land.w2phase` block 551
  grants `gwint_card_dijkstra`; the window opens at `cgnomansland` when `cg_baron_discovered` is
  set, and records the Baron's office as the fallback. It is not a Tier B missable window and does
  not enter NOW; the CARDS ledger shows the exact source and fallback.
- **Every reviewed window names its open gate.** `opens` is required for `missable` and `one_time`
  rows; Thaler and Lambert carry their earlier-source notes. A `fallback` turns a closed one-time
  source into `check`, never a hard lost claim.
- **The statuette turn-in reads the save's facts.** `mq3012_noble_statuette` and
  `mq3012_soldier_statuette` select "both", "one missing" or "neither" wording, while
  `q210preparations` remains the outer deadline. Newest save: both; median: soldier missing;
  earliest: neither.
- **The 224-card audit is a checker.** `cardwindows.py check` now also rejects a `none` row that
  hides a one-time source, a window without `opens`, a gate on a fact that is not in the game's
  fact index, and a no-window row resting on a deck list alone. 13 mutation tests.

Counts: 224 cards = 15 missable (15 Tier B) + 17 one-time + 192 no-window; 200 sourced / 24
explicit unknown; Tier A 186, B 15, C 23. Route and outcomes are unchanged: 412 nodes
(403 + 9 `manual_reviewed`), 4 outcome groups / 11 outcomes.

## Gate evidence

| gate | result |
|---|---|
| `cargo test --locked` | 56 passed, 0 failed |
| `py tools/cardwindows.py check` | 224 = 15 missable (15 Tier B) + 17 one-time + 192 no-window; 23 unknown-source rows |
| `py tools/test_cardwindows.py` | 13 tests, OK |
| `py tools/cards.py check` | 224 = 202 + 22; 200 sourced / 24 unknown; newest save 129 owned / 94 not / 1 unknown |
| `py tools/cardwindows.py build` | regenerated `gwent_cards.json` and `card_windows.json`, deterministic |
| four isolated profiles | clean `top == []`; earliest `top == []`; newest `CARD WINDOW OPEN` + `MISSABLE`; median failed quest + card window + statuettes |
| `--dump` vs `--view` | top equal on all three saves |
| Dijkstra | owned on newest and median; `not_yet` on earliest; active/check/fallback in Rust fixtures |
| statuette turn-in | both (newest), soldier missing (median), neither (earliest) |
| `package.ps1 -Bump minor` | built `dist/Witcher3MissablesTracker-1.3.0/` and `.zip`; packaged exe re-run headless |

The packaged `--view` matched the tested payload in every field except `save.age_secs`, which is
read from the clock at run time; the NOW band, `--cards` and the statuette verdict matched.

The three real saves were copied into a temporary `APPDATA` profile; the originals were never
written. The native Tauri WebView was not driven by automation, as in earlier releases.

## Artifact

- `dist/Witcher3MissablesTracker-1.3.0/Witcher3MissablesTracker.exe`
  SHA-256 `6a11c37193b924b767840e139518252a8c12eb7a4f24c7f99690b805a794ea86`
- `dist/Witcher3MissablesTracker-1.3.0.zip`
  SHA-256 `2e5d50259a9eab87cf3bc829b907c520befa6df7958a71769cfe219574f6fd7a`
- Repo-root `Witcher3MissablesTracker.exe`
  SHA-256 `6a11c37193b924b767840e139518252a8c12eb7a4f24c7f99690b805a794ea86`
- Zip entries: `22`; `testzip()` reports no damage.
- All shipped `data/*.json` files in the dist folder are byte-identical to the checkout files that
  passed the gates.

## Still open

- The native Tauri WebView was not driven by automation.
- No corpus save has Dijkstra unowned after the Baron line, so the active/check/fallback states
  are Rust fixtures; the real saves cover owned and `not_yet`.
- The 24 explicit unknown-source cards and the 3 unknown route nodes remain visible data gaps; the
  app shows them as unknown rather than inventing a source.
