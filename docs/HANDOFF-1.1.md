# Handoff 1.1 - the outcome matrix and the run plan

Status: **current, next milestone.** The card-deadline work is deferred to
[PLAN-1.2-card-deadlines.md](PLAN-1.2-card-deadlines.md). This file is the handoff for a new chat:
it records what 1.0 really has, the gap that matters more than cards, the data model, the work
order and the acceptance checks.

Project: `C:\Steam\steamapps\common\The Witcher 3\w3tracker`

## 1. The goal, unchanged

The app answers one question: **what do I do next in this save, and what can I still lose?**

- The game's files decide every rule.
- The loaded save decides every fact about where you are.
- The app decides only order and presentation.
- No second-hand knowledge, no wiki text, no guessed dialogue line.
- Silence is valid when nothing can still change.
- Ticks fill gaps the save cannot see; the journal and a fired cutoff outrank a tick.
- No spoilers by default. Outcome names and exact lines appear only after the user opts in.
- Universal by construction: keyed on quests, facts and outcomes, never on one save.

The long-term user goal is **100% completion: all obtainable quests, chosen endings for the base
game and both DLCs, and no missed Gwent cards**.

## 2. The correction: cards are not the blocker. Outcomes are.

The 1.0 card ledger is a valid later feature, but it is not the reason the app cannot yet answer the
100% question. The blocker is that the app has **no outcome model**.

Measured on the current checkout:

| area | measured state | consequence |
|---|---|---|
| selectable ending targets | 2 | far short of base + Hearts of Stone + Blood and Wine |
| guided ending targets | **1**: `bw_both_sisters` | only one ending can be actively guided |
| placeholder target | **1**: `baron_wife_cured`, `guidance_status: not_guided_yet` | it names a goal but has no facts and no path |
| `recommended` preset | includes both, one of them unguided | "Recommended endings" is not yet a real recommendation |
| ending schema | `requires[].source.kind` and `guidance[].source.kind` are exactly `scene_choice` | phase-set outcomes cannot be represented |
| `data/branches.json` | 2,286 choices over 141 steps | rich scene data, but not an outcome catalogue |
| q105 branches | 96 choice rows that set facts | the Baron material exists, but no reviewed outcome rows use it |
| q502 branches | 7 choice rows, mostly scene setup | main-story fate is not a scene-choice target |
| q503, q504, q505 branches | **0** choice rows that set facts | the main-story ending cannot be expressed with the current schema |
| q605 branches | 8 choice rows, all scene setup | Hearts of Stone finale has no outcome row |
| q704 / q705 branches | 74 / 44 choice rows that set facts | Blood and Wine is the one pack with usable scene-choice evidence |
| `tools/fact_index.json` | base-game phase files only; **0 DLC sources** | no phase facts from `ep1` or `bob` |
| `data/exclusive.json` | **0 edges** | no outcome or quest exclusivity is modelled |
| `data/coverage.json` | quest/card coverage only | no outcome coverage dimension |
| save corpus | 547 indexed saves; **none** carries `q502_ciri_dead`, `q502_ciri_survives`, `q605_*`, `q704_ft_ribbon_won` or `q705_henrietta_alive` | terminal outcomes need synthetic fixtures, not only the corpus |
| q105 save facts | `q105_kids_gone` in 217 saves; `q105_evil_spirit_done` in the corpus | the Baron branch is visible in saves; the exact terminal flags still need review |

Two facts make the gap precise:

1. **The two ending rows are not equivalent.** `bw_both_sisters` has two validated facts and two
   exact scene lines. `baron_wife_cured` has `requires: []` and a note saying the Whispering Hillock
   outcome is set by `q105_evil_spirit.w2phase`, not by a scene choice. It is a reviewed label with
   no path.
2. **The main story has no row at all.** The phase facts exist (`q502_ciri_dead`,
   `q502_ciri_survives`, `q502_ciri_strong`, `q502_ciri_weak`), but `branches.json` cannot set them
   and the target schema rejects a phase-fact source. The epilogue's `ending_boards.w2phase` tests
   these facts; that is the file evidence for the eventual matrix.

This is why adding a third or fourth ending row to `endings.json` would not fix it. The data model
has to grow first.

The sample rows in §5 are shape examples, not reviewed conclusions. In particular,
`q502_ciri_survives` is a phase flag; the reviewer must confirm that it is the terminal flag the
epilogue tests, not an intermediate flag. Do not copy an example row into `data/outcomes.json`
without that review.

