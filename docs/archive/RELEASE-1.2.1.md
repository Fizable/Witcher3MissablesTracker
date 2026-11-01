# Witcher 3 Missables Tracker 1.2.1

Released: 2026-10-29
Previous package: `dist/Witcher3MissablesTracker-1.2.0/` (left untouched)

## What changed

1.2.1 closes the finish-contract proof work and fixes the one data-reading defect that work found.

- **Quest status fallback.** A route file can name one journal objective (`quest#objective`). When
  a save carries the quest's own entry but not that objective, the tracker now uses the quest's
  journal status. This fixes `cgnovigrad`, which was `Done` in the save but displayed `Not started`,
  and which kept a proven passed one-time card window at `OPEN LATER`. A `Failed` objective still
  wins over a completed quest. Regression test:
  `model::tests::a_finished_quest_answers_for_an_objective_the_save_does_not_carry`.
- **Section 6 save matrix** run against the packaged exe: early, mid, epilogue, failed quest,
  missing collection block, corrupted save, missed community card, passed one-time card, all four
  goals true and all four impossible. **539/539 checks**.
- **Section 7 adversarial clearance**: two passes; 20 quest + 20 card claims re-derived from REDkit
  and the string database per pass, plus 25 real saves through the packaged exe. **0 unsupported
  lost claims; 0 open P0/P1**.
- **Section 9 final report**: [FINAL-REPORT.md](FINAL-REPORT.md), measured counts and named unknowns.

No shipped quest, card or warning was removed, and no threshold was relaxed.

## Data / counts

- 412 route nodes = 403 quests + 9 `manual_reviewed` steps (the audited denominator; the prompt's
  prose still says 414 / 11 at lines 71, 134, 197, 202, 370 and 395).
- 224 cards = 202 collectible main + 22 leaders; 216 sourced, 8 explicit `unknown source`.
- 15 Tier B missable windows, 15 Tier A one-time sources, 194 documented no-window rows.
- 4 outcome groups, 11 outcomes, 4 targets, 4 guided.
- 11 accepted exclusivity edges.

## Gates run fresh

| gate | result |
|---|---|
| `cargo test --locked` | 47 passed |
| `py tools/regen.py --check` | all 11 outputs match |
| `py tools/contradictions.py` | 5 claims, 0 contradicted; 5 prerequisites, 0 disputed |
| `py tools/endings.py check --release` | 4 targets, 4 guided, 0 not guided |
| `py tools/test_endings.py` | 24 passed |
| `py tools/cards.py check` | 224 = 202 + 22; 216 sourced / 8 unknown; 15 / 15 / 194 |
| `py tools/outcomecheck.py --release` | 4 groups, 11 outcomes, 4 guided, 0 warnings |
| `py tools/exclusivity.py --check` | 11 accepted, 44 + 2 rejected |
| `py tools/test_outcomes.py` | 8 passed |
| `py tools/cardwindows.py check` | 224 = 15 B + 15 one-time + 194 no-window |
| `py tools/test_cardwindows.py` | 8 passed |
| `py tools/matrixcheck.py` | 412 = 403 + 9; 6 warnings with evidence |
| `py tools/test_matrix.py` | 8 passed |
| `py tools/statuscheck.py` | no regression |
| `py tools/fuzz.py` | 60 damaged files, 0 unacceptable |
| packaged `--view`/`--plan`/`--outcomes`/`--targets`/`--cards` | real save, all-good, all-bad, matrix cases |
| `target/proof/matrix.py` | 539/539 |
| `target/proof/adversarial.py` seed 2 | 20 + 20 claims, 0 unacceptable |
| `target/proof/warning_sample.py` | 25 saves, 0 unsupported lost |

## Artifact

- `dist/Witcher3MissablesTracker-1.2.1/Witcher3MissablesTracker.exe`
  SHA-256 `a486c246692e9c594d3a7f7e3e33e2b33e84566d1978e4040444b819ea63fe65`
- `dist/Witcher3MissablesTracker-1.2.1.zip`
  SHA-256 `33aa88b8929d1b26997f00ebe5ae4bf61792034baf3089c4b4f76cbeb4850124`
- The repo-root `Witcher3MissablesTracker.exe` is the same build and hash.

## Still open / accepted unknowns

- No Tier A card-level deadline is proved; all 15 missable windows are visibly labelled Tier B
  community evidence with a source and review date.
- 8 cards remain explicit `unknown source`; 3 route nodes remain `unknown`.
- The five stale entries in `tools/save_index.json` are a P2 cache cleanup, not an app claim.
- Native Tauri WebView automation was not available; the UI was rendered from the shipped `ui/`
  against packaged payloads at 1280x900 (no console errors, no horizontal overflow).
