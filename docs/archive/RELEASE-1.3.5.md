# Witcher 3 Missables Tracker 1.3.5

Released: 2026-10-31
Previous package: `dist/Witcher3MissablesTracker-1.3.4/` (left untouched)

1.3.4 still listed every in-log quest in `UP NEXT`. On the newest save that meant the two statuette
quests sat in the queue even though Triss had already left Novigrad and their only live action was a
later turn-in. 1.3.5 makes the queue the small surface it was meant to be: the quest you are
tracking and the one next plan step. Other in-log quests stay in `MORE > PROGRESS`; a window already
carried by `NOW` is not repeated.

## What changed

- **`UP NEXT` is no longer a second quest log.** `model::todo_order` admits the tracked quest and the
  next unblocked plan step only. On the copied saves the queue is 0 (clean), 1 (earliest, tracked
  `q001beggining`), 1 (median, tracked `q302mafia`), 1 (newest, tracked `q401_phylactery`) and 2
  (goal profile, tracked plus `q110postbattle`).
- **The statuettes leave the queue without leaving the warning.** The median profile still shows
  `DO THIS NOW` "You still need the soldier statuette" in `NOW` and the same answer on the quest
  page; neither statuette id is in `view.todo`. On the newest profile the statuette window is
  `later`, so the band stays silent and the queue still does not carry them.
- **One owner for the rule.** The UI displays `view.todo` as-is; no second filter was added.
  `README.md`, `docs/DESIGN.md` 10.9 and `docs/BACKEND_CONTRACT.md` all state the smaller queue.
- **1.3.4's claim is withdrawn.** That package did restore the search verdict, STATUS rows and the
  single watch reader, but it did not simplify the queue. Its release page now says it was superseded
  on this point.

## Evidence

Copied saves in temporary `APPDATA` profiles; the originals were not written and the game was not
launched.

| profile | `view.todo` | queue | statuette in `NOW` | statuette in `todo` |
|---|---|---|---|---|
| clean | 0 | empty | no | no |
| earliest | 1 | tracked `q001beggining` | no | no |
| median | 1 | tracked `q302mafia` | `DO THIS NOW` "You still need the soldier statuette" | no |
| newest | 1 | tracked `q401_phylactery` | no | no |
| goal | 2 | tracked + `q110postbattle` | no | no |

`py .next-phase/release/run.py` printed `PASS payload matrix: 7 profiles, 412 steps each, dump=view`;
its top/todo/cards output was `0/0/224, 0/1/27/196/1, 2/1/114/109/1, 1/1/129/94/1`. The goal plan
still has 7 steps and 4 instruction rows; guidance off has 7 steps, 0 instructions and 4 goal chips.
`--dump` matched `--view` on `top` and `todo` for every profile.

At 480x820 the real `ui/` rendered the newest payload as one `The Final Trial` card, with no
statuette text in the queue, no toggle, `scrollWidth == clientWidth == 480` and no console errors.
The median payload rendered the statuette warning in `NOW` and one `Get Junior` card in `UP NEXT`,
again with no statuette in the queue. The goal payload rendered `The Final Trial` and `Blood on the
Battlefield`.

The packaged WebView was also read directly through WebView2's debugging port on the newest copied
profile: `#todoCards` had one card, `#todoSec` had no statuette text, `innerWidth` and `scrollWidth`
were both 480, and the embedded UI carried the new one-line legend. This is the same `ui/` that ships
in the executable, not a browser-only mock.

`cargo test --locked`: 67 passed, 0 failed. `cargo build --release`: warning-free. `node --check
ui/app.js`: clean. `package.ps1` built the version and did not touch the 1.3.4 folder.

## Artifact

- `dist/Witcher3MissablesTracker-1.3.5/Witcher3MissablesTracker.exe`, FileVersion and
  ProductVersion 1.3.5, SHA-256
  `a189fa75df22b5005e72392794300952c510aa33e608bd9e511323e8069d78dd`
- The repo-root `Witcher3MissablesTracker.exe` and the freshly built
  `target/release/witcher3-missables-tracker.exe` have the same hash.
- `dist/Witcher3MissablesTracker-1.3.5.zip`, 21 entries, `testzip()` clean, SHA-256
  `804a18a8513620b3e45c6b980328d0fe79fe9d37d31ee8bac55f26ffc21a20db`; the executable inside the
  zip has the same 1.3.5 hash.

## Still open

The states the 518-save corpus cannot produce are unchanged: both statuettes with the window open,
a soldier-only statuette, an unowned Dijkstra past the Baron line, an Active ending-relevant quest,
and a passed cutoff check. Those are proved by shipped-data unit tests or fixture payloads. The
1.3.5 DOM read covers the packaged window's queue and legend, not every interactive control in the
WebView. The build is unsigned and has no store upload step; no signing or store credentials are
configured in the repository.
