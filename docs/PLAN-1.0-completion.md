# Plan 1.0 - the completion planner: quests, endings and Gwent

**Revision 2026-10-28, written against the measured 0.2.2 build.** This is not another warning
pass. It turns the tracker from "what is at risk?" into "what can I still get in the run I chose?".

**Wave 1/2 data status (verified 2026-10-28):** the choice split, DLC extraction, Gwent index, branch
graph, coverage and target schema are in the tree. The generated branch graph now has **2,286
fact-setting branch rows on 141 quests**, with 111 dialogue-only rows and 0 contract branches. The
route has 403 quests + 11 manual steps. `data/coverage.json`, `data/branches.json`,
`data/gwent_cards.json` and `data/exclusive.json` exist; the Blood-and-Wine both-sisters target is
guided, while the Baron target is honestly `not_guided_yet` because its outcome is set by a phase
script, not a scene line. `regen.py --check` matches all 11 outputs. The remaining work is the
app-side target/settings/payload/UI integration and packaging; the execution split is
[WAVE2-PARALLEL.md](WAVE2-PARALLEL.md). The baseline table below records the pre-Wave-1 state and is
kept as the comparison point, not as the current measurement.

**Scope at a glance, measured on this install:**

| item | 0.2.2 reality |
|---|---|
| route | **414 steps** = 403 quests + 11 manual |
| reviewed cutoffs | **2 rules / 6 quest steps** (four Brothers in Arms quests, two statuettes) |
| "choice" flags | **79**, all from `singleUseChoice` dialogue rows, **0** from fact-setting branches; 21 are contracts |
| Hearts of Stone | **26 quests, 0 phase files, 0 scenes, 0 choice flags** |
| Blood and Wine | **83 quests, 0 phase files, 0 scenes, 0 choice flags** |
| Gwent | **11 route steps**, no card index, no card inventory |
| save corpus | **547 saves** |
| tests | **16 passing** |

The 403 route quests are **281 base + 122 DLC**: 26 Hearts of Stone, 83 Blood and Wine, and 13
free-DLC quests. The DLC split matters because the base game has phases for 225 of its 281 route
quests and scenes for 186; every DLC pack has 0 of either in the REDkit export.

The important sentence: the app is silent about most missed content because it has not modelled
it, not because there is nothing to lose. 1.0 has to make that distinction visible.

## 0. Design intention

**The app answers two questions: "what can I still get?" and "what do I do next for the run I
chose?"** It is still not a wiki and not a full walkthrough. It becomes a planner.

| source | what it is allowed to decide |
|---|---|
| the game's own files | every rule: quests, phases, scenes, facts, journal states, switches, endings and card definitions |
| your save | every fact about where you are: statuses, objectives, facts set, inventory if readable |
| the user's chosen target | which of the possible endings or completion goals the run is aiming at |
| the app itself | order, coverage, and the difference between "done", "still possible" and "no longer possible" |

The rules, in the order they matter:

1. **No second-hand knowledge.** Every generated claim has a file/locId/save source. The wiki JSON
   stays unused. The one new exception is explicit: an **ending target** is a reviewed user goal,
   not a game fact. It is labelled `reviewed`, names its evidence, and never pretends the game
   called it "best".
2. **Only what changes a decision.** A warning disappears once the save settles it. A target step
   disappears once it is behind you, and says whether the target is still reachable.
3. **Silence is valid only where the data is complete.** On a pack or quest where phases/scenes or
   cards are not modelled, the app must say **not modelled**. It may not stay silent and let the
   player infer safety. This is a new rule created by the DLC gap.
4. **Your word is not evidence.** Ticks remain bookkeeping. The journal and a fired cutoff win;
   where they disagree, the app shows the disagreement.
5. **Spoilers are opt-in, and the default is silent about them.** No ending names, choice text,
   recommended options or outcome summaries are shown until the user explicitly chooses an ending
   goal. The default gets one vague marker: "a choice here affects an ending", never which one.
6. **Guided mode is scoped, not a walkthrough.** If the user chooses a goal, the app may show the
   exact line to say at the steps that goal requires, and nothing about other goals or outcomes.
   Every line must come from a scene choice locId; no paraphrased or guessed line ships.
7. **Traceable, not chatty.** The card says what to do; the detail pane opens the scene, locId,
   fact, phase block and save state behind it.
8. **One column of urgency.** At risk now, then still obtainable, then impossible/excluded,
   then progress.
