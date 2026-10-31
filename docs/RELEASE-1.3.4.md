# Witcher 3 Missables Tracker 1.3.4

Released: 2026-10-31
Previous package: `dist/Witcher3MissablesTracker-1.3.3/` (left untouched)

1.3.3's package predated the band and surface work in this tree. 1.3.4 is the first package built
from that work: the NOW band and UP NEXT are back on the main surface, the choice warning is a band
row again, the no-save watch leak and the UI's second queue filter are gone, and search returns the
verdict it always had in the payload. This release is the verification record for those changes.

## What changed

- **The play surface is restored.** `UP NEXT` and `PLAN AHEAD` are below the band on the main
  surface, not inside `MORE`. `ENDING CHOICE AHEAD` is a NOW item again for an Active ending-relevant
  quest; the row names the quest and never the choice text or ending. Settled losses and passed
  cutoffs stay on `MORE > STATUS` and the quest page.
- **One save gate for every watch.** `live_watch` returns no row unless a save is usable, and both
  `view` and `detail` take their watch from it. On a clean profile the statuette steps no longer
  report a live `open` watch, and the matrix reports `at_risk: 0` instead of claiming two quests are
  at risk without a save.
- **The backend owns the queue.** The UI displays `view.todo` in the backend's order and no longer
  re-derives which plan steps are current. The next plan step (`q110postbattle` with a goal selected)
  now reaches UP NEXT.
- **Search shows its answer.** The detail page renders `detail.verdict` under `CAN I DO THIS NOW?`.
  Search and detail both resolve the step through `step_short` and both call `verdict_for`, so a
  multi-file step cannot answer for a different journal than the one that was clicked.
- **One statuette warning reader.** `read_warning` is the single save-aware read used by the step
  card, the band and `live_watch_for`; it applies the both/one/neither turn-in wording before any
  surface sees the row. The median save now says "You still need the soldier statuette" in all three
  places instead of a generic "Hand both statuettes" in two of them.
- **Documentation matches the product.** The target schema no longer says `goal` chips disappear with
  guidance off, the contract documents `view.status`, the order and card tags, and the first-run
  cutoff scenario now places `CUTOFF PASSED - CHECK NOW` on `MORE > STATUS` as the README and the
  locked band definition already did.

## Evidence from the real saves

Copied saves in temporary `APPDATA` profiles; the originals were not written and the game was not
launched.

| save | role | `top` tags | `todo` | cards owned/not/unknown |
|---|---|---|---|---|
| none | clean | `[]` | 0 | 0/0/224 |
| `ManualSave_53db8_7e221800_4f13d1b.sav` | earliest | `[]` | 2 | 27/196/1 |
| `ManualSave_5258a_7e224000_39e1473.sav` | median | `DO THIS NOW`, `CARD WINDOW OPEN` | 51 | 114/109/1 |
| `CheckPoint_10083c_7ea4f400_4f324d3.sav` | newest | `CARD WINDOW OPEN` | 60 | 129/94/1 |
| the newest save with four goals | goal | `CARD WINDOW OPEN` | 61, includes `q110postbattle` | 129/94/1 |
| the same save, guidance off | goaloff | `CARD WINDOW OPEN` | 61; 7 plan steps, 0 instructions, 4 goal chips | 129/94/1 |

Every profile had 412 steps, section totals 96+183+35+87+11, and `--dump` matched `--view` on `top`,
`todo` and the warning rows (`dump.status_rows` equals `view.status`). The statuette answer was `warn` "Find both statuettes, then talk to Triss"
(earliest), `warn` "You still need the soldier statuette" (median), and `info` "Triss has left
Novigrad - the next chance is Final Preparations" (newest). Dijkstra was `unknown` clean, `not_owned`
with `not_yet` earliest, and `owned` median and newest.

