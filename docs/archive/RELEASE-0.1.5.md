# 0.1.5 - quest order from the game's own files

This release replaces the quest-order advice with data worked out from the game's files, and adds
the machinery that keeps it honest. Nothing is read from a wiki to decide a warning any more; where
something is still wiki-only it is labelled as such in the app.

## What the app shows now

- Every step can carry a **cutoff** with the mechanism named: which quest switches off which game
  resource, and why the step needs it. Example (Soldier/Nobleman Statuette): *"Hand both statuettes
  to Triss before Pyres of Novigrad"* - because five quests switch off `triss.w2comm`, the community
  file that puts Triss in the world, and the statuette scenes are played with her.
- The **game's own wording**: 99 steps show the quest-log name from the string database, and the
  detail pane lists the objective list in quest-log order.
- Steps whose prerequisites the saves contradict carry a note saying so, instead of a silent rule.

## Where the data comes from

All of it is read from the player's own install, by the tools in `tools/` (see `tools/README.md`):

| source | what it gives |
|---|---|
| `.w2phase` quest graphs | who adds each quest's journal entry (`CJournalQuestBlock`), and what each quest's story phases switch off (`CDeactivateSpawnset`) |
| `.w2scene` story scenes | dialogue choices (`locId`), the facts a choice's section waits on, one-shot choices |
| `.journal` files | the quest's own entry GUID and its objectives, in quest-log order |
| `LocalEditorStringDataBaseW3_UTF8.db` | the game's text for all of the above, in English |
| 517 saves | the journal status each save recorded, in the order they were written |

`tools/derive.py` writes `data/derived.json` (what the app shows) and `data/cutoffs.json` holds the
reviewed cutoff selection - the only cutoffs that become warnings.

## What was verified, and how

- **Contradiction harness** (`tools/contradictions.py`): 10 claims about the derived data, tested
  against all 517 saves - all hold; 119 route prerequisites checked, 9 disputed and written to
  `data/route_disputes.json` rather than asserted.
- **App against the data**: the built exe's `--dump` is compared with the same save index (4 of 442
  quests read differently - the known description-entry cases - so this compares as a rate).
- **Reproducibility** (`tools/regen.py`): the whole pipeline re-runs byte-identically; 6 outputs are
  hash-checked against `tools/goldens.json`.
- **Parser hardening** (`tools/fuzz.py`): 60 truncated/corrupted files fed to the readers, no
  misreads and no unclean failures; an old container version (the version-129 `.w2dset` files) is
  refused instead of decoded into nonsense.
- **Unit tests**: 9 `cargo test` cases, including the quest-index build from the player's bundles.

## Still open

- **Quizzed prerequisites**: the 9 disputed ones need a decision - is the prerequisite wrong, or is
  the journal status reading (`Failed` for a quest that was never available) wrong? `q402skelligeallies`,
  `q402novigradallies` and `q302war` read `Failed` in saves where they cannot have been offered.
- **Save evidence cannot prove a cutoff.** For the statuette quests no save has ever finished them,
  so the saves are consistent with the cutoff but a quest nobody finishes looks like one that cannot
  be finished. The mechanism is what makes it a cutoff; the saves are corroboration.
- **Coverage**: 105 of 150 route quest names resolve to REDkit files; 47 (mostly Gwent decks and
  contract placeholders) have no quest graph at all. 20 journal files in REDkit are unreadable by
  the reader (older container versions).
- **Cutoff pool not yet reviewed**: 6,276 candidates from the files, 12 consistent with the saves;
  1 reviewed and shipped, 1 recorded as pending review in `data/cutoffs.json`.
- The GUI itself was not driven; verification was through `--dump`, the harness and the tests.