9. **Universal by construction.** Data is keyed on quests, branches, cards and targets, not on
   anyone's save. The 547 saves are a test corpus, never the definition of a claim.

The old rule "no choice text" still applies to the **default** screen. The opt-in target mode is the
deliberate exception, because the user asked to be told what to say for the ending they chose.

## 1. What the app does today

- The route is every playable journal quest plus 11 manual bookkeeping steps.
- The top section only knows two proof-backed rules; the four Brothers in Arms quests and the two
  statuettes. It correctly says the statuettes are **missable until the end of Final Preparations**
  and that Haunted House has no cutoff.
- The `choice` tag is currently wrong for the purpose. `tools/questindex.py` accepts any
  `singleUseChoice` as a choice, so all 79 flags are one-shot dialogue rows; none is a fact-setting
  branch. That is why 21 contracts claim "a choice changes the outcome".
- DLC quests are journal-only. REDkit `r4data` has no Hearts of Stone or Blood and Wine phase/scene
  folders, so choice and ending analysis cannot run there yet.
- Gwent is a quest list: six unique-card quests, *Collect 'Em All*, *High Stakes*, *Get Junior*, the
  Blood and Wine tournament and one manual Vegelbud step. There is no card database, no source per
  card and no inventory read.
- The only setup today is the **my game** panel: flags, folders, level. There is no ending goal, no
  spoiler mode, no completion count and no card ledger.

## 2. Target behaviour

### 2.1 Setup and the spoiler gate

On first launch after 1.0, show a non-blocking setup card:

> **Optional: choose an ending goal.** If you want the tracker to guide you, it can ask which
> endings you are aiming for. This reveals ending names and, later, exact choice lines. You can skip
> this and stay spoiler-free.

Buttons:

- **Skip - stay spoiler-free** (default; writes `endings: []`, `guidance: "off"`, `setup_v1: true`).
- **Choose a goal (spoilers)** - only this click reveals the target list.

The target list is grouped by pack (`Main game`, `Hearts of Stone`, `Blood and Wine`, `Gwent`) and by
preset (`Recommended endings`, `All still possible quests`, `All Gwent cards`). A target selection
writes to `settings.json`; it does not alter the route or any save.

**My game** gains one row: `Ending goal: none` or the selected target labels, with **change** and
**clear**. Clearing returns the UI to spoiler-free immediately and removes every target label from
the payload.

### 2.2 Spoiler-free mode (default)

- A quest containing an ending-critical branch gets one vague chip: **`ENDING CHOICE`** with the
  tooltip "a choice here affects an ending". No target name, no choice text, no option list.
- A quest with a fact-setting non-ending branch gets **`CHOICE`** / "a choice changes later
  content". A one-shot dialogue row gets **no chip**; it is not an outcome branch.
- The detail pane shows the existing game-text objectives and technical details, never choice lines.
- The target list is not rendered, not hidden in the DOM, and not present in `get_view` or
  `get_detail`. A test asserts this.
- The coverage panel is visible: `Blood and Wine choices: not modelled` until the DLC extraction
  step passes. This is the honest replacement for silence.

### 2.3 Guided mode (only after opt-in)

For each selected target:

- The card gets a `GOAL` chip. Clicking it opens the detail pane at the target section.
- On a step the target requires, the detail pane shows:

  > **YOUR GOAL - Blood and Wine: both sisters live**
  > **At this step:** say "..." (the exact scene line).
  > **Why:** the line sets `<fact>`; the target needs it.

- The exact line is only the selected target's line. The other option, other targets and the
  outcome are not shown.
- If the step is already behind the save: `Already settled in this save` plus what the save says.
  Do not tell the player to go back.
- If the target is no longer reachable: `This goal is no longer reachable` with the failed fact,
  quest or cutoff that settled it. Changing target is allowed; the past is not rewritten.
- On the Blood and Wine target, the app must not guess. If the scene line cannot be extracted, the
  target state is `not guided yet`; no invented dialogue is shown.

**Worked example - "both sisters live" in Blood and Wine.** The target is a reviewed entry in
`endings.json`. After extraction, its guidance points at the relevant Blood and Wine scene choice
locIds and the exact line to pick. The card for that quest says only `GOAL`; the detail says
`YOUR GOAL - both sisters live` and the exact line. Until the extracted scene exists, the target is
visible only as `not guided yet`, never as a guessed instruction.