At 480x820 in the real `ui/`, the no-save payload hid the band, read "Load a save to see what is
next" in UP NEXT, and opened FOLDERS with the saves path and Browse. The earliest save hid the band,
carried only the tracked and in-log quests, and listed 31 ahead cards under MORE > CARDS > LATER. A
note-only tick kept `q110postbattle` at `Not started`, showed the pencil in PROGRESS and the NOTE
block on the detail page, and left the statuette warning in the band. The goal-off profile kept PLAN
AHEAD and the GOAL chip and showed no exact line. The corrupt-save payload named the file, said the
tracker retries, reopened FOLDERS and painted no band.

## Checks

| gate | result |
|---|---|
| `cargo test --locked` | 67 passed, 0 failed |
| `cargo build --release` | warning-free |
| `node --check ui/app.js` | clean |
| `py tools/regen.py --check` | all 12 outputs match the recorded hashes |
| `py tools/cardwindows.py check` | 224 cards = 15 missable (15 Tier B) + 17 one-time + 192 no-window |
| `py tools/test_cardwindows.py` | 13 tests, OK |
| `py tools/cards.py check` | 224 cards; 200 sourced, 24 unknown; median identity 114/109/1 |
| `py tools/endings.py check --release` | 4 targets, 4 guided, 0 warnings |
| `py tools/outcomecheck.py --release` | 4 groups, 11 outcomes, 0 warnings |
| payload assertion | `PASS: 4 real profiles, 518 corpus saves, 418 Baron-fact card rows` |

The mutation record for invariants 1, 3, 4, 5, 6 and 7 is in `NEXT-PHASE-PLAN.md` section 11.4: each
named test failed when its guarantee was deliberately broken, and every file was restored.

Game logs were re-read. `w3loadfix.log` ends with 0 verify errors, `WitcherNativeBridge.log` has all
registrations OK, `BeardmosImmersiveWorld.log` ends with its rain timer alive, and `OptiScaler.log`
ends with a normal DLL detach. `ReShade.log` and `RenoDX-DLSS5-crash.log` still record the native
layer crash at 2026-10-30 20:09 (`code=0x80000003`, `witcher3.exe+0x1f103a3`, `addon-module=no`); it
is not a tracker fault, and the tracker has no log by design.

## Artifact

- `dist/Witcher3MissablesTracker-1.3.4/Witcher3MissablesTracker.exe`
  SHA-256 `9b7d8454a50e185754b785f338ef810ac2ecd118c8574c59c2209b1cac4cf02d`
  (identical to the freshly built `target/release/witcher3-missables-tracker.exe`)
- `dist/Witcher3MissablesTracker-1.3.4.zip`
  SHA-256 `5792d8e465638fd435669c37003c919acd4bf6dda561ec9c02df90dad0dc02d4`
- FileVersion and ProductVersion are 1.3.4; the zip has 21 entries and `testzip()` is clean.
- The packaged binary matched the target build on every median `--view` field except the save's
  elapsed age, and on `--cards`.
- Repo-root `Witcher3MissablesTracker.exe` is the same binary.
- The build is unsigned. The repo configures no signing or store command and holds no credentials,
  so there is no remaining authorized release step.

`package.ps1` built the version and both artifacts. Its final convenience copy to the repo root
failed because the 1.3.3 tracker process was still running; the process was stopped, the same dist
binary was copied to the root, and all three copies hash to the value above. No push, tag or store
upload was performed.

## Still open

- No save in the 518-file corpus has both statuettes with the window still open, a soldier-only
  statuette, an unowned Dijkstra past the Baron line, an Active ending-relevant quest, or a passed
  cutoff check. Those rows are proved by shipped-data unit tests or fixture payloads, not by a real
  save.
- The native Tauri WebView was not automated. The real `ui/` was driven in Chromium at 480x820 with
  a mock built from the release binary's payloads.
- `cargo fmt --check` could not run because the toolchain has no `rustfmt` component installed. No
  formatting-only changes were made.
- The recorded native-layer crash above predates this release and is outside the tracker.
