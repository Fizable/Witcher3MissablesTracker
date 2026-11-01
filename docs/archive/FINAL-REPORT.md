# Final report - Witcher 3 Missables Tracker 1.2.1

Status: **COMPLETE**
Date: 2026-10-29
Package: `dist/Witcher3MissablesTracker-1.2.1/Witcher3MissablesTracker.exe`
Chosen run: `ciri_witcher + baron_wife_cured + olgierd_saved + bw_both_sisters`
Compatibility: **proven** for the four chosen outcomes. They are one outcome in each of four
one-of groups; no `data/exclusive.json` edge joins two of them. The 11 accepted edges are proved
between their listed alternatives.

## Measured counts

| item | measured | evidence |
|---|---|---|
| route | **412** nodes = **403** quests + **9** manual_reviewed | `matrixcheck.py`; `data/route.json` |
| baseline manual rows | 11 -> **2 replaced + 9 kept and labelled** | `docs/MANUAL-STEPS-AUDIT.md`; `route_overrides.json` |
| quests | done **142**, obtainable **261**, at risk **6**, lost **0**, excluded **0**, unknown **3**; max achievable **409** | real-save `--view`, matrix line |
| cards | **224** = 202 collectible main + 22 leaders; owned **129**, not owned **94**, unknown **1** | real-save `--cards` |
| card windows | **15 Tier B missable** (0 Tier A), **15 one-time Tier A**, **194 documented no-window**; 216 sourced / 8 explicit unknown source | `cardwindows.py check` |
| card tiers | **202 Tier A**, **15 Tier B**, **7 Tier C** | `--cards.missable_windows` |
| outcomes | **4 groups, 11 outcomes, 4 targets, 4 guided, 0 not guided yet** | `outcomecheck.py --release` |
| exclusivity | **11 accepted outcome edges**; 44 cross-group pairs rejected; 2 cutoff candidates rejected | `exclusivity.py --check` |
| coverage | 196 base + 28 Blood and Wine + 0 Hearts of Stone (expected) + 22 leaders | `docs/CARD-WINDOWS.md`; `cardwindows.py check` |
| card warnings on this save | 1 active Tier B window, 3 ahead, 0 lost/check; one-time rows are not deadline warnings | `--cards`, real save |
| quest warnings on this save | 6 at-risk route nodes, 0 lost | `--view`, real save |

No completion percentage is printed in the app or in this report.

## Section 6 save matrix

The packaged 1.2.1 exe was driven with its own `data/` over nine saves:

| case | proof |
|---|---|
| early | full 412-node view; no target/line leak |
| mid (real) | 4 targets: 1 settled, 3 reachable; 412-node matrix |
| epilogue | full view; failed rows and card state read |
| failed quest | failed journal row appears as `FAILED IN YOUR QUEST LOG` |
| missing card collection | `block_ok: false`; **224 unknown**, 0 owned |
| corrupted save | error reported on the save object; 412 rows all Not started; no crash |
| missed community card | Iorveth shows `PASSED - CHECK · COMMUNITY WINDOW`, never `LOST` |
| passed one-time card | Cirilla shows `ONE-TIME · PASSED · TIER A` after the quest's own journal is Done |
| all four goals true | all four targets `settled`; every opposing outcome `impossible` |
| all four goals impossible | all four targets `impossible`; the save's taken alternatives `met` |

The harness is `target/proof/matrix.py`; its final run is **539/539 checks passed**
(`target/proof/out/matrix-1.2.1.txt`). The one defect it found was fixed before the final run:

- `cgnovigrad` was `Done` in the save's journal, but the route file names the narrower objective
  `cgnovigrad#Win unique card from Dijkstra`, which the save does not carry. `node_status` looked
  only for the exact key and reported `Not started`; a proven passed one-time card window stayed
  `OPEN LATER`. The lookup now falls back to the quest's own journal status when the exact objective
  is absent, while a `Failed` objective still wins. Regression test:
  `model::tests::a_finished_quest_answers_for_an_objective_the_save_does_not_carry`.
  The 1.2.0/1.2.1 diff on the same save changes **only** `cgnovigrad` (`Not started` -> `Done`),
  and the card row `card_ciri` from `ONE-TIME · TIER A` (ahead) to `ONE-TIME · PASSED · TIER A`;
  no other step status or target verdict changes.

Both sides of every target were also checked through `--targets` and `--outcomes` on the real save
and the synthetic all-good / all-bad saves, and `--plan` was checked on the early and real saves.

### Conflict proof

The four shipped targets are one per exclusive group, so no shipped pair can conflict. The conflict
path was therefore proved with a **proof-only fifth target** in a copy of the data under
`target/proof/conflict` (not shipped): selecting `ciri_witcher` and `ciri_empress` returns
`state: conflict`, **0 steps**, an `outcome_group` card, and the reviewed `exclusive` edge. The
rendered UI with the same payload shows two `CONFLICT` cards and `0 ahead · 0 set · conflict`.
This is a fixture proof of the code path; the shipped target set is deliberately conflict-free.

## Section 7 adversarial clearance

Two consecutive passes were run on the packaged build and on the data it ships.

| pass | file claims | save corpus | result |
|---|---|---|---|
| 1 | 20 quest + 20 card claims re-derived from REDkit/scene/journal/string database | 25 real saves through the packaged exe | found the `cgnovigrad` status/late-card defect above; fixed, regression test added |
| 2 | fresh 20 quest + 20 card claims (different seed) | same 25-save sample, 0 unsupported lost claims | **0 new P0/P1** |