## 3. The thing that has not been said: there is no single 100% path

This is the most important product decision in the milestone.

Witcher 3 has at least two kinds of exclusivity:

- **Outcome exclusivity**: two terminal states in the same group cannot both be true in one save.
  Ciri cannot both live and die; the Baron's family cannot end in every state at once.
- **Quest exclusivity**: some quests are mutually exclusive, or become unavailable after a choice
  or cutoff. `data/exclusive.json` currently proves none of them.

Therefore a claim like **"one path that gets 100% of quests and 100% of endings" is impossible.**
The honest product is three separate things:

| thing | question it answers | what it must never claim |
|---|---|---|
| **run** | one save lineage, with one outcome per exclusive group | that it is the only way to play |
| **run plan** | what to do in this save for the chosen outcomes, in route order | that every quest in the game fits this run |
| **run set / coverage** | the minimum number of runs that can see every outcome and every obtainable quest | that a single save can see everything |

The app should say, for example, "these two goals cannot coexist in one save; covering both needs
2 runs" rather than silently dropping one or showing a false 100%. That sentence is the core of the
planner.

This also means **"All quests" is not a target that can be evaluated without quest-exclusivity
edges.** Until those edges are reviewed, the correct state is `unknown`, not `100%`.

## 4. What counts as an outcome

An **outcome** is a terminal state the game's own facts can distinguish, not every dialogue
variation and not a walkthrough step.

Good outcome candidates:

- a fact the epilogue or a quest phase tests to choose a scene or journal entry;
- a fact that one phase sets and another phase branches on;
- a journal `Failed`/`Done` state that is decided by a reviewed cutoff or a branch.

Not outcomes:

- every `CChoice` row;
- a one-shot dialogue line that changes only a local scene flag;
- a quest objective;
- a wiki category such as "good ending".

The first scope should be small enough to review completely:

| pack | outcome group(s) to review | evidence already present |
|---|---|---|
| base | main-story Ciri fate | `q502_*` facts; `ending_boards.w2phase` tests |
| base | Baron family outcome | 96 q105 scene choices; `q105_evil_spirit.w2phase` facts |
| base | major world state only if the save exposes a fact the epilogue tests | `q505_*` facts; review first, do not assume |
| `ep1` | Hearts of Stone finale (Olgierd / Gaunter) | DLC phase files have not been indexed yet |
| `bob` | Blood and Wine sisters / duchy outcome | q704/q705 scene choices; `q705_henrietta_alive` / `_dead` |

The exact number of outcomes is a review result, not a target. The plan should not invent labels
before the facts are read. A group may contain 2, 3 or more terminal states; the matrix must be
complete, not symmetrical.

## 5. Data model

The reviewed data stays in `data/`; generated candidate reports stay in `tools/`. The app never
generates an outcome label or an instruction.

### 5.1 `data/outcomes.json` (new, reviewed)

One row per terminal state. It is the matrix; it is not the user's goal list.

```json
{
  "version": 1,
  "note": "Reviewed terminal outcomes. Facts come from the game files; labels are reviewed.",
  "groups": {
    "main_ciri": {
      "pack": "base",
      "label": "Main story: Ciri's fate",
      "selection": "one",
      "outcomes": ["main_ciri_lives", "main_ciri_empress", "main_ciri_dead"]
    }
  },
  "outcomes": {
    "main_ciri_lives": {
      "group": "main_ciri",
      "pack": "base",
      "label": "Ciri lives",
      "spoiler": true,
      "reviewed": "2026-10-28",
      "requires": [
        {
          "fact": "q502_ciri_survives",
          "value": true,
          "source": {
            "kind": "phase_fact",
            "file": "quests\\part_3\\q502_avallach.w2phase",
            "fact": "q502_ciri_survives"
          }
        }
      ],
      "guidance": [
        {
          "step": "q502...",
          "kind": "quest_action",
          "instruction": "an exact journal objective line, not a paraphrase",
          "source": {
            "kind": "journal_objective",
            "file": "quests\\...\\...w2journal",
            "locid": 123456
          }
        }
      ]
    }
  }
}
```

Rules:

- `requires[].value` may be `true` or `false`, but `false` has a narrow meaning: **the save's
  facts DB has been observed not to contain the fact after the deciding step**. If the app cannot
  distinguish "not reached" from "not set", it must return `unknown`, never `false`. The current save
  reader only exposes set facts, so most exclusivity should be expressed by groups, not negatives.
- A `selection: "one"` group has mutually exclusive outcomes. When one outcome is met, every other
  outcome in the group is `impossible`, not `unknown`.
- `selection: "many"` is for independent world states that can coexist.
- `guidance[].kind` is one of:
  - `scene_choice` - the existing exact dialogue line, validated against `branches.json`;
  - `quest_action` - an action named by a journal objective or a reviewed action label, validated
    against the string database;
  - `phase_fact` - the outcome is set by a phase script and there is no dialogue line; the row may
    carry only the exact objective that describes the action, plus a mechanism note.
- A `phase_fact` row must never invent "say X". If the game gives no player-facing line, the card
  says so and shows the objective. That is still useful guidance and still traceable.
- A `not_guided_yet` outcome is allowed in the matrix. It is excluded from `recommended` and from
  any "100% path" claim until it has a reviewed guidance row.

### 5.2 `data/endings.json` (existing, extended)

Keep it as the **user-selectable goals**, not a second matrix. Add optional fields:

```json
{
  "label": "Blood and Wine: both sisters live",
  "outcomes": ["bw_both_sisters"],
  "completion": "chosen_outcomes",
  "requires": [],
  "guidance_status": "guided",
  "guidance": []
}
```

- `outcomes` names one or more rows in `outcomes.json`.
- `completion` is `"chosen_outcomes"` or `"all_obtainable_quests"`. The second one is allowed only
  when the selected outcome set is compatible and when quest-exclusivity coverage is known.
- A target may still keep its own `requires`/`guidance` for compatibility, but the checker must
  reject duplication that disagrees with the outcome row.
- `baron_wife_cured` must not stay in the `recommended` preset while it is `not_guided_yet`. Either
  guide it from the q105 phase facts in this milestone or remove it from the preset and label it
  "not guided yet" in the picker.

### 5.3 `data/exclusive.json` (existing, extended)

The current file has 0 edges and only accepts `kind: "target"`. Extend it to reviewed evidence:

- `kind: "outcome"` - two outcomes cannot coexist even across groups;
- `kind: "quest"` - two quests cannot both be completed in one save;
- each edge needs a `mechanism`: `file`, a `fact` or `locid`, and a short reviewed reason.

An edge is not inferred from "these look related" and not from two quests appearing in the same
chapter. The checker rejects an edge without file evidence.

### 5.4 Coverage

Add `data/outcome_coverage.json` (generated) with, per pack:

- total outcomes;
- guided outcomes;
- outcomes with a real save fact;
- outcomes that can only be tested with a fixture;
- groups and their `selection` mode;
- unresolved outcomes and why.

Do not merge this into `coverage.json` until the schema is settled; keep quest/card coverage and
outcome coverage separate so a number cannot be mistaken for another.

## 6. Tooling

### 6.1 DLC phase facts first

`tools/factgates.py` scans `paths.QUEST_ROOT` only. That is `r4data/quests`, which is base-game.
`tools/fact_index.json` has 0 DLC sources even though `ep1` and `bob` phase files exist.

Change:

- scan `r4data/quests` plus the DLC roots under `r4data/dlc/*/data/quests` (reuse the DLC path
  rules in `tools/questindex.py` / `tools/resources.py`; do not write a second path classifier);
- keep the existing `src` format relative to `r4data`;
- do not overwrite base rows with a DLC row of the same fact; both sources are evidence and both
  must be listed;
- keep the build cache resumable, and report the added file/row counts.

