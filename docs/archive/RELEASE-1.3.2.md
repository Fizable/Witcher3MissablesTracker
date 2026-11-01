# Witcher 3 Missables Tracker 1.3.2

Released: 2026-10-30
Previous package: `dist/Witcher3MissablesTracker-1.3.1/` (left untouched)

1.3.2 fixes a window-timing defect present in 1.3.0 and 1.3.1. A quest cutoff whose closing quest
had not started was put into the NOW band and turned into a warning on the quest page, with an
instruction to act before a quest the player had not reached. The statuettes were the visible case:
the band said to hand them to Triss during Final Preparations while Final Preparations was not in the
log and the turn-in was not available.

## What changed

- **An ahead quest window is no longer a NOW item.** The band keeps only what can change the outcome
  now: a loss, a cutoff you are standing inside, a cutoff that passed with the quest still open, a
  failed quest, a live ending choice, and a card window whose gate is active. This is the rule card
  windows already followed; quest windows now match it.
- **The quest page and search stop turning an ahead window into a warning.** The route model's own
  answer stands, so the statuettes read `safe` while their quests are open and Final Preparations has
  not started, and the ahead row is removed from the detail payload.
- **The step's own state follows.** A quest with only a future window is `obtainable`, not `at_risk`,
  until the closing quest enters the log.
- **The window itself is unchanged.** Its gate is the closing quest's journal: when Final
  Preparations becomes Active the row returns as `DO THIS NOW` with the both/one/neither wording, and
  once its Novigrad phase is done it reads `CUTOFF PASSED - CHECK NOW`. No card, route or cutoff data
  changed.

## Evidence on the reported save

`QuickSave_10aa70_7ea4f400_4141f72.sav`, copied into a temporary profile; Final Preparations is not
in the log.

| check | 1.3.1 | 1.3.2 |
|---|---|---|
| `--view` top | Iorveth card + "Finish The Nobleman Statuette and The Soldier Statuette before the end of Final Preparations" | Iorveth card only |
| statuette step watch | one `ahead` row | empty |
| statuette classification | `at_risk` / cutoff | `obtainable` / route |
| `--detail mq3012noblestatuette` | `warn`, "Both statuettes in hand - talk to Triss now" | `safe`, no details, `derived.watch=[]` |

The regression test `top_tests::only_the_journal_can_declare_a_loss` now asserts that an `ahead`
window on an Active quest produces an empty band; it fails against 1.3.1.

## Gate evidence

| gate | result |
|---|---|
| `cargo test --locked` | 57 passed, 0 failed |
| packaged exe `--view` / `--detail` | top = Iorveth card only; statuette `safe`, watch empty |
| `py tools/cardwindows.py check` | 224 = 15 missable (15 Tier B) + 17 one-time + 192 no-window |
| `py tools/test_cardwindows.py` | 13 tests, OK |
| `py tools/cards.py check` | 200 sourced / 24 unknown; newest save 129/94/1 |
| `py tools/regen.py --check` | all 11 outputs match the recorded hashes |

No save was written and the game was not launched. The native Tauri WebView was not driven by
automation; the packaged exe was exercised through its headless commands.

## Artifact

- `dist/Witcher3MissablesTracker-1.3.2/Witcher3MissablesTracker.exe`
  SHA-256 `c4105984e7237e3fac058f45daa5005c383b7915f8e2e31880e7c6d73d6db767`
- `dist/Witcher3MissablesTracker-1.3.2.zip`
  SHA-256 `49c292ef24e6e321a2a48a9eaa66b4c38dde7281fd81cb7750c8be6b7de92263`
- Repo-root `Witcher3MissablesTracker.exe` (same binary as the package)
- Zip entries: `22`; `testzip()` reports no damage.

## Still open

- The native Tauri WebView was not driven by automation.
- No corpus save has Final Preparations active with a statuette still open, so the `DO THIS NOW`
  state for this window is covered by the Rust fixtures rather than a real save.
- The 24 explicit unknown-source cards and the 3 unknown route nodes remain visible data gaps.
