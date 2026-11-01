# Witcher 3 Missables Tracker 1.3.3

Released: 2026-10-30
Previous package: `dist/Witcher3MissablesTracker-1.3.2/` (left untouched)

1.3.2 removed a warning that was wrong, and with it the only chance the app had to warn at all. The
statuettes are turned in to Triss. She is in Novigrad until Now or Never, she leaves on that quest,
and she is back for Final Preparations. The journal never fails the statuettes when she leaves -
their own phase switches her community back on for the turn-in scene - so the quest does not die at
Now or Never; the chance to act closes and a second chance opens later. 1.3.2 knew only the second
one, so an Act 1 save with both statuettes in hand said nothing, and the detail page said "no cutoff
is known" while a reviewed window existed.

1.3.3 models both.

## What changed

- **A new reviewed window: Triss leaves on Now or Never.** It closes at `q309mages#To Triss`, the
  first phase of Now or Never, and is marked `mechanism: "availability"` because no journal failure
  exists behind it. `tools/review_cutoffs.py` accepts it on that mechanism, after checking that the
  phase is real and the file evidence is named, instead of demanding a Failure branch.
- **The band shows it while you can act.** With Triss still in Novigrad and the quest Active, the
  statuettes are `DO THIS NOW` with the both/one/neither wording: "Both statuettes in hand - talk to
  Triss now", "You still need the soldier statuette", or "Find both statuettes, then talk to Triss".
- **After she leaves, the app says so and says where the next chance is.** The row becomes
  `WINDOW CLOSED - NEXT CHANCE LATER`, level info, never a NOW item: "Triss has left Novigrad - the
  next chance is Final Preparations". It is not a loss and the quest is not called lost.
- **Final Preparations is still the last window.** The existing `q210preparations#Novigrad` window
  keeps its `DO THIS NOW` while that quest is open, and outranks the "she has left" note on the
  quest page.
- **Quest state follows.** An open availability window classifies the quest as at risk; the closed
  one leaves it obtainable, because it can still be finished later.

## Evidence from the real saves

| save | Now or Never | statuettes | band | quest page |
|---|---|---|---|---|
| `ManualSave_53db8_7e221800_4f13d1b.sav` (earliest) | not started | not started | empty (nothing accepted) | `warn` "Find both statuettes, then talk to Triss" |
| `ManualSave_5258a_7e224000_39e1473.sav` (median) | not started | Active | `DO THIS NOW` "Hand both statuettes to Triss before she leaves Novigrad" | `warn` "You still need the soldier statuette" |
| `AutoSave_10d9e0_7ea4f000_581b307.sav` (newest) | done | Active | Iorveth card only | `info` "Triss has left Novigrad - the next chance is Final Preparations" |
| `QuickSave_10aa70_7ea4f400_4141f72.sav` (reported save) | done | Active | Iorveth card only | `info` "Triss has left Novigrad - the next chance is Final Preparations" |

Every save was copied into a temporary profile; the originals were not written and the game was not
launched. The packaged exe was checked on the median and newest saves and returned the same answers
as the debug build.

## Checks

| gate | result |
|---|---|
| `cargo test --locked` | 59 passed, 0 failed (two new window tests) |
| `py tools/review_cutoffs.py build` | 1 community cutoff, 2 journal windows, 43 decisions |
| `py tools/derive.py` | 403 quests, 412 steps, 3 reviewed cutoffs, 6 steps carrying a warning |
| `py tools/regen.py --check` | all 11 outputs match the recorded hashes |
| `py tools/cardwindows.py check` | 224 = 15 missable + 17 one-time + 192 no-window, unchanged |
| `py tools/test_cardwindows.py` | 13 tests, OK |

## Artifact

- `dist/Witcher3MissablesTracker-1.3.3/Witcher3MissablesTracker.exe`
  SHA-256 `6886cae1e30e5e53bcccfb5e6c41ccc974b41ebd7264fa3ab2ef19805bc09b51`
- `dist/Witcher3MissablesTracker-1.3.3.zip`
  SHA-256 `387bc0c70a5b32e38e668828c57eccc84e4e1d070eafa1f6b619ef9a99a251fe`
- Repo-root `Witcher3MissablesTracker.exe` (same binary) and 22 zip entries, `testzip()` clean.

## Still open

- The window closes at the start of Now or Never. Triss may still be talkable for the first moments
  of that quest; closing at its start is the conservative side and matches the save where she
  refused to discuss the statuettes while it was under way.
- No corpus save has Final Preparations active with a statuette still open, so `DO THIS NOW` for the
  second window still rests on the game files rather than a save.
- The native Tauri WebView was not driven by automation; the packaged exe was checked through its
  headless commands.
