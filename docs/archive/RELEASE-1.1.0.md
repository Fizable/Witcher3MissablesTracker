# Release 1.1.0 - UI, warnings and package

2026-10-29. This is the section 4.5 release note: the UI/warning pass and the first package that
contains the 4.2 outcome planner, the 4.3 quest matrix and the 4.4 card windows. It is not the
section 9 finish report; the mission-wide adversarial clearance is still open.

## Denominator and version

- Shipped version: **1.1.0**.
- Route denominator: **412 nodes = 403 quests + 9 `manual_reviewed` steps**. The 1.0.0 baseline was
  414 nodes (403 quests + 11 manual); the two removed rows were exact duplicates of `q108eve` and
  `q111imlerith`, recorded in [MANUAL-STEPS-AUDIT.md](MANUAL-STEPS-AUDIT.md). The mission prompt's
  414 is the historical baseline; the audited 412 is what the payloads, matrix checker and this
  release use.

## What changed in 4.5

- A warning opened from **AT RISK NOW** now keeps the same tag, headline and action on the quest
  page. The statuette warning reads `MISSABLE` in both places, not `WATCH OUT` on the detail page.
- Every `missable` and `one_time` card row has its own collapsed **Technical details**: tier,
  closing step, event, mechanism, community source URL and review date, evidence entries, and the
  save note.
- The quest detail **Technical details** block now names the closing step, mechanism, evidence tier,
  source files and caveats. A card warning opened from the top list also names its card window and
  evidence there.
- `package.ps1` now ships `card_windows.json` (the static 224-row evidence report) and
  `card_window_review.json` (its reviewed input) beside the runtime card index.
- The packaged README describes the 15 reviewed Tier B card windows and no longer says card-level
  windows are unmodelled.

## Rendered UI evidence

The real UI was served against payloads produced by the **dist** exe, not the checkout data. The
native Tauri WebView was not automated; this is the rendered browser surface with the same
`ui/` source that is embedded at build time.

- Fresh app-data profile: `RUN` reads `SPOILER-FREE`, the setup card is visible, and the DOM contains
  no target label or choice line. `Matrix: 412 route nodes ... 9 manual reviewed (2 replaced)`.
- Goal picker: 4 target rows; outcome matrix: 4 groups, 11 rows. The `Recommended endings` preset
  selects all 4; applying it makes `RUN` show all four goals (`settled`, `reachable`, `reachable`,
  `reachable`).
- Run plan: visible after opt-in, `5 ahead · 1 set · ready`; level order is
  `L20 -> L30 -> L36 -> L47 -> L49` (`Blood on the Battlefield`, `Tedd Deireadh`, `Whatsoever a Man
  Soweth...`, `Beyond Hill and Dale...`, `Pomp and Strange Circumstance`). The two settled Baron
  steps are dropped from the visible route, as specified.
- Cards: 224 rows; 15 `COMMUNITY WINDOW` rows; all 15 show a source and review date; 3 are open/at
  risk. All 15 have collapsed technical details. Gaunter O'Dimm's details read:
  `Tier B - community`, closing step `Open Sesame! (q603bank)`, event `Open Sesame ends`, mechanism,
  source `Gwent Checklist - All 15 Missable Gwent Cards` with URL and `reviewed 2026-10-29`.
- Statuette warning detail: tag `MISSABLE`; technical details name
  `Closing step: the end of Final Preparations / Battle Preparations`,
  `Mechanism: journal Failure block`, the evidence tier and the three game files.
- Iorveth/card warning detail: tag `CARD WINDOW OPEN`; technical details name the `Shock Therapy`
  closing step and the reviewed card mechanism.
- No console errors and no horizontal overflow in the tested 646 px viewport.

## Package evidence

- `dist/Witcher3MissablesTracker-1.1.0/Witcher3MissablesTracker.exe`
- `dist/Witcher3MissablesTracker-1.1.0.zip`
- SHA-256 of the exe: `3a013a33468c5b36b27f6c762897fa2a29ce7ff1ea946c528f84680132a6c1b6`
- The root `Witcher3MissablesTracker.exe` has the same SHA-256; the zip's exe entry has the same
  SHA-256. The zip has 22 entries and `testzip()` reports no damage.
