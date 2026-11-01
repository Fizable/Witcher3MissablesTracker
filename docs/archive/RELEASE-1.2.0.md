# Release 1.2.0 - cockpit UI

2026-10-29. This is the UI shape pass: one play loop, one reference drawer, and no separate run-plan
section. It does not change the route, outcome, matrix or card data. The denominator is still the
audited **412 route nodes = 403 quests + 9 manual_reviewed steps**; the mission prompt's 414/11 is
the historical 1.0.0 baseline.

## The screen

- **NOW** is a sticky band above the scrolling list. It contains only entries that can still change
  the outcome in this save: `DO THIS NOW`, `MISSABLE`, `CUTOFF PASSED - CHECK NOW`, `LOST IN THIS
  SAVE`, `CARD WINDOW OPEN`, and the card check/lost variants. When nothing is actionable the band
  disappears; it does not hold empty space.
- **UP NEXT** is the only long list. The tracked quest comes first, then the reviewed plan when
  guidance is on, then safe route steps. A plan step and a quest are one card, never two. The exact
  `SAY THIS` line appears only on the tracked goal step; future plan steps show a `GOAL`/`PLAN`
  marker and never the line early.
- **MORE** is one drawer with `CARDS`, `PROGRESS`, `COVERAGE` and `STATUS` tabs. It opens from the
  header, from the later-card-warning count, or from `PROGRESS` references. It closes on Escape,
  its close button, or a click on the backdrop.
- The separate `RUN PLAN` section is gone. The plan note (`5 ahead · 1 set · ready`) and plan issues
  live in the `UP NEXT` header. Completion counts and exclusions live in `MORE > STATUS`.
- Future plan cards are compact: title, goal marker, level and the one-line note, without the
  description and starting objectives that belong to the current/tracked quest.

## Card timing

Card warnings that are merely `ahead` are not in `NOW`. Gaunter O'Dimm and King Bran are the two
reviewed card deadlines in that state in this save; they are reachable from
`+ 2 later card warnings` and from `MORE > CARDS > LATER`. The `LATER` ledger filter has three rows
because it also contains Skellige Storm, a Tier A **one-time source** rather than a reviewed
deadline. The `NOW` count is deliberately labelled "later card warnings" so it does not claim to be
the ledger-filter count.

The card ledger still has all 224 rows, 15 reviewed Tier B community windows, 15 Tier A one-time
sources and 194 documented no-window rows. No window evidence, card state or ownership changed.

## Evidence from the packaged 1.2.0 exe

`dist/Witcher3MissablesTracker-1.2.0/Witcher3MissablesTracker.exe` was run from its own folder
against its own `data/`, using the real save. Fresh and guided app-data profiles were used for the
spoiler gate; the real profile was used for the completion numbers.

- Fresh view: `target: null`, `setup.needed: true`; no ending label or line in the payload.
- Guided view: four targets, `guidance: on`, states
  `settled`, `reachable`, `reachable`, `reachable`.
- Targets: 4, all `guided`; one preset.
- Outcomes: 4 groups, 11 outcomes, 4 selected, 0 conflicts.
- Plan: `ready`, `5 ahead · 1 set`; levels `5, 9, 20, 30, 36, 47, 49`.
  The two settled Baron steps (`q105evilspirit`, `q107swamps`) are present in the report but are not
  visible in `UP NEXT`. The five visible steps are `q110postbattle` (20), `q502avallach` (30),
  `q605finale` (36), `q704bfairyland` (47) and `q705ceremony` (49).
- `q110postbattle` carries `All right, Velen it is.` (locId 550164); the other three planned
  instructions are present in the plan but are not shown until their step is tracked.
- Cards: 224; 129 owned, 94 not owned, 1 unknown; 15 missable (15 Tier B, 0 Tier A), 15 one-time,
  194 no-window; 3 `ahead`, 1 `active`.
- Real-profile view: 412 route nodes, 143 done, 260 obtainable, 6 at risk, 3 excluded, 0 unknown,
  9 manual reviewed. Section headers `37/96 + 60/183 + 9/35 + 28/87 + 9/11` sum to **143/412**,
  matching the matrix line.

## Rendered UI evidence

