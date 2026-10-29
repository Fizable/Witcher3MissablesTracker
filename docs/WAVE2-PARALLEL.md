# Wave 2 - three workstreams

This is the execution split for the rest of
[PLAN-1.0-completion.md](PLAN-1.0-completion.md). It follows the same rule as Wave 1: split by
**files and data ownership**, not by plan section number. Two chats must never edit the same
generated file at the same time.

## Wave 2 data status

Verified on 2026-10-28 after Parts 1 and 2:

| item | state |
|---|---|
| choice semantics | **2,286 fact-setting branch rows on 141 quests**, 111 dialogue-only rows, **0 contract branches** |
| DLC extraction | `q704*`/`q705*` all attach scenes; 118 branches on 10 Blood-and-Wine steps |
| Gwent index | 224 cards = 202 collectible main + 22 leaders; 216 sourced, 8 unknown source, 0 missable |
| targets | 2 targets: Blood-and-Wine both sisters **guided**, Baron wife cured **not guided yet** |
| schema | `docs/TARGET-SCHEMA.md`, `tools/endings.py`, 24 passing fixtures |
| route | 403 quests + 11 manual = 414 steps |
| coverage | 5 packs; phases 309, scenes 235, branch quests 141, cutoffs 6 |
| gates | `branchgen check`, `coverage check`, `cards check`, `endings check --release`, `regen --check` (11/11), `contradictions`, `cargo test` all pass |

Still absent, and owned by Part 3:

- the app-side target/settings/payload/UI integration
- packaging of the new data files
- a guided Baron target: its outcome is set by a phase script, not a scene choice, so there is no exact line to ship; it remains `not_guided_yet`
- card-level missable windows: **0 proven**; do not infer them from a Gwent quest failing
- any proven `exclusive.json` edge: the file is present and empty, which is honest

The `coverage.json` hash was re-recorded by `tools/regen.py --update` after Part 2 added the card
columns; `regen.py --check` now matches all 11 outputs.

One overlap is intentional and stays: the DLC probe's follow-up changed `tools/questindex.py` and
regenerated the route/derived outputs. That is the baseline for Part 1, not something to undo.

## Start order

```
Part 1  ─────────────────────────────┐
  coverage + branches                │
                                     ├─→ Part 2 target phase → final integration
Part 2  cards (can start now) ───────┘
                                     └─→ Part 3 (after Part 1 + target phase are frozen)
```

- **Part 1 and the card half of Part 2 can start together.** They do not touch the same files.
- **The target half of Part 2 waits for Part 1**, because a reviewed target needs a real branch
  source in `data/branches.json`.
- **Part 3 can start its settings scaffold after Part 1**, but its final UI work waits for the
  target and card payloads. It must not edit data or tools.
- The **integration owner** is the only chat that runs `tools/regen.py` after Part 2 adds targets,
  because `routegen` bakes `ending_relevant` from `data/endings.json`.

## Part 1 - data foundation: coverage and branch graph

**Owns**

- `tools/resources.py` (new, if a shared root provider is needed)
- `tools/branchgen.py` (new)
- `tools/coverage.py` (new)
- `tools/questindex.py`
- `tools/regen.py` and `tools/goldens.json`
- generated: `data/branches.json`, `data/coverage.json`, `tools/quest_index.json`,
  `data/route.json`, `data/derived.json`

**Does not touch**

- `data/endings.json`, `data/exclusive.json`, `data/gwent_cards.json`
- `src/`, `ui/`, `package.ps1`

**Work**

1. Make the DLC roots first-class. The probe proved REDkit already contains every DLC resource;
   the problem is attribution and one root set, not bundle extraction. Keep the existing
   DLC-scoped `quest_folder` rule, and make every reader that needs phases/scenes use the same
   roots. Do not add a second copy of the same resource from a bundle.
2. Generate `data/coverage.json` with one row per pack (`base`, `ep1`, `bob`, `other_dlc`,
   `gwent`): route quests, with phases, with scenes, with branches, with cards, with cutoffs. Counts
   must come from the index/route/cutoffs, not prose. Until Part 2 supplies cards, use `null` or
   `unknown` for `with_cards`; never invent a card count.
3. Generate `data/branches.json` from the index's scene choices. Include only fact-setting,
   non-one-shot rows. The shape must validate through `tools/endings.py`:
   `branches[step].choices[]` with `id`, `step`, `scene`, `choice_locid`, `sets`, `tests`,
   `one_shot: false`, and `source`. Keep `choice_text` in the generated file for the guided path,
   but never put it in the default payload.
4. Add both generators to `tools/regen.py` in dependency order, record the new hashes, and keep
   `base` route/derived nodes byte-identical except for intentional `ending_relevant` changes (none
   until Part 2 adds a guided target).

**Checks**

```
py tools/branchgen.py check
py tools/coverage.py check
py tools/regen.py --check
py tools/endings.py check
py tools/contradictions.py
cargo test
```