### 2.4 The completion planner

The main list becomes:

1. **RUN** - the selected target set, or `SPOILER-FREE`.
2. **AT RISK NOW** - the existing top section, unchanged in priority.
3. **STILL OBTAINABLE** - quests and cards still reachable for the target, in route order.
4. **IMPOSSIBLE / EXCLUDED** - already failed/lost, or excluded by a choice/target; each names the
   reason.
5. **TRADEOFFS** - mutually exclusive quests/targets; "doing X closes Y".
6. **PROGRESS** - the existing sections.

The header shows two numbers, never a misleading single percentage:

- `Quests: 214 done / 37 still possible / 3 at risk / 149 not in this run`
- `Cards: 87 owned / 12 still possible / 4 at risk / 63 not in this run`

The denominator is not always 403. Some content is mutually exclusive. The app shows
`max achievable for this run`, not "100% of every branch".

**"All quests"** is a target, but it resolves to the maximum consistent set, not a promise that
every mutually exclusive branch fits in one save.

**"Best endings"** is a preset of named targets, not a hidden ranking. The preset is called
`Recommended endings` in the UI and is marked `reviewed`; the user can change it. A preset conflict
is shown before it is applied.

### 2.5 Coverage panel

A small, collapsible section under **RUN**:

| pack | quests | phases | scenes | branches | cards | cutoffs |
|---|---:|---:|---:|---:|---:|---:|
| Base game | 281 route quests (283 journals, 2 debug excluded) | 225 | 186 | 0 proven | not measured | 6 warned steps |
| Hearts of Stone | 26 | 0 | 0 | not modelled | not measured | none |
| Blood and Wine | 83 | 0 | 0 | not modelled | not measured | none |
| Free DLC (`dlc3/7/10/12/15`) | 13 | 0 | 0 | not modelled | not measured | none |

These are generated counts from `coverage.json`, not prose. The panel exists so "no warning" cannot
be mistaken for "nothing to lose".

### 2.6 Cards

A **GWENT CARDS** section lists every card with:

- name and deck (from the game's own string database),
- source (quest, opponent, vendor, random drop, or "unknown source" if the files do not say),
- missable window, when one is proven,
- owned / not owned / unknown.

If the save exposes card item GUIDs, ownership is automatic. If it does not, the section falls back
to manual ticks and says so; it never claims a card is owned because a quest is done.

## 3. Data schema

New inputs are split into **generated** files (never hand-edited) and **reviewed** files (hand
decisions with sources). `tools/regen.py` owns every generated file.

### 3.1 `data/branches.json` (generated)

The branch graph extracted from scenes and phases. It replaces `has_choice` as the source of the
card tags.

```json
{
  "version": 1,
  "note": "scene choices that set or test facts; generated from CR2W; choice text is gated",
  "branches": {
    "q105evilspirit": {
      "step": "q105evilspirit",
      "choices": [
        {
          "id": "q105_help_spirit",
          "scene": "quests\\part_1\\quest_files\\q105_witches\\scenes\\q105_...w2scene",
          "choice_locid": 123456,
          "choice_text": "...",
          "sets": ["q105_help_spirit"],
          "tests": [],
          "one_shot": false,
          "source": {"kind": "scene_choice", "file": "quests\\...", "locid": 123456}
        }
      ]
    }
  },
  "consequences": [
    {
      "fact": "q105_help_spirit",
      "kind": "quest_branch",
      "affects": ["family", "q105evilspirit"],
      "evidence": [{"kind": "file", "value": "quests\\...w2phase", "block": 780}]
    }
  ]
}
```

Rules for this file:

- A `branch` is a choice whose scene section contains a **fact-setting** block. `singleUseChoice`
  alone is **not** a branch; it is `dialogue_choice`.
- `ending_relevant` is not inferred here. It is attached by `endings.json` review; a branch becomes
  ending-relevant only when a reviewed target names it.
- `choice_text` is shipped only for a selected target and only through the guidance path. The
  default view never includes it. The text is still stored so the tool can prove what it shows.

### 3.2 `data/endings.json` (reviewed)

Targets are user goals, not game facts. Every target names its evidence and its review date.

```json
{
  "version": 1,
  "note": "reviewed targets; the game files decide facts, the reviewer decides which target is wanted",
  "targets": {
    "bw_both_sisters": {
      "label": "Blood and Wine: both sisters live",
      "pack": "bw",
      "spoiler": true,
      "reviewed": "2026-10-28",
      "requires": [
        {"fact": "<fact from the extracted B&W scene>", "value": true,
         "source": {"kind": "scene_choice", "file": "quests\\...", "locid": 123456}}
      ],
      "guidance": [
        {
          "step": "q704...",
          "branch": "<branch id from branches.json>",
          "instruction": "<the exact line the scene offers>",
          "source": {"kind": "scene_choice", "file": "quests\\...", "locid": 123456}
        }
      ]
    }
  },
  "presets": {
    "recommended": {
      "label": "Recommended endings",
      "targets": ["ciri_witcher", "bw_both_sisters", "baron_wife_cured"],
      "reviewed": "2026-10-28"
    }
  }
}
```

Rules:

- No placeholder locId or paraphrased line ships. The `endings.py check` fails on `locid: 0` or a
  missing source.
- `requires` facts must resolve in `branches.json` or `quest_index.json`.
- A target can be marked `not_guided_yet`; that is a valid state, not a failure to hide.
- The label `best` is not used. The preset is `Recommended endings`, and the detail says it is a
  reviewed preference.
- A target that cannot be evaluated from the save is `unknown`, never `reachable`.

### 3.3 `data/exclusive.json` (reviewed)

The missing relation for a real completion count.

```json
{
  "version": 1,
  "edges": [
    {
      "a": "target:ciri_witcher",
      "b": "target:ciri_empress",
      "kind": "target",
      "reason": "the same end-game choice selects one epilogue",
      "evidence": [{"kind": "file", "value": "quests\\...w2phase", "block": 123}]
    }
  ]
}
```

Edge kinds: `target`, `quest`, `quest-target`, `card-target`. Only proven/reviewed edges are
shipped. The planner uses these edges to compute `excluded` and `max_achievable`.

### 3.4 `data/gwent_cards.json` (generated from card definitions plus review)

```json
{
  "version": 1,
  "cards": [
    {
      "id": "card_...",
      "name": "Zoltan Chivay",
      "deck": "Scoia'tael",
      "source": {
        "kind": "quest",
        "step": "cgoldfriends",
        "text": "Win a unique card from ..."
      },
      "missable": {
        "step": "cgoldfriends",
        "event": "the quest ends",
        "mechanism": "journal"
      },
      "evidence": [{"kind": "locid", "value": 123456}]
    }
  ]
}
```

Rules:

- Every card has a name from the string DB and at least one source row. A card with no source is
  shown as `unknown source`, not omitted.
- A missable card must name a step and mechanism; no prose-only warnings.
- Ownership is separate from the card definition: `get_cards` returns `owned | not owned |
  unknown` from the save or from `progress.json` manual ticks.
- The card file is generated only after the definition probe succeeds. If no card resource exists,
  the feature is not shipped as if it worked.

### 3.5 `data/coverage.json` (generated)

Per pack:

```json
{
  "packs": {
    "base": {"quests": 281, "with_phases": 225, "with_scenes": 186, "with_branches": 0, "with_cards": 0, "with_cutoffs": 6},
    "ep1":  {"quests": 26,  "with_phases": 0,   "with_scenes": 0,   "with_branches": 0, "with_cards": 0, "with_cutoffs": 0},
    "bob":  {"quests": 83,  "with_phases": 0,   "with_scenes": 0,   "with_branches": 0, "with_cards": 0, "with_cutoffs": 0},
    "other_dlc": {"quests": 13, "with_phases": 0, "with_scenes": 0, "with_branches": 0, "with_cards": 0, "with_cutoffs": 0}
  }
}
```

The UI reads this; a hard-coded "not modelled" sentence is not allowed.

### 3.6 Backend contract additions

`View` gains:

```json
{
  "target": null | {
    "ids": ["bw_both_sisters"],
    "labels": ["Blood and Wine: both sisters live"],
    "guidance": "on"
  },
  "completion": {
    "quests": {"done": 214, "available": 37, "at_risk": 3, "lost": 2, "excluded": 149, "total": 403, "max_achievable": 254},
    "cards":  {"owned": 87, "available": 12, "at_risk": 4, "excluded": 63, "unknown": 0, "total": 166}
  },
  "coverage": {"packs": {"bob": {"with_phases": 0, "with_scenes": 0}}}
}
```

`Detail` gains:

```json
{
  "branches": [
    {"id": "q105_help_spirit", "ending_relevant": true, "label": "a choice here affects an ending"}
  ],
  "guidance": null | {
    "target": "bw_both_sisters",
    "label": "Blood and Wine: both sisters live",
    "instruction": "<the exact line>",
    "settled": false,
    "source": {"kind": "scene_choice", "file": "quests\\...", "locid": 123456}
  }
}
```

Commands:

- `set_target(ids: string[] | [])` - empty clears the goal and returns to spoiler-free.
- `set_guidance(on: boolean)` - only meaningful with a target.
- `get_cards() -> Card[]` and `set_card(id, owned)` for the manual fallback.
- `get_coverage()` or the `coverage` field on `View`.

Invariants, tested at the payload level:

- `target === null` => no `guidance`, no target labels, no `choice_text`, no ending names anywhere
  in `get_view` or `get_detail`.
- `target !== null` => `guidance` contains only the selected target's rows; other targets and
  options are absent.
- The default view contains no `choices` array, no wiki prose and no source URLs.

### 3.7 Storage

`settings.json`:

```json
{
  "game_dir": "...",
  "saves_dir": "...",
  "endings": [],
  "guidance": "off",
  "setup_v1": true
}
```

`progress.json` keeps `ticks`, `level`, `flags`; if card ownership is manual, add
`"cards": ["card_id", ...]`. One profile remains one save/run; multiple runs are an explicit later
feature, not silently mixed.

## 4. Work order

Each step ends with a check. Do not start the UI for a feature whose data probe failed.

### 0. Freeze the target definition and the truth baseline

Decide the first target presets (section 7), the one-run rule, and the card-ownership fallback.
Add `coverage.json` with the measured 0.2.2 zeros before changing behaviour.

Check:

- coverage counts match the current files: 0 DLC phases/scenes, 6 warned steps, 79 weak choice
  flags;
- `cargo test` still 16/16;
- no user-facing change yet.

### 1. Fix the choice semantics

In `tools/questindex.py`:

- rename the current meaning: `has_branch` = a scene section sets a fact; `has_dialogue_choice` =
  a one-shot dialogue row; remove `has_choice` from the route/derived output.
- fix the `section_sets` probe if it is returning zero for a known fact-setting scene. Use a known
  branch (for example the Whispering Hillock spirit path) as the fixture.
- `routegen` carries `branch` and `ending_relevant` (ending relevance attached from `endings.json`,
  not from the one-shot heuristic).

Check:

- the 21 contracts have **zero** branch tags;
- every `branch` has a scene source and at least one fact;
- `choice` no longer appears in `route.json` or `derived.json`; the UI's old label is gone;
- `py tools/regen.py` is byte-identical after the intentional update, and
  `py tools/contradictions.py` remains 0 contradicted / 0 disputed;
- `cargo test` has a regression test that a one-shot dialogue row is not an outcome branch.

### 2. Add the DLC resource provider

Add `tools/resources.py` (or extend `bundles.py`) that:

- reads POTATO70 bundles from the game's `content` and `dlc` folders,
- exposes virtual resource paths for `.w2phase`, `.w2scene` and journal resources,
- overlays the DLC resources on the base REDkit data,
- never writes extracted game files into `data/` or the package.

Refactor `questindex.py`, `cutoffs.py` and `derive.py` to read through the provider instead of
`Path.read_bytes()`.

Check:

- the provider reports the number of DLC phase and scene resources found; record it in
  `coverage.json`;
- at least one Blood and Wine quest (`q704...`/`q705...`) has a real scene row after extraction;
- the base-game outputs are byte-identical except for the known counts;
- if extraction returns zero, the step fails loudly and the DLC remains `not modelled`; no target
  is invented.

### 3. Build the base branch graph and the first target

Generate `branches.json`; add the first reviewed target from content that already has phase facts.
The Baron path is the recommended first vertical slice because `q105_help_spirit`,
`q105_evil_spirit_released`, `q105_evil_spirit_destroyed`, `q105_kids_gone` and
`q105_anna_with_kid` already exist in the base-game files.

Add `endings.json` for that target, with `requires` facts and guidance locIds. Add
`exclusive.json` only where a branch is proven to close another target.

Check:

- `py tools/branchgen.py check` - every branch has a scene/source/fact, no one-shot-only branch;
- `py tools/endings.py check` - every target requires and guidance row resolves; no `locid: 0`;
- the target evaluates to `reachable | settled | impossible | unknown` on the corpus, and a save
  on the other side of the choice evaluates to the other state;
- the exact line shown is the scene's line, not a paraphrase;
- `regen` and `contradictions` pass.

### 4. Add the target schema, setup panel and spoiler gate

Add `endings.json` validation, settings keys, `set_target`/`set_guidance` and the first-run card.
Build the target list only after the user clicks **Choose a goal (spoilers)**.

Check:

- first launch writes `endings: []`, `guidance: "off"`, `setup_v1: true` when skipped;
- default `get_view`/`get_detail` JSON contains no target label, ending name, choice text or
  guidance; a test greps the serialized payload for the selected target's label and line;
- after selecting a target, only that target's label and guidance appear;
- clearing the target restores the spoiler-free payload;
- changing target keeps the old save state and reports settled steps honestly.

### 5. Add the Blood and Wine target and its exact guidance

Using the extracted scenes, add **Blood and Wine: both sisters live** as the first DLC target. Fill
`requires` and `guidance` from the actual scene choice locIds. Add the target's `exclusive` edges
and its `coverage` rows.

Check:

- every guidance line has a scene file and locId that resolves through the string database;
- the target has at least one reachable save and one impossible/settled fixture, or is explicitly
  `unknown` with a reason;
- the detail pane shows the exact line for the selected target and no line for the other target;
- the default UI for the same quest shows only `ENDING CHOICE`, not the line;
- no DLC target is shipped from guessed text.

### 6. Add the Gwent card index and ownership

Probe the game bundles for card definitions and the string database for names. Generate
`gwent_cards.json`; add `get_cards` and the manual fallback. Try reading card item GUIDs from the
save inventory before accepting manual-only.

Check:

- the card count matches the game's card database (report the number; do not promise a count
  before the probe);