Pass 1 evidence: `target/proof/out/adversarial-pass1.txt`. Pass 2:
`target/proof/out/adversarial-pass2.txt`. Save sample:
`target/proof/out/warning-sample.txt` (**25/25 loaded, 17 lost classifications, 17 failed journal
rows, 0 unsupported**).

The corpus check (`contradictions.py`) reports **5 derived claims, 0 contradicted; 5 route
prerequisites, 0 disputed** over the readable saves.

## Packaged exe checks

- `--view` fresh: `target` is absent; no target label, choice line or instruction; no `%`; setup not
  requested twice.
- `--view` guided: exactly the four chosen target ids; no unselected instruction line.
- `--plan`: level-then-route **5, 9, 20, 30, 36, 47, 49**; settled `q105`/`q107` steps have no
  instruction and are not rendered as plan cards.
- `--outcomes`: 4 groups / 11 outcomes; 0 conflicts for the chosen four.
- `--targets`: all four guided; real save = 1 settled + 3 reachable; all-good = 4 settled;
  all-bad = 4 impossible.
- `--cards`: 224 rows; every row has a window kind; every no-window row names sources checked;
  every Tier B row has a source, URL and review date.
- Rendered UI at 1280×900: no console errors, no horizontal overflow, no `%`; PROGRESS has 412
  inspectable rows and section headers **37/96 + 60/183 + 9/35 + 28/87 + 8/11 = 142/412**.
- Tier B source/date visible in the card row; passed one-time row shows `ONE-TIME · PASSED`.
- Packaged `data/` matches the checkout for all 16 shipped JSON files (sha256).

## Gates (fresh, 1.2.1 tree)

| gate | result |
|---|---|
| `cargo test --locked` | **47 passed**, 0 failed |
| `py tools/regen.py --check` | all **11** outputs match |
| `py tools/contradictions.py` | 5 claims, **0 contradicted**; 5 prereqs, **0 disputed** |
| `py tools/endings.py check --release` | 4 targets, **4 guided**, 0 not guided |
| `py tools/test_endings.py` | 24 tests, **OK** |
| `py tools/cards.py check` | 224 = 202 + 22; 216 sourced / 8 unknown; 15 missable / 15 one-time / 194 no-window |
| `py tools/outcomecheck.py --release` | 4 groups, 11 outcomes, 4 guided, **0 warnings** |
| `py tools/exclusivity.py --check` | **11** accepted, 44 cross-group + 2 cutoff rejected |
| `py tools/test_outcomes.py` | 8 tests, **OK** |
| `py tools/cardwindows.py check` | 224 = 15 B + 15 one-time + 194 no-window |
| `py tools/test_cardwindows.py` | 8 tests, **OK** |
| `py tools/matrixcheck.py` | 412 = 403 + 9; 0 exclusive edges among chosen; 6 warnings with evidence |
| `py tools/test_matrix.py` | 8 tests, **OK** |
| `py tools/statuscheck.py` | no regression (exit 0) |
| `py tools/fuzz.py` | 60 damaged files, **0** unacceptable |
| `target/proof/matrix.py` (1.2.1) | **539/539** |
| `target/proof/adversarial.py` pass 2 | 20 + 20 claims, **0 unacceptable** |
| `target/proof/warning_sample.py` | 25 saves, **0 unsupported lost** |

Machine-readable gate rows: `target/proof/out/gates.json`.

## Artifact

- Exe: `dist/Witcher3MissablesTracker-1.2.1/Witcher3MissablesTracker.exe`
  SHA-256 `a486c246692e9c594d3a7f7e3e33e2b33e84566d1978e4040444b819ea63fe65`
- Zip: `dist/Witcher3MissablesTracker-1.2.1.zip`
  SHA-256 `33aa88b8929d1b26997f00ebe5ae4bf61792034baf3089c4b4f76cbeb4850124`
- Repo-root exe has the same SHA-256, so the two visible 1.2.1 binaries are one build.
- The 1.2.0 folder and zip were not touched; they remain the previous release.

## Remaining unknowns / exclusions

- **No Tier A card-level deadline is proved.** All 15 missable card windows are Tier B community
  evidence, visibly labelled, each with a named source, URL and review date. The other 209 rows are
  15 Tier A one-time sources and 194 documented no-window rows (187 Tier A, 7 Tier C).
- **8 cards have no concrete source**, including Iorveth (which has a Tier B window). They are shown
  as `unknown source`, never as inferred ownership.
- **3 route unknowns** remain in the matrix; their names and reasons are in PROGRESS.
- **Denominator live decision:** the audited data uses **412 / 9**; the mission prompt's prose still
  says **414 / 11** at lines 71, 134, 197, 202, 370 and 395. The code, data, checkers and this report
  use 412 / 9. Recommended resolution: amend those six lines to "412 route nodes = 403 quests + 9
  manual_reviewed (the other 2 of the 11 baseline rows were replaced by file-derived steps)".
- Five save files still indexed in `tools/save_index.json` no longer exist in the saves folder.
  They are a stale cache, not a data claim; `contradictions.py` skips them and exits 0. Pruning
  that cache is a P2 cleanup.
- Native Tauri WebView automation is not available in this environment; the rendered-UI checks ran
  the shipped `ui/` against payloads from the packaged exe. The packaged window itself was launched
  and read through `--view`/`--cards`, not clicked by a UI driver.

## Not tested

- Full 518-save UI replay (25 saves were sampled; the full corpus was checked by
  `contradictions.py` for its five claims and prerequisites).
- A real player save taken through every one of the four terminal outcomes; those sides were proved
  with synthetic saves built from real saves, listed above.