- every branch has a scene, a locId and at least one set fact; **no** one-shot row and **no**
  contract branch;
- every `branches.json` step exists in `data/route.json`;
- coverage counts sum to 403 route quests and 414 route steps; every pack has a row;
- DLC `q704*`/`q705*` keep their scene rows; base node count is unchanged;
- if attribution produces zero branches or zero DLC scenes, stop and report; do not create a target.

**Prompt**

```text
Read docs/PLAN-1.0-completion.md, docs/DLC-PROBE.md and docs/WAVE2-PARALLEL.md first.
Work only on Wave 2 Part 1: coverage and branch graph.

You own:
- tools/resources.py (new, only if needed)
- tools/branchgen.py (new)
- tools/coverage.py (new)
- tools/questindex.py
- tools/regen.py and tools/goldens.json
- generated data/branches.json, data/coverage.json, tools/quest_index.json,
  data/route.json, data/derived.json

Do not edit data/endings.json, data/exclusive.json, data/gwent_cards.json, src/, ui/ or package.ps1.
Do not add a target, choose a choice line, or edit the reviewed target files.

Use the measured DLC result: REDkit already has all 2229 DLC resources; fix attribution and shared
roots, not a second bundle copy. Generate coverage from the index/route/cutoffs. Generate branches
from fact-setting non-one-shot scene choices, with a source file, locId and set facts per branch.
Add both generators to regen.py, record the new hashes, and verify that base route/derived nodes are
unchanged.

Run the checks in docs/WAVE2-PARALLEL.md Part 1. Report exact counts before/after and every file
changed. If a DLC node or a branch has no source, stop and report it; never invent one.
```

## Part 2 - completion content: cards, targets, exclusivity

**Owns**

- `tools/cards.py` (new), `data/gwent_cards.json`
- `tools/endings.py`, `tools/test_endings.py` (only if a target rule needs extending)
- `data/endings.json`, `data/exclusive.json`
- the card columns of `data/coverage.json`, after Part 1 has landed

**Does not touch**

- `tools/questindex.py`, `tools/routegen.py`, `tools/regen.py`, `data/route.json`,
  `data/derived.json`, `data/branches.json`
- `src/`, `ui/`, `package.ps1`

**Work**

1. **Cards first (independent of Part 1).** Build `tools/cards.py` from the probe's five XML
   resources and the string database. Generate `data/gwent_cards.json` with the plan's shape:
   id, name, deck, source, optional missable window, evidence. Use the save's
   `SBCollectionCard`/`SBLeaderCollectionCard` indices for ownership; a missing block is
   `unknown`, never `not owned`. Do not infer ownership from a quest status. `Hemdal`, the two bear
   tokens and the other summon-only definitions are not collectible targets; record why.
2. **Targets after Part 1.** Add the Baron target from real `branches.json` facts and locIds. Add
   the Blood and Wine both-sisters target only from an extracted, reviewed B&W branch. If the exact
   line is not reviewed, keep the target `not_guided_yet` with a reason; do not paraphrase.
3. Add `data/exclusive.json` only for a proven/reviewed conflict: target-target, quest-quest,
   quest-target or card-target, with a file/locId/mechanism. No "these probably conflict".
4. Fill the card columns of `data/coverage.json` from the generated card index, but only after
   Part 1's coverage file exists. Do not regenerate the route.

**Checks**

```
py tools/cards.py check
py tools/endings.py check --release
py tools/test_endings.py -v
py tools/coverage.py check
```

- every card has a name and a source or explicit `unknown source`; every missable card names a step
  and mechanism; the count and denominator are reported, not promised;
- ownership is `owned` / `not owned` / `unknown`; a manual tick cannot be overwritten by a quest
  status; the parser is exercised on at least one save;
- at least one target is guided, every `requires`/`guidance` source resolves to the same branch,
  scene and locId, and the exact line equals the string database text;
- every target state is reachable/settled/impossible/unknown/not-guided on fixtures; no `locid: 0`;
- every `exclusive.json` edge names its evidence; a preset conflict is a warning, not a silent drop;
- no route or branch file changed.

**Prompt**

```text
Read docs/PLAN-1.0-completion.md, docs/TARGET-SCHEMA.md, docs/GWENT-PROBE.md and
docs/WAVE2-PARALLEL.md first. Work only on Wave 2 Part 2: cards, reviewed targets and exclusivity.

You own:
- tools/cards.py (new) and data/gwent_cards.json
- tools/endings.py and tools/test_endings.py only if a target rule needs extending
- data/endings.json, data/exclusive.json
- the card columns of data/coverage.json after Part 1 lands

Do not edit tools/questindex.py, tools/routegen.py, tools/regen.py, data/route.json,
data/derived.json, data/branches.json, src/, ui/ or package.ps1.

Start with the independent card index. Use the five card XML resources, the string database and the
save's SBCollectionCard/SBLeaderCollectionCard indices. Do not infer ownership from quests.
Summon-only definitions are not collectible targets. Then wait for Part 1's branches.json and add
the Baron target and the Blood and Wine both-sisters target only from real extracted branches.
If no exact line is reviewed, keep the target not_guided_yet; never paraphrase or invent it.
Add exclusive edges only with a file/locId/mechanism.

Run the checks in docs/WAVE2-PARALLEL.md Part 2. Report card and target counts, changed files, and
every unresolved source. Do not change the route or regenerate it; the integration owner does that.
```

