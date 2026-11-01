# Release 1.0.0 - the completion planner

2026-10-28. The route was already generated from the game's files in 0.2. This release adds the part
that answers the other half of the question: **what am I aiming at, and how much of it is still
possible?** The route is unchanged at 403 quest steps plus 11 manual steps.

## What the screen does now

- **RUN** shows quest and card completion separately: total, done/owned, still possible, and only the
  non-zero trouble counts (at risk, lost, excluded, unknown). It never collapses them into one
  percentage, because mutually exclusive branches make a single percentage a lie.
- **Ending goals are opt-in.** The first-run card offers the spoiler-free path. Only after the user
  opens the goal picker does a target name appear. With a target selected, the matching mission's
  detail pane shows the reviewed line to say; the list never does. Clearing the target removes the
  label and line again.
- **Spoiler-free tags stay vague.** A mission card says `CHOICE`, `ENDING CHOICE`, `Gwent` or
  `missable` only when the files justify it. No card contains choice text.
- **GWENT CARDS** is the collection ledger: every card, its deck, its source (or `unknown source`),
  and owned / not owned / unknown from the save. The app says in the section that no card-level
  missable window is proven; it does not invent one.
- **COVERAGE** shows the measured extraction per pack. A zero or `not modelled` is visible rather
  than being mistaken for "nothing to lose".
- **IMPOSSIBLE / EXCLUDED** and **TRADEOFFS** exist for content that is already failed/lost or for
  reviewed exclusivity edges. `exclusive.json` is empty today, so the tradeoff section stays hidden.

## What is reviewed, and what is not

- `data/endings.json` has two reviewed targets. **Blood and Wine: both sisters live** is guided with
  two exact scene lines (`q704bfairyland` and `q705ceremony`). **Baron: his wife is cured** is
  deliberately `not_guided_yet`: its outcome is set by a phase script, not by a scene choice, so
  there is no reviewed line to show. The app says that and does not guess.
- The target state is computed from the loaded save and the branch graph:
  `settled`, `reachable`, `impossible`, `unknown` or `not_guided_yet`. A tick cannot overrule an open
  journal entry.
- `data/branches.json` contains extracted scene choices with their facts. `data/gwent_cards.json`
  contains the card index and measured sources. `data/coverage.json` contains the pack counts.
- `data/exclusive.json` is empty. No mutually exclusive edge has been reviewed, so the planner makes
  no tradeoff claim.

## Checks actually run

```
py tools/regen.py --check
  all 11 outputs match the recorded hashes

py tools/contradictions.py
  5 derived claims, 0 contradicted; 5 route prerequisites checked, 0 disputed
  (5 indexed saves are no longer present on disk; they are reported as unreadable, not as passes)

py tools/test_endings.py
  24 tests passed

cargo test
  23 passed, 0 failed
```

The 1.0 UI was rendered in a browser against generated `--view` and `--detail` payloads:

- spoiler-free profile: `RUN` reads `SPOILER-FREE`; the setup card is visible; the DOM contains no
  target label and no line; skipping writes an empty target and hides the card;
- guided profile: the both-sisters target reads `REACHABLE`; `q704bfairyland` shows
  `SAY THIS “I'll pay you for the ribbon.”`; `q705ceremony` shows
  `“You were children then, both.”`; the default list does not contain either line;
- source file/locId and fact names appear only inside the collapsed **Technical details** block,
  not next to the instruction;
- the card ledger opens, shows owned/not-owned/unknown without claiming a missable window;
- no console errors and no horizontal overflow in the tested viewport.

The packaged exe was checked from `dist/Witcher3MissablesTracker-1.0.0` against its own `data/`: the
`--view`, `--detail`, `--cards` and `--targets` outputs load the 1.0 files, the both-sisters target
reads `reachable`, and the exact line is present only under the guided profile. The root
`Witcher3MissablesTracker.exe` also reads the live `data/` and reports the reviewed targets.

## Limitations

- **No save in the 120 newest saves checked has the reviewed target facts**, so `settled` and
  `impossible` are covered by Rust unit tests on the save state, not by a real save that reached the
  Blood and Wine epilogue with a target applied. The wider corpus was not exhaustively scanned for
  these facts.
- **Only two targets exist.** The Baron goal is not guided; adding it needs a reviewed phase-script
  edge, not a guessed line.
- **Card-level missable windows are not proven.** Card ownership is shown, but the card section is a
  ledger, not a deadline warning.
- **Hearts of Stone has no Gwent card pack.** Blood and Wine card sources are measured; a random
  merchant reward can still be `unknown source` when the script does not name the merchant.
- **Exclusivity is not reviewed.** With `exclusive.json` empty, `max_achievable` is not reduced by a
  tradeoff edge; the UI has the section, but there is nothing to put in it yet.
- **One profile is one run.** Changing a goal recomputes guidance from the current save; it cannot
  undo a choice already settled.
