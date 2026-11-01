# Witcher 3 Missables Tracker 1.2.2

Released: 2026-10-29
Previous package: `dist/Witcher3MissablesTracker-1.2.1/` (left untouched)

## What changed

1.2.2 is the cockpit follow-up to 1.2.1:

- **UP NEXT is actionable-only.** It shows the tracked quest, quests whose save frontier is
  `in_log`, and the one plan step that is current. Unlocked route steps that are not in the log
  stay in PROGRESS instead of filling the play queue.
- **Future plan steps sit under one collapsed PLAN AHEAD line.** The line names the goal count and
  level span; future goal cards no longer appear beside the quest you are actually on.
- **Plan guidance follows the tracked step.** `SAY THIS` appears only on the tracked goal step; a
  future step keeps its goal marker and never leaks its scene line early.
- **Non-tracked Active quests are labelled correctly.** They read `in your quest log`, not
  `not in your log yet`.

The route, outcomes, matrix and card data are unchanged: 412 route nodes (403 quests + 9
`manual_reviewed`), 224 cards (202 collectible main + 22 leaders), 4 outcome groups / 11 outcomes.

## Gate evidence

Run on a hardlinked snapshot of the same 518 saves, so the running game could not rotate a file
between the directory scan and the read. All 15 named gates exited 0:

| gate | result |
|---|---|
| `cargo test --locked` | passed |
| `py tools/regen.py --check` | all 11 outputs match |
| `py tools/contradictions.py` | 5 claims, 0 contradicted; 5 prerequisites, 0 disputed |
| `py tools/endings.py check --release` | 4 targets, 4 guided, 0 not guided yet, 1 preset |
| `py tools/test_endings.py` | OK |
| `py tools/cards.py check` | 224 = 202 + 22; 216 sourced / 8 unknown; 129 owned / 94 not / 1 unknown |
| `py tools/outcomecheck.py --release` | 4 groups, 11 outcomes, 4 guided, 0 warnings |
| `py tools/exclusivity.py --check` | 11 accepted, 44 cross-group and 2 cutoff candidates rejected |
| `py tools/test_outcomes.py` | OK |
| `py tools/cardwindows.py check` | 224 = 15 Tier B + 15 one-time + 194 no-window |
| `py tools/test_cardwindows.py` | OK |
| `py tools/matrixcheck.py` | 412 = 403 + 9; 6 warnings with evidence |
| `py tools/test_matrix.py` | OK |
| `py tools/statuscheck.py` | 518 saves; no regressions |
| `py tools/fuzz.py` | 60 damaged files, 0 unacceptable |

Two earlier full-suite attempts hit `FileNotFoundError` in `statuscheck.py` because the live game
deleted an autosave between the directory listing and the read. The same command passed on the
stable snapshot and on an immediate live retry; no checker logic was weakened.

## Packaged-exe evidence

The packaged exe was run from `dist/Witcher3MissablesTracker-1.2.2/` against the real save
`CheckPoint_10083f_7ea4f000_26ac204.sav` (20 seconds old at read time):

- `--view`: 412 route nodes, 198 route candidates, tracked `Ugly Baby`, guidance on with four
  selected targets (`settled`, `reachable`, `reachable`, `reachable`), NOW tags `MISSABLE`,
  `CARD WINDOW OPEN`, two `MISSABLE CARD` rows.
- `--plan` for all four targets: `state: ready`, 7 steps, `5 ahead · 1 set`, levels
  `5, 9, 20, 30, 36, 47, 49` in that order. The five ahead steps are
  `q110postbattle`, `q502avallach`, `q605finale`, `q704bfairyland`, `q705ceremony`.
- `--outcomes`: 4 groups, 11 outcomes, 4 selected outcomes, 0 conflicts.
- `--cards`: 224 total, 129 owned / 94 not owned / 1 unknown; 15 Tier B, 15 one-time,
  194 no-window.

The packaged exe's embedded asset bundle was decompressed and hashed: `index.html`, `app.js`,
`api.js` and `style.css` are byte-identical to the tested `ui/` sources. The native window was not
driven by automation; the packaged headless surface and the embedded assets are the evidence here.

## Artifact

- `dist/Witcher3MissablesTracker-1.2.2/Witcher3MissablesTracker.exe`
  SHA-256 `f488847d2a78b6786ac788ca5ab15b7b884e5e7379d9925c6585bb8a899542ac`
- `dist/Witcher3MissablesTracker-1.2.2.zip`
  SHA-256 `e4ff01e66713ffdf7660f8edc0064cdc644ca9245d004f823d69102aa2018465`
- Repo-root `Witcher3MissablesTracker.exe` has the same SHA-256 as the dist exe.
- Zip: 22 entries, `testzip()` reports no damage. All 16 shipped `data/*.json` files are
  byte-identical to the checkout files that passed the gates.
- `package.ps1` built the dist folder and zip; its final root copy was blocked while the old 1.2.1
  process was still running, then completed after that process exited. The final root and dist
  binaries match.

## Still open

- The native Tauri WebView was not driven by automation.
- The 8 cards with explicit unknown source and the 3 unknown route nodes remain the accepted
  data gaps from 1.2.1; this release does not change them.