The same `ui/` source that is embedded at build time was served against the dist payloads above at
480x820, 400x700 and 360x640. No console errors and no horizontal overflow at any width.

- `NOW` contained `MISSABLE` (statuettes) and `CARD WINDOW OPEN` (Iorveth); `King Bran` was absent.
  The later link read `+ 2 later card warnings`.
- `UP NEXT` order: `Ugly Baby` (tracked), `Blood on the Battlefield` L20, `Tedd Deireadh` L30,
  `Whatsoever a Man Soweth...` L36, `Beyond Hill and Dale...` L47; with `show all`, `Pomp and
  Strange Circumstance` L49 appears once. Each planned quest appeared exactly once.
- Simulating the tracked goal as `Blood on the Battlefield` produced exactly one `SAY THIS` block:
  `"All right, Velen it is."` and goal `Ciri lives: witcher ending · locId 550164`. No other card
  received a guidance block.
- `MORE > CARDS`: 224 rows; `LATER` showed 3 rows with `OPEN LATER · COMMUNITY WINDOW`,
  `ONE-TIME · TIER A`, `OPEN LATER · COMMUNITY WINDOW`.
- `MORE > PROGRESS`: 412 rows; five headers total 143/412, equal to the matrix line.
- `MORE > STATUS`: 412 route nodes, 143 done, 3 exclusions, 7 tradeoffs, card counts as above.
- The packaged native window launched from its own folder, reported the title
  `Witcher 3 · Missables Tracker`, and stayed responsive. The native WebView was not driven by
  automation; the rendered proof is the real UI source with the dist payloads.

## Package

- `dist/Witcher3MissablesTracker-1.2.0/` and `.zip` were built by `package.ps1 -Bump minor`, exit 0.
- Exe SHA-256: `cfb76c37dc9d639c4128695db859bb7a1ba25da708da5e94dbc2c48dc0ed961c`.
- The root `Witcher3MissablesTracker.exe`, the dist exe and the zip's exe entry all have that hash.
- All 16 shipped `data/*.json` files are byte-identical to the checkout files that passed the gates.
- Zip: 22 entries, `testzip()` reports no damage. Packaged README starts
  `# Witcher 3 Missables Tracker 1.2.0`.
- `dist/Witcher3MissablesTracker-1.1.0/` and its zip were not touched; they remain the historical
  1.1.0 package. The repo-root exe is now 1.2.0, matching the newest dist folder.

## Gates run fresh before packaging

| gate | result |
|---|---|
| `cargo test --locked` | 46 passed |
| `py tools/regen.py --check` | all 11 outputs match |
| `py tools/contradictions.py` | 5 claims, 0 contradicted; 5 prerequisites, 0 disputed |
| `py tools/endings.py check --release` | 4 targets, 4 guided, 0 not guided yet, 1 preset |
| `py tools/test_endings.py` | 24 passed |
| `py tools/cards.py check` | 224 = 202 + 22 leaders; 129 owned / 94 not / 1 unknown |
| `py tools/outcomecheck.py --release` | 4 groups, 11 outcomes, 4 guided, 0 warnings |
| `py tools/exclusivity.py --check` | 11 accepted edges; 44 cross-group and 2 cutoff candidates rejected |
| `py tools/test_outcomes.py` | 8 passed |
| `py tools/cardwindows.py check` | 15 B + 15 one-time + 194 no-window = 224; 7 unknown-source rows |
| `py tools/test_cardwindows.py` | 8 passed |
| `py tools/matrixcheck.py` | 412 = 403 + 9; 0 exclusive edges; 6 warnings with evidence |
| `py tools/test_matrix.py` | 8 passed |
| `py tools/statuscheck.py` | no regressions |
| `py tools/fuzz.py` | 60 damaged files, 0 unacceptable |

## Still open

- The mission-wide section 7 adversarial clearance (two consecutive full passes with no new P0/P1)
  is not done, and section 9's final report is not written. This note is not that clearance.
- The section 6 save matrix (early/mid/epilogue, failed quest, missing collection block, corrupted
  save, missed/passed card windows) has not been run against this package.
- The native Tauri WebView was not driven by automation; the packaged window launch was a liveness
  check.
- No card window is Tier A; all 15 reviewed windows are Tier B community evidence. Seven cards still
  have an explicit unknown-source row.