## Part 3 - app: spoiler gate, planner payload, UI and package

**Owns**

- `src/main.rs`, `src/model.rs`
- `ui/app.js`, `ui/api.js`, `ui/index.html`, `ui/style.css`, `ui/mock/*`
- `package.ps1`, `packaging/README.md`, root `README.md` only for release notes

**Does not touch**

- any `tools/*.py`
- `data/branches.json`, `data/endings.json`, `data/exclusive.json`, `data/gwent_cards.json`,
  `data/coverage.json`, `data/route.json`, `data/derived.json`

**Work**

1. Add the settings keys and first-run card from `TARGET-SCHEMA.md`: `endings`, `guidance`,
   `setup_v1`; skip writes `[]`/`off`/`true`; `get_targets` is never called on startup; a stale id
   is dropped without a crash.
2. Add the target state evaluator and payload fields: `View.target`, `completion`, `coverage`,
   `Detail.branches`, `Detail.guidance`, card commands. Use the exact chip vocabulary:
   `GOAL` when guided, `ENDING CHOICE` for ending-relevant, `CHOICE` for a fact-setting branch;
   no chip for dialogue-only.
3. Build the UI order: `RUN` → `AT RISK NOW` → `STILL OBTAINABLE` → `IMPOSSIBLE / EXCLUDED` →
   `TRADEOFFS` → `GWENT CARDS` → `COVERAGE`, with the existing progress sections. Keep the 0.2.2
   cleanup: no technical evidence on cards.
4. Make the spoiler-free default a hard invariant in code and tests: no target id, label, choice
   text or instruction in `get_view`, `get_detail` or the DOM. Selecting a target reveals only that
   target's rows; clearing removes them immediately.
5. Package only after the data parts are merged. Verify the packaged exe reads its own `data/`, and
   run `--view` for spoiler-free, guided, settled, impossible, card-owned and card-unknown states.

**Checks**

```
cargo test
cargo build --release
# with a prepared --view payload for early, mid and epilogue saves:
# no target strings in default payload/DOM; only the selected target in guided mode
```

- `target === null` means no `guidance`, no target labels, no choice text anywhere;
- a settled target says settled; an impossible target says why; a not-guided target shows no line;
- completion arithmetic never counts known losses as available; cards unknown never become owned;
- no console errors; the existing top section, journal-over-tick rule and empty-top behaviour still
  pass;
- the packaged exe starts with the new data and does not depend on the checkout.

**Prompt**

```text
Read docs/PLAN-1.0-completion.md, docs/TARGET-SCHEMA.md and docs/WAVE2-PARALLEL.md first.
Work only on Wave 2 Part 3: the app, payload and UI.

You own:
- src/main.rs, src/model.rs
- ui/app.js, ui/api.js, ui/index.html, ui/style.css, ui/mock/*
- package.ps1, packaging/README.md, README.md release notes

Do not edit any tools/*.py or data/*.json. Read the generated branch, target, card and coverage
files; never rewrite them.

Implement the settings keys and first-run spoiler gate exactly as TARGET-SCHEMA.md specifies.
Add target state evaluation, View.target/completion/coverage, Detail.branches/guidance and card
commands. Use GOAL, ENDING CHOICE and CHOICE exactly; dialogue-only gets no chip. Build the RUN,
STILL OBTAINABLE, IMPOSSIBLE/EXCLUDED, TRADEOFFS, GWENT CARDS and COVERAGE sections without putting
technical evidence back on the cards.

Add tests for the empty top section, target-free payload, selected-target-only guidance, settled and
impossible states, and card ownership unknown. Drive ui/ against --view payloads for early, mid and
epilogue saves. Package only after the data parts are merged, and verify the packaged exe reads its
own data/. If a target or card file is missing, stop and report; do not invent data.
```

## Final integration (one chat, after Parts 1 and 2)

The integration owner:

1. runs `py tools/routegen.py build` after the guided target is added, so `ending_relevant` is
   attached from `data/endings.json`;
2. runs `py tools/regen.py --update` only for the intentional route/derived hash change, then
   `py tools/regen.py --check`;
3. runs `py tools/endings.py check --release`, `py tools/test_endings.py -v`,
   `py tools/contradictions.py`, `cargo test`;
4. runs the three-save `--view` check and the packaged-exe check;
5. packages 1.0.0 with `package.ps1` and confirms the new exe and `dist/` zip contain the new data.

Do not let two chats run `regen.py` or edit `data/route.json` at the same time.
