# 0.1.9 - a tick cannot outrank the journal

0.1.8 made every warning re-read against the loaded save, and then gave your own ticks the last word:
"a step you ticked yourself is finished as far as every warning is concerned". That is right for the
steps a save cannot show at all (a visit, a tutorial, a Gwent match), and wrong for everything else.

The case that broke it: the Nobleman and Soldier Statuettes were ticked done, but both were still
`Active` in the journal while all five quests that switch Triss off (Pyres of Novigrad, Novigrad
Dreaming, Count Reuven's Treasure, Now or Never, A Matter of Life and Death) were finished. The
cutoff had fired, the quests were unrecoverable, and the app showed no box at all - it reported a
loss that had already happened as nothing to worry about. A tick is a note about your memory; the
journal is a record of the game.

## What changed

- **The journal wins, and the disagreement is stated.** A tick only fills in what the save cannot
  show: it counts when the journal has nothing to say about the quest (no entry, `Not started`), and
  is set aside when the journal still carries it as `Active`. The cutoff stays on the card, and its
  `In this save:` line ends with `You ticked The Nobleman Statuette, The Soldier Statuette done, but
  the journal still has them open - the journal wins here.` Nothing is silently resolved either way.
- **A step ticked done no longer clears its own cutoff box.** The card's watch list used to be
  emptied whenever the step read `Done`; it is now only emptied when the step is over for a reason
  the journal can see.
- **The same rule in all three places the save is read**: the cutoff boxes on a step, the quest-order
  feed, and `--view` / `--dump` output, so what the app shows and what the check scripts read agree.
- Ticks on steps with no journal entry at all are untouched: those still count, because nothing else
  can answer for them.

## What was verified

- `cargo test`: 13 pass. The new test (`a_tick_never_silences_a_cutoff_the_journal_still_shows`)
  checks the three readings of the statuette cutoff: ticked with the quests open -> `passed` plus the
  disagreement sentence; unticked -> the same verdict without the sentence; both quests finished in
  the journal -> no box at all.
- **The real profile that produced the defect** (tick in place, newest save): the feed and both
  statuette steps now report `CUTOFF PASSED - LOST IN THIS SAVE`, with the tick sentence naming why.
  `--dump` agrees with `--view`.
- No change to anything else the app shows: the other four feed items still read as settled by the
  same save, and the step count, sections and DO NEXT order are untouched.

## Still open

- The step itself still reads `Done`, because the tick is still yours to keep. The box beneath it says
  the journal disagrees; the two readings are shown side by side rather than one being deleted.
- Coverage is still one reviewed cutoff and four feed items. This release changes how a claim is read
  against a save, not how many claims there are - that is 0.2's job (see `PLAN-0.2-quest-order.md`).