- every card has a name and source, or an explicit `unknown source`;
- every missable card names a step and mechanism;
- ownership is `owned`/`not owned`/`unknown`; a manual tick cannot be overwritten by a quest status;
- *Collect 'Em All* and the Blood and Wine tournament appear as card-relevant quests, not as a
  substitute for the card list;
- the all-cards target can be evaluated and never says `100%` while `unknown > 0`.

### 7. Add exclusivity and the completion planner

Add `exclusive.json` rows where a choice or target really closes another. Compute
`completion.quests` and `completion.cards` from the save, target and graph. Add the tradeoff list.

Check:

- a target pair with a known conflict cannot both be selected without a visible tradeoff;
- `max_achievable` is lower than `total` when exclusive content exists; a test asserts the app
  never labels "every quest" as achievable if an exclusive edge exists;
- `done + available + at_risk + lost + excluded <= total`, with the exact arithmetic checked;
- a save with a failed quest moves it to `lost`, not `available`;
- an unmodelled pack is `excluded`/`unknown` with a coverage reason, not silently missing.

### 8. Build the UI

- First-run setup card with the spoiler-free default.
- **RUN** header with target labels only after opt-in; `SPOILER-FREE` otherwise.
- `ENDING CHOICE` chip in default mode; `GOAL` chip in guided mode.
- Detail pane: `YOUR GOAL` section, exact line, source link, settled/impossible state.
- `STILL OBTAINABLE`, `IMPOSSIBLE / EXCLUDED`, `TRADEOFFS`, `GWENT CARDS`, `COVERAGE`.
- Keep the existing top section and detail technical panel; do not regress the 0.2.2 cleanup.