- All 16 shipped `data/*.json` files are byte-identical to the checkout files that passed the gates.
- The packaged README starts `# Witcher 3 Missables Tracker 1.1.0`.

Commands run from `dist/Witcher3MissablesTracker-1.1.0` against its own `data/`:

- `--view` (fresh app data): `target: null`, `setup.needed: true`, matrix 412 / 403 / 9.
- `--view` (guided): all four target ids, `guidance: on`.
- `--targets`: 4 targets, all `guided`.
- `--outcomes`: 4 groups, 11 outcomes, 4 selected, 0 conflicts.
- `--plan`: 7 returned steps, 2 settled + 5 ahead; levels
  `5, 9, 20, 30, 36, 47, 49`.
- `--cards`: 224 total; 129 owned, 94 not owned, 1 unknown; 15 missable (15 Tier B, 0 Tier A);
  15 one-time, 194 no-window.
- `--detail mq3012noblestatuette`: watch entry closes at the end of Final Preparations with
  `journal_failure`.
- `--detail mq2039vowofsilence`: the Iorveth card warning is present on the Shock Therapy page.
- `--detail q110postbattle`: `All right, Velen it is.` (locId 550164, Ciri).
- `--detail q605finale`: `[Help Olgierd.]` (locId 1104139, Olgierd).
- `--detail q704bfairyland`: `I'll pay you for the ribbon.` (locId 1154229, both sisters).
- `--detail q705ceremony`: `You were children then, both.` (locId 1191986, both sisters).
- `--detail q502avallach`: no dialogue line; the phase fact is the confirmation step, as the UI says.

## Gates, run fresh before packaging

| gate | result |
|---|---|
| `py tools/regen.py --check` | all 11 outputs match |
| `py tools/contradictions.py` | 5 claims, 0 contradicted; 5 prerequisites, 0 disputed |
| `py tools/endings.py check --release` | 4 targets, 4 guided, 0 not guided |
| `py tools/test_endings.py` | 24 passed |
| `py tools/outcomecheck.py --release` | 4 groups, 11 outcomes, 11 edges, 0 warnings |
| `py tools/exclusivity.py --check` | 11 accepted edges; 44 cross-group and 2 cutoff candidates rejected |
| `py tools/test_outcomes.py` | 8 passed |
| `py tools/cardwindows.py check` | 224 = 15 B + 15 one-time + 194 no-window; 7 unknown-source rows |
| `py tools/test_cardwindows.py` | 8 passed |
| `py tools/cards.py check` | 224 = 202 + 22 leaders; 129 owned / 94 not / 1 unknown |
| `py tools/matrixcheck.py` | 412 = 403 quest + 9 manual; 0 exclusive edges; 6 warnings with evidence |
| `py tools/test_matrix.py` | 8 passed |
| `py tools/statuscheck.py` | no regressions |
| `py tools/fuzz.py` | 60 damaged files, 0 unacceptable |
| `cargo test --locked` | 46 passed |

`package.ps1 -Bump minor` exited 0; `cargo build --release` finished in 1m25s.

## Still open beyond 4.5

- The mission-wide section 7 adversarial loop is not cleared: it requires two consecutive full
  passes with no new P0/P1. This release note is not that clearance.
- The native Tauri window was not driven by automation; the rendered proof used the real UI source
  with the dist payloads. The packaged exe's GUI was not clicked through.
- No card window is Tier A; all 15 reviewed windows are Tier B community evidence. Seven cards still
  have an explicit `unknown source` row (Iorveth has the reviewed Shock Therapy window and is not one
  of the seven no-window rows).
- The section 6 save matrix (early/mid/epilogue, failed quest, missing collection block, corrupted
  save, missed and passed card windows) has not been run against this package.