Check: q605, q704 and q705 each produce at least one phase row; `src` contains `dlc\`; the base row
count does not change.

### 6.2 Candidate report, not guessed data

Add `tools/outcomeprobe.py`:

- reads `fact_index.json`, `branches.json`, `route.json` and the journal index;
- proposes candidate outcome facts, grouped by reviewed group keys from a small config file;
- for each candidate, records: fact, setter file, tester file, set/test kind, whether a scene
  branch sets it, the quest step, the journal objective text if any, and the source hash;
- outputs `tools/outcome_candidates.json` and a Markdown review table;
- never writes `data/outcomes.json` and never writes labels.

The reviewer promotes candidates into `data/outcomes.json` by hand. The probe's job is to make the
review cheap and to show what is missing.

### 6.3 Checker

Add `tools/outcomecheck.py` or extend `tools/endings.py check`:

- every `outcomes.json` id, group, pack and review date is valid;
- every `requires` fact resolves in `fact_index.json` (base or DLC);
- every `scene_choice` guidance row still matches a branch's scene and locid;
- every `quest_action` instruction equals a journal objective locid's exact text;
- every `phase_fact` row names a real phase file and a fact that file sets;
- every group has at least two outcomes and every outcome belongs to exactly one group;
- `selection: "one"` groups have no two outcomes selected in the same run;
- `recommended` contains no `not_guided_yet` target;
- every `exclusive.json` edge has a mechanism;
- coverage counts are exact and reproducible.

The checker is the gate. A row is not shipped because it sounds right; it ships because the file
and the string database agree.

### 6.4 Quest exclusivity

Add `tools/exclusivity.py` (can be a later slice of 1.1, but it blocks the 100% claim):

- candidate pairs from `CJournalQuest` failure blocks, reviewed cutoffs, `CDeactivateSpawnset`, and
  facts one phase sets while another tests;
- for each candidate, report the file and fact;
- reject a candidate when any save in the corpus shows both quests done;
- output a review table, then populate `data/exclusive.json` only with reviewed edges.

Check: no edge is accepted without a file mechanism; `contradictions.py` still reports 0
contradicted claims; the count is reported honestly, even if it stays low.

## 7. Backend

### 7.1 Files and command surface

Add:

- `src/outcomes.rs` - load `outcomes.json`, evaluate each outcome, enforce group selection;
- `src/plan.rs` - the run planner and the run-set planner;
- `src/exclusive.rs` or extend the existing exclusivity loader - reviewed edges.

Commands:

- `get_outcomes` - the matrix, **spoiler-gated**. It must not be called on startup in spoiler-free
  mode, and its labels must not be hidden in the default DOM. This mirrors the existing
  `get_targets` rule.
- `get_plan` - the current run plan for the selected targets/outcomes. It may be part of
  `get_view` if the payload stays small and the no-spoiler rule holds.
- `get_runset` - the minimum run set for "cover all outcomes". This is a separate opt-in view, not
  the default screen.

### 7.2 Outcome state

For each outcome:

| state | rule |
|---|---|
| `met` | every `requires` fact is set |
| `open` | at least one requirement is unset, at least one guidance row is `ahead`, no requirement is closed |
| `impossible` | a requirement is closed, or another outcome in the same `selection: one` group is `met` |
| `unknown` | the save/data cannot decide, including a missing DLC fact index or an unguided phase action |

Group rule: once one outcome in a `selection: one` group is `met`, the others are `impossible` with
`blocked_by` naming the met sibling. This is how the app represents "Ciri lives" without a negative
fact.

Do not reuse `not_guided_yet` as a save state. It is a definition state: the outcome exists but the
reviewer has not supplied a path. It must never become `open`.

### 7.3 Run plan

Inputs: selected outcomes, route order, quest statuses, cutoffs, prerequisites, branch states,
reviewed exclusive edges.

Algorithm:

1. Evaluate every selected outcome. If any is `impossible`, the plan is `blocked` with the reason.
2. If two selected outcomes share a `selection: one` group, return `conflict` and do not pretend one
   can be dropped silently. The UI must ask the user to choose or plan two runs.
3. Collect the guidance rows that set the required facts. Add their steps and the prerequisite
   closure of those steps.
4. Sort by route order. A step that is already done is `settled`; a step behind the save without
   the fact is `unreachable`; a step whose cutoff fired is `blocked`.
5. Return `steps` with `ahead` / `settled` / `unreachable` / `blocked`, plus the reason and the
   exact instruction only for `ahead`.
6. Return `coverage`: how many route quests this run includes, which outcome groups it covers, and
   which selected goals it cannot cover. Do not call this "100%" unless every gap is zero.

The plan is allowed to say "no path with the current data". That is the correct answer for an
unguided outcome, and it is better than a false step.

### 7.4 Run set ("what would 100% take?")

For a selected "cover all outcomes" mode:

1. Group outcomes by `selection: one`; a run can realize at most one per group.
2. The lower bound is the largest group size. Add cross-group `exclusive` edges as compatibility
   constraints.
3. Build a greedy run set, then an exact search for the small number of groups; return the minimum
   number of runs and the outcome assignment for each.
4. For each run, show the outcomes it covers and the quests that conflict with the others.
5. If quest-exclusivity edges are unknown, report `quest_completion: unknown`. Do **not** add
   "all quests" to the run-set denominator.

This is the feature that answers "how do I 100% the game?" honestly: a set of runs, not a single
checklist.

## 8. UI

The default screen stays exactly as it is when no goal is selected: no outcome names, no matrix,
no target labels.

When the user opens the spoiler gate:

- **Goal picker**: groups, outcomes, states, and a line saying whether the selection is one run or
  needs multiple runs.
- **Outcome matrix**: a table of groups x outcomes, with `met` / `open` / `impossible` / `unknown`
  / `not guided yet`. Labels are visible only here, after opt-in.
- **Run strip**: the selected outcomes and a conflict message. It is not a second to-do list.
- **Run plan**: a detail drawer or a section inside `DO NEXT`, showing only the selected run's
  required steps in route order. `DO NEXT` remains the single ordered list; the plan annotates it
  with `GOAL` chips rather than creating a competing list.
- **Coverage**: under `PROGRESS`, outcome groups covered and the minimum run count; never a single
  "100%" number until the gaps are zero.

Screen order remains: `AT RISK NOW` (when non-empty) -> `DO NEXT` -> `PROGRESS`. If a run strip is
added, it is a header, not a fourth urgency column.

The `baron_wife_cured` card must stop saying "not guided yet" once q105 phase guidance is reviewed,
or it must be visibly marked as a goal with no path. The current picker hides that distinction too
well.

## 9. Work order

Do not start with UI. Start with the evidence.

### Slice A - DLC facts and candidates (parallelizable)

1. Extend `factgates.py` to DLC roots; rebuild `fact_index.json`.
2. Add `outcomeprobe.py`; produce `outcome_candidates.json` and the review table.
3. Report measured counts: phase files, facts, candidates, facts with a scene setter, facts with
   only a phase setter.

Check: q605/q704/q705 have rows; base counts unchanged; the candidate report has a file for every
row.

### Slice B - schema and reviewed matrix (depends on A)

1. Extend `TARGET-SCHEMA.md` with `outcomes.json`, `selection`, the three guidance kinds, and the
   negative-fact rule.
2. Extend `endings.py` / add `outcomecheck.py`.
3. Review and write `data/outcomes.json`. Start with the groups in §4; do not add a group until its
   facts and at least one guidance row are reviewed.
4. Remove `baron_wife_cured` from `recommended` while unguided, or guide it from q105.
5. Generate `outcome_coverage.json`.

Check: checker passes; every guided row's exact text resolves; every unguided row is excluded from
recommended; coverage counts match the file.

### Slice C - planner (depends on B)

1. Add `outcomes.rs` and `plan.rs`.
2. Implement outcome states, group exclusivity, conflict detection, route-ordered plan, and the
   run-set lower bound.
3. Add `get_outcomes`, `get_plan`, `get_runset` with the spoiler gate.
4. Update `docs/BACKEND_CONTRACT.md` for the new commands, payload fields and the rule that
   `get_outcomes` is never called on startup.

Check: Rust tests for met/open/impossible/unknown, sibling exclusivity, conflict, plan order,
blocked cutoff, and a run set with at least two runs.

### Slice D - UI (depends on C)

1. Add the matrix/picker behind the existing gate.
2. Add the run strip and plan annotations.
3. Add outcome coverage to `PROGRESS`.

Check: default payload has no labels; opt-in payload has labels; a conflict shows a conflict, not a
silent choice; a phase-action outcome shows the objective and no invented line.

### Slice E - quest exclusivity and honest 100% (parallel with B/C)

1. Add `exclusivity.py` and the candidate review.
2. Populate only proven edges.
3. Make `all_obtainable_quests` return `unknown` until the edge set is reviewed.

Check: 0 contradicted claims; no edge without a mechanism; the run set never counts a mutually
exclusive pair as simultaneously obtainable.

### Slice F - packaging

Bump to 1.1.0 only after A-E pass. `package.ps1` must leave the newest exe in the tracker folder and
a new zip in `dist/`; the packaged exe must read its own `data/` and expose `--outcomes`, `--plan`
and `--runset` without the checkout.

## 10. Acceptance checks

Run all of these; report the measured numbers, not promises:

```text
py tools/factgates.py build
py tools/outcomeprobe.py
py tools/outcomecheck.py
py tools/test_outcomes.py
py tools/endings.py check
py tools/contradictions.py
py tools/regen.py --check
cargo test
```

Required outcomes:

- `outcomecheck.py`: 0 errors, 0 warnings that hide a missing fact.
- `contradictions.py`: 0 contradicted claims, 0 disputed prerequisites.
- `regen.py --check`: all generated outputs byte-identical.
- `cargo test`: all tests pass, including the new outcome and planner tests.
- Default `--view` on a save: no outcome label, no matrix, no target label.
- `--outcomes` after opt-in: every group and outcome present; states match the save.
- `--plan` on a selected target: route-ordered steps; no step after its own cutoff; conflicts are
  explicit.
- `--runset` for all outcomes: minimum run count and per-run assignment; if quest exclusivity is
  unknown, `quest_completion` is `unknown`.
- Three UI payloads: early, mid, epilogue; plus one synthetic fixture per pack for a terminal
  outcome, because the 547-save corpus does not carry the terminal q502/q605/q704/q705 facts.
- Packaged exe from `dist/.../` reads its own `data/` and passes the same checks.

## 11. Decisions to settle before coding

These are the only open choices that change the shape of the work:

1. **Outcome scope.** Recommended: main-story Ciri fate, Baron family, Hearts of Stone finale,
   Blood and Wine sisters/duchy. Add major politics/romance only if the save exposes a terminal fact
   the epilogue tests. Do not try to model every dialogue flag.
2. **One run vs run set.** Recommended: both, but they are different screens. The default is one
   run for the chosen outcomes; "cover everything" is a run set with a minimum count. Never show a
   single 100% bar for the whole game.
3. **Phase guidance.** Recommended: use exact journal objectives for `quest_action`/`phase_fact`;
   if there is no player-facing line, say "no dialogue line is involved" and show the objective.
   Do not invent a line and do not call the outcome unguided just because it is not dialogue.
4. **Quest exclusivity.** Recommended: include the candidate audit in 1.1, but ship only proven
   edges. Until then, "all quests" is `unknown`, not 100%.
5. **Placeholder targets.** Recommended: remove `baron_wife_cured` from `recommended` immediately;
   guide it in 1.1 if q105 review succeeds, otherwise keep it in the matrix as `not guided yet` and
   out of the recommendation.

## 12. Prompt for a new chat

Copy this:

```text
Work in the Witcher 3 Missables Tracker at
C:\Steam\steamapps\common\The Witcher 3\w3tracker.