Check:

- render three saves (early, mid, epilogue) with `--view` and the browser mock;
- default DOM contains no target label, no exact line, no other-target text;
- guided DOM contains the selected target's line on the matching step and nowhere else;
- a target that is already settled shows "settled", not a warning to go back;
- no console errors and no missing source links.

### 9. Verification and package

Run the full gate:

```
py tools/questindex.py build --all
py tools/contradictions.py
py tools/regen.py --check
cargo test
```

Then package 1.0.0 with `package.ps1`, verify the packaged exe against its own `data/`, and run
`--view` on a save for each state: spoiler-free, target selected, target settled, target
impossible, card-owned and card-unknown.

## 5. Acceptance checks

### Data and provenance

- [ ] `branches.json`: every branch has a scene source and a fact; **0** contracts carry a branch.
- [ ] `endings.json`: every target has `reviewed`, at least one `requires` fact and at least one
  guidance source; **0** `locid: 0`; no target with guessed text.
- [ ] `gwent_cards.json`: every card has a name and a source or `unknown source`; every missable
  card has a step and mechanism.
- [ ] `coverage.json`: every pack and every route step has a coverage row; no DLC pack is reported
  as modelled before its extraction check passes.
- [ ] `exclusive.json`: every edge names a mechanism and a source; no unsourced "these conflict".
- [ ] `py tools/regen.py --check` reports all outputs matching.
- [ ] `py tools/contradictions.py` reports 0 contradicted claims and 0 disputed prerequisites.

