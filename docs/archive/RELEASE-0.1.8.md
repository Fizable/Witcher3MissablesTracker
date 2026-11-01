# 0.1.8 - warnings that read your save

0.1.7 shipped the warnings as data: each one named the mechanism and the quest it protected, but the
sentence was fixed. "Hand both statuettes to Triss before Pyres of Novigrad" was shown on every save,
including one where Pyres of Novigrad, Now or Never and three other quests that switch Triss off were
already done and the statuettes were still open — the exact case where the advice is years too late
and the tracker should be reporting a loss.

## What changed

- **Every warning is re-read against the save on each refresh** (see `model.rs`, "a warning read
  against the loaded save"). The data names `affected` (what it protects) and `closed_by` (the quests
  that end it); the app looks both up in the loaded journal and labels the box:
  - `CUTOFF AHEAD` - none of the quests that end it has started; the original advice still applies.
  - `CUTOFF NOW - YOU ARE INSIDE IT` - you are in the quest that switches the resource off partway
    through; it names what you still have to finish.
  - `CUTOFF PASSED - LOST IN THIS SAVE` - a quest that ends it is already done and the protectee is
    still unfinished. The action line is dropped, because there is no longer an action.
  - `ALREADY LOST IN THIS SAVE` - the journal marks the protectee Failed.
  - no box at all once the protected quest is finished, or the step it hangs from is over.
- **Every box ends with an `In this save: ...` line** naming the status of every quest involved
  (`done: Pyres of Novigrad, Novigrad Dreaming; not started: Now or Never, ...`), so what the app says
  about your save is visible, not implied.
- **The same treatment for the order feed**: `ALREADY SETTLED IN THIS SAVE` for a gate the journal has
  passed, `MISSED IN THIS SAVE` when the gating quest is over and the gated quest never entered the log,
  `SETTLED BY YOUR SAVE` / `FAILED IN YOUR SAVE` for the refuted wiki claims (your journal answers
  those directly), and `NOT ANSWERED BY THIS SAVE YET` when the save has not reached the question.
  Live items sort above settled ones.
- **Corpus statistics are labelled as such.** Lines that describe the 517-save research corpus now say
  `Corpus (the 517 saves this was worked out on, not your current save)`, so they are not read as a
  claim about the save you have loaded.
- **Your own ticks count.** A step you ticked yourself is finished as far as every warning is
  concerned, so the feed can no longer contradict the card next to it.
- **`--view out.json`** writes exactly what the window is handed (the old `--dump` writes the state),
  so the rendered text can be checked without clicking through the GUI.

## What was verified

- `cargo test`: 12 pass, including the route/gate unit tests.
- `py tools/contradictions.py`: 12 derived claims, 0 contradicted; 115 prerequisites, 0 disputed. The
  app-vs-data check now runs the exe with its own throwaway profile (a tick or a cached index could
  otherwise decide whether the app and the data agree) and expects the data's warnings minus the ones
  the loaded save has overtaken.
- `py tools/regen.py`: all 7 outputs byte-identical to the recorded hashes.
- **Driven over three real saves** (`target/_ask/live_check.py` in the session that built it), one for
  each state: nothing started → `ahead`; Pyres of Novigrad in the log → `inside`; Pyres and Novigrad
  Dreaming done with the statuettes open → `passed`. The `In this save:` line matched the index's
  statuses in all three.
- **Rendered**, not just dumped: the real `ui/` was served against a `--view` payload and read in a
  browser. That is how two defects were caught and fixed - a gate counted a quest that the save only
  carries as "not started" as being in the log, and the failed-quest alert said "Still open: Twisted
  Firestarter" about a quest the journal had just marked Failed.

## Still open

- Coverage is unchanged: one reviewed cutoff (the statuettes), four feed items, and the wider cutoff
  pool (6,276 candidates from the files, 12 consistent with the saves) is still unreviewed.
- The app re-reads the warnings it has. It cannot invent warnings the data does not carry, and a
  cutoff whose `closed_by` quest is mid-way through is reported as `inside` rather than at the exact
  phase that fires - the journal does not record the phase.
- Expansion quests can be tested against the saves but still cannot be settled from the files: the
  file-derived index reads only the base game's quest graphs.