Read, in this order: docs/HANDOFF-1.1.md, docs/TARGET-SCHEMA.md,
docs/PLAN-1.0-completion.md and docs/RELEASE-1.0.0.md.

Implement milestone 1.1: the outcome matrix and the run planner. The current
ending layer has only one guided target and only accepts facts set by scene
choices; main-story and Hearts of Stone outcomes are phase-set facts. Extend
the fact index to the DLC phase files, produce a reviewed outcome-candidate
report, then add data/outcomes.json with terminal outcome groups for the base
game, Hearts of Stone and Blood and Wine. Extend the schema and checker for
phase_fact and quest_action guidance, and keep every instruction exact game
text or an explicit "no dialogue line" mechanism note.

Then add the run planner: one run for selected outcomes, explicit conflicts for
mutually exclusive outcomes, route-ordered steps, and a separate run-set view
that reports the minimum number of runs needed to cover all outcomes. Do not
claim a single 100% path for quests and endings; if quest-exclusivity evidence
is not reviewed, report quest coverage as unknown. Keep the spoiler gate: the
default view must contain no outcome labels or lines.

Do not write guessed outcome rows, wiki text, or anything from one save. Keep
py tools/regen.py --check, py tools/contradictions.py, py tools/test_endings.py,
py tools/outcomecheck.py and cargo test passing. Verify the default and opt-in
payloads plus three save states, use synthetic fixtures for terminal outcomes
the 547-save corpus does not contain, and finish with package.ps1 -Bump minor so
the packaged exe reads its own new data. Report the measured number of guided
outcomes and the minimum run count; say honestly if either is incomplete.
```