### Spoiler gate

- [ ] Default `get_view` and `get_detail` contain no target labels, ending names, choice text or
  guidance. The test serializes the payload and fails on any selected target's label or line.
- [ ] The first-run skip path writes an empty target set and does not show the target list.
- [ ] Selecting a target shows only that target's label and guidance; clearing it restores the
  default payload.
- [ ] The `ENDING CHOICE` chip is vague and exists only for reviewed ending-critical branches.

### Behaviour

- [ ] B&W both-sisters target: the relevant step shows the exact scene line; the default step does
  not; changing the target hides the old line.
- [ ] A settled target says settled; an impossible target says why; an unmodelled target says
  `not guided yet`.
- [ ] `max_achievable` never exceeds `total`; exclusive content is counted and visible.
- [ ] Cards without readable ownership are `unknown`, not silently `not owned` or `owned`.
- [ ] Existing 0.2.2 behaviours survive: statuettes missable until Battle Preparations, Haunted
  House no cutoff, CHECK NOW vs LOST, journal over tick.

### UI

- [ ] Browser rendering for early, mid and epilogue saves; no console errors.
- [ ] The default UI has no spoiler strings in the DOM.
- [ ] The guided detail shows source file/locId behind the line.
- [ ] Coverage panel shows the DLC zeros before extraction and the real counts after.

## 6. Limits and non-goals

- **"Best" is not a game fact.** The app ships reviewed targets and calls the preset
  `Recommended endings`; it never claims the game ranks outcomes.
- **All quests in one run may be impossible.** Some content is mutually exclusive; the planner
  shows the maximum achievable set for the chosen targets and the tradeoffs. "100%" means
  "everything still possible in this run", not "every branch ever written".
- **No full walkthrough.** Guided mode shows only the steps that a selected target requires. It
  does not narrate the quest or list every dialogue option.
- **No wiki text.** The existing wiki JSON stays frozen and unused. Target labels and guidance are
  reviewed over game locIds, with their sources named.
- **Card ownership may remain manual.** If the save does not expose card item GUIDs, the app says
  so and uses ticks; it does not infer ownership from quest completion.
- **DLC coverage may fail.** If bundle extraction cannot read the DLC phases/scenes, those packs
  stay `not modelled` and their ending targets are not shipped. Guessing is not an option.
- **One profile is one run.** Multiple concurrent runs and cross-run planning are later work; the
  data model keeps target IDs so they can be added without rewriting the route.

## 7. Decisions needed before implementation

1. **Target presets.** Which named outcomes make the first `Recommended endings` set? Suggested
   starting set: Ciri witcher, Baron's wife cured, Blood and Wine both sisters. Add or remove before
   the targets are written.
2. **One run or several?** When "all quests" and the chosen ending conflict, should the planner
   optimise for the ending, for the most unique quests, or ask the user to choose? The default
   recommendation is: ending first, then maximum quests, and show the tradeoff.
3. **Card ownership fallback.** If the save cannot expose card GUIDs, is a manual checklist
   acceptable, or should the card feature wait for an inventory reader?
4. **Guidance scope.** Should guided mode show the exact line only, or also a one-sentence reason
   naming the fact? The plan assumes exact line + fact name, never the outcome.
5. **Pack scope.** Is Hearts of Stone included in the first target pass, or only Blood and Wine and
   the main game? The resource provider covers both; the review effort is the constraint.

## 8. Recommended first slice

Do **steps 1, 2 and 3** before any target UI:

- fix the 79 false choice flags;
- prove DLC phase/scene extraction;
- build one Baron target from facts that already exist.

That gives a truthful app, a working target schema on real game data, and the answer to whether
Blood and Wine guidance is feasible. If step 2 fails, stop and label DLC journal-only; do not
build a B&W planner on guesses.

