# Target schema and setup specification (1.0)

**Status: schema and checker implemented by `tools/endings.py`; app integration is Wave 2.** This
document freezes the shape of `data/endings.json`, the target keys in `settings.json`, the first-run
flow, the target part of the payload, and the vocabulary for target states and chips. The checker
and its fixtures are `tools/endings.py` and `tools/test_endings.py`; this document itself adds no
game data.

It is written against the retired 1.0 completion plan (its record is [RELEASE-1.0.0.md](archive/RELEASE-1.0.0.md)), sections 2.1-2.3, 3.2, 3.6
and 3.7. Where the plan sketches a shape rather than fixing it, this document makes the decision and
records it in section 1.

**No real Blood and Wine line appears here.** The extraction probe has not produced one. The
"both sisters live" material in section 7 is a fixture: invented fact, branch, step, file, locId and
instruction, marked `FIXTURE ONLY` on every user-facing string. It is a shape, not evidence.

Normative words: **MUST**, **MUST NOT**, **SHOULD**.

---

## 1. Decisions this document makes

These are the places where the plan is a sketch, ambiguous, or internally inconsistent. Later
sections apply them.

1. **Pack codes match `coverage.json`.** The valid values are `base`, `ep1`, `bob`, `other_dlc` and
   `gwent`. The plan's target example writes `"pack": "bw"`; `bw` is not a data value. Blood and
   Wine is `bob`, the same code the coverage panel uses.
2. **`Detail.guidance` is an array, not one object.** The plan's single-object sketch is the element
   shape. A user may select several targets, and more than one selected target may require the same
   step. One element per selected target keeps "only its own guidance" checkable without making the
   type depend on how many targets happen to apply.
3. **Target states live under `View.target.states`.** The plan's `View.target` only listed `ids`,
   `labels` and `guidance`; those cannot say whether a target is reachable, settled, impossible,
   unknown or not guided yet. `states` is the payload home for section 6.
4. **`get_targets()` is a separate command.** The target list MUST NOT be present in `get_view` or
   `get_detail`, and MUST NOT sit hidden in the default DOM. The picker fetches it only after the
   user clicks **Choose a goal (spoilers)**. Startup in spoiler-free mode never calls it.
5. **`not_guided_yet` is a stored target state, not a missing field.** A target with
   `guidance_status: "not_guided_yet"` has no `requires` and no `guidance`; it carries a
   `guidance_reason` instead. This prevents a placeholder fact or a guessed line from looking like
   data while the extraction probe is unfinished.
6. **`requires[].value` is `true` in v1.** The save reader exposes facts that are set, not a
   three-valued fact database. "Fact is false" and "fact has not been reached" are not
   distinguishable. A target that needs an outcome must name a positive fact that the winning
   branch sets. `false` is rejected by the checker rather than given a false meaning.
7. **`endings.json` presets are explicit target-id sets only.** `Recommended endings` is such a
   preset. `All still possible quests` and `All Gwent cards` are completion-planner selectors, not
   ending targets: they have no `requires`/`guidance` rows and are defined with the planner, not
   given fake ending rows here.
8. **Target state is computed, never persisted.** `settings.json` stores target ids. Reachable,
   settled, impossible, unknown and not-guided are recomputed from the current save and the reviewed
   files on every `get_view`; a stale state cannot survive a save reload or a target change.
9. **Selecting a target turns guidance on.** The user opted into exact lines by opening the spoiler
   list and choosing a goal. A `Guidance: on/off` control in **My game** can turn the lines off
   while keeping the labels. Clearing the target forces guidance off.
10. **`setup_v1` is set on every exit from the first-run card.** Skip, close and apply all write
    `setup_v1: true`. The card is a one-time invitation, not a nag; **My game** keeps the entry
    point.

---

## 2. `data/endings.json`

Reviewed file, not generated. `tools/regen.py` MUST NOT rewrite it. It is validated by
`py tools/endings.py check` (section 2.7).

### 2.1 Top level

```json
{
  "version": 1,
  "note": "reviewed targets; the game files decide facts, the reviewer decides which target is wanted",
  "targets": {},
  "presets": {}
}
```

| field | type | required | rule |
|---|---|---|---|
| `version` | integer | yes | exactly `1` |
| `note` | string | yes | what the file is and who reviews it; no game claim |
| `targets` | object | yes | keys are target ids; values are target objects (2.2) |
| `presets` | object | yes | keys are preset ids; values are preset objects (2.5) |

Unknown top-level keys are validation errors. `targets` may be empty only before the first target is
reviewed; when it is empty, the first-run card MUST offer only **Skip**, and `get_targets()` returns
an empty list. A 1.0 release build MUST contain at least one target and `presets.recommended`.

### 2.2 Target object

```json
{
  "label": "string, user-facing and spoiler-bearing",
  "pack": "base",
  "spoiler": true,
  "reviewed": "2026-10-28",
  "review_note": "why this target is a reviewed goal",
  "outcome": "ciri_witcher",
  "requires": [],
  "guidance_status": "guided",
  "guidance": []
}
```

| field | type | required | rule |
|---|---|---|---|
| `label` | string | yes | complete user-facing label, 1-80 characters, no trailing period; the picker may group it under its pack, but the label stands alone |
| `pack` | enum | yes | `base`, `ep1`, `bob`, `other_dlc` or `gwent` (1.1) |
| `spoiler` | boolean | yes | MUST be `true` in v1; `false` is rejected because there is no non-spoiler target path |
| `reviewed` | string | yes | `YYYY-MM-DD`, a real calendar date; the date the `requires`/`guidance` rows were last reviewed |
| `review_note` | string | no | why this target is offered; must not claim the game ranks it |
| `outcome` | string | no | id in `data/outcomes.json`; when present the terminal facts and guidance live there and `requires`/`guidance` must be empty |
| `requires` | array | yes | requirement rows, 2.3; empty for `not_guided_yet` and for an outcome-backed target |
| `guidance_status` | enum | yes | `guided` or `not_guided_yet` |
| `guidance_reason` | string | conditional | required when `guidance_status` is `not_guided_yet`; forbidden otherwise |
| `guidance` | array | yes | guidance rows, 2.4; empty only for `not_guided_yet` |

Target ids:

- Keys of `targets`, lowercase snake case, `^[a-z][a-z0-9_]{2,63}$`.
- An id is stable. Changing what a target means requires a new id, because `settings.json` stores
  ids and users may have the old one.
- An id MUST NOT equal a pack code (`base`, `ep1`, `bob`, `other_dlc`, `gwent`) or a route step id.
  This keeps the default spoiler scan from colliding with ordinary payload keys and step ids.
- The prefix `fixture_` is reserved for examples and tests. A shipped `data/endings.json` MUST NOT
  contain a `fixture_` id; `endings.py check` rejects it.
- Target labels MUST be unique. Two ids with the same label are a validation error.

A target is **guided** when `guidance_status` is `guided`. A guided direct target MUST have at least
one `requires` row and at least one `guidance` row. An **outcome-backed** target names `outcome`
and keeps both arrays empty: the rows live once, in `data/outcomes.json`, where `outcomecheck.py`
validates the terminal fact, the exact line or journal objective, and the journal description. Its
`pack` and `guidance_status` MUST match the outcome. A `not_guided_yet` target MUST have
`requires: []`, `guidance: []` and a non-empty `guidance_reason`; it MUST NOT carry placeholder
facts or placeholder text. That is the only way to ship a label whose evidence has not been
extracted yet.

Review date scope: a target's `reviewed` date covers every `requires` and `guidance` row in that
target. There is no per-row reviewed field. Any change to a label, requirement or guidance row MUST
update the target's `reviewed` date. A preset's `reviewed` date covers its target list.

### 2.3 `requires` rows

A requirement says: this fact must be set in the save for the target to be settled. In the
outcome-backed form in `data/outcomes.json` the same shape is used, with two differences: `value`
may be `false` for a negative terminal fact (the source step must finish before absence proves the
branch), and a `journal_outcome` row names the exact journal description instead of a scene line.

```json
{
  "fact": "q105_help_spirit",
  "value": true,
  "source": {
    "kind": "scene_choice",
    "step": "q105evilspirit",
    "branch": "q105_help_spirit",
    "file": "quests\\part_1\\q105_witches\\scenes\\q105_...w2scene",
    "locid": 123456
  }
}
```

| field | type | required | rule |
|---|---|---|---|
| `fact` | string | yes | non-empty; no whitespace; unique within the target |
| `value` | boolean | yes | exactly `true` in v1 (1.6) |
| `source` | object | yes | the scene choice that sets the fact |

`source` fields, all required:

| field | type | rule |
|---|---|---|
| `kind` | string | exactly `scene_choice` in v1 |
| `step` | string | a route step id; MUST exist in `data/route.json` |
| `branch` | string | a branch id; MUST exist in `data/branches.json` and MUST be the branch whose `sets` contains `fact` |
| `file` | string | the branch's scene resource path, exactly |
| `locid` | integer | the branch's `choice_locid`, positive; MUST resolve in the string database |

Cross-file rules:

- The branch's `step` MUST equal `source.step`.
- The branch's `scene` MUST equal `source.file`.
- The branch's `choice_locid` MUST equal `source.locid`.
- The row's `fact` MUST appear in the branch's `sets`.
- Every required fact MUST be set by at least one guidance row's branch. A target with a required
  fact that no guidance row can set is a validation error: it could never be reachable.
- A requirement fact MUST NOT be a fact that the app only infers from a quest being done. It needs a
  scene-choice setter, so the branch behind it is reviewable.

`requires` order is canonical: target order is defined in 2.6; within a target, rows are sorted by
`fact` ascending. The order has no meaning beyond deterministic payloads.

### 2.4 `guidance` rows

A guidance row says: at this step, for this target, the exact scene line is this string.

```json
{
  "step": "q105evilspirit",
  "branch": "q105_help_spirit",
  "instruction": "exact scene line, not a paraphrase",
  "source": {
    "kind": "scene_choice",
    "file": "quests\\part_1\\q105_witches\\scenes\\q105_...w2scene",
    "locid": 123456
  }
}
```

| field | type | required | rule |
|---|---|---|---|
| `step` | string | yes | a route step id; MUST exist in `data/route.json`, equal the branch's step, and be unique within the target |
| `branch` | string | yes | a branch id in `data/branches.json`; MUST set at least one of this target's required facts |
| `instruction` | string | yes | the exact line the scene offers; see the exactness rule below |
| `source` | object | yes | `kind` is `scene_choice`; `file` and `locid` MUST match the branch's scene and choice locId |

Exactness rule:

- `instruction` MUST equal the string-database text for `source.locid` after Unicode NFC and
  trimming leading/trailing whitespace. Nothing else is accepted: no paraphrase, no ellipsis, no
  "say the kind option", no translation made by the reviewer.
- `source.locid` MUST be positive. `locid: 0`, a negative number or a missing source is a validation
  error.
- `instruction` MUST be non-empty.
- The row MUST NOT carry a `sets`, `tests`, `choice_text` or `one_shot` field. The facts it sets are
  read from `branches.json`; duplicating them here would let the two disagree.

Derived facts:

- `facts = branch.sets ∩ target.requires[*].fact`. It MUST be non-empty.
- The payload's `Detail.guidance[].facts` is this set, sorted. The UI's "Why" line names it.
- Every required fact MUST be covered by at least one guidance row.
- `step` MUST be unique within a target: at most one guidance row per step. If one step offers two
  independent choices for the same goal, they are separate route steps or separate targets, not two
  lines in one detail pane. With unique steps, `(step, branch)` is unique as well.
- Guidance rows are ordered by route order of `step`, then by `branch` ascending. The UI does not
  depend on authored order.

A target with `guidance_status: "not_guided_yet"` has no guidance rows. It never gets a guessed
row while the scene is missing.

### 2.5 `presets`

A preset is a named selection of targets. It does not add facts, change a target, or rank outcomes.

```json
{
  "recommended": {
    "label": "Recommended endings",
    "targets": ["ciri_witcher", "bw_both_sisters", "baron_wife_cured"],
    "reviewed": "2026-10-28",
    "note": "A reviewed preference, not a game ranking."
  }
}
```

| field | type | required | rule |
|---|---|---|---|
| `label` | string | yes | 1-80 characters |
| `targets` | array | yes | at least one target id, unique, every id MUST exist in `targets` |
| `reviewed` | string | yes | `YYYY-MM-DD` |
| `note` | string | no | must not claim the game ranks outcomes |

- Preset ids use the same pattern as target ids.
- `presets.recommended` is required for a 1.0 release. Its `label` MUST be exactly
  `Recommended endings`.
- A preset that contains two targets connected by a `target` edge in `data/exclusive.json` is
  allowed. `endings.py check` reports the conflict as a warning; the UI MUST show the tradeoff and
  ask for confirmation before applying the preset. Validation does not silently drop either target.
- Selecting a preset writes its target ids to `settings.json`; the preset id itself is not
  persisted. There is no hidden "preset mode" that changes state later.
- `All still possible quests` and `All Gwent cards` are not entries here (1.7). They are planner
  selectors and are defined with the planner.

### 2.6 Canonical target order

JSON object order is not a contract. The canonical order is:

1. pack order `base`, `ep1`, `bob`, `other_dlc`, `gwent`;
2. then target id ascending.

`settings.endings`, `View.target.ids`, `View.target.labels`, `View.target.states` and
`Detail.guidance` all use this order. A preset's `targets` array is normalized to it before it is
applied. This keeps the payload deterministic regardless of how the reviewed file is formatted.

### 2.7 `py tools/endings.py check`

`py tools/endings.py check` runs the normal check; `py tools/endings.py check --release` adds the
release-only requirements (`presets.recommended`, no `fixture_` ids). Both modes are check-only:
they never rewrite `endings.json`, `branches.json` or the route. The checker reads:

- `data/endings.json`
- `data/branches.json`
- `data/route.json`
- `data/quest_index.json`
- the game's string database through `tools/stringsdb.py`
- `data/exclusive.json` when present, for preset-conflict warnings

It MUST fail, with the target id and field named, on every one of these:

- invalid JSON, wrong `version`, unknown keys, missing required fields, wrong types;
- a target id, label, preset id or preset label that is duplicated where it must be unique;
- a `pack` outside the enum, a `spoiler` that is not `true`, an invalid `reviewed` date;
- a guided target with no `requires` or no `guidance`;
- a `not_guided_yet` target with any `requires`, any `guidance`, no `guidance_reason`, or a
  `guidance_reason` on a guided target;
- a `requires` row with `value` not `true`, a missing/zero locId, a file that is not the branch's
  scene, a locId that is not the branch's choice locId, or a fact not in the branch's `sets`;
- a requirement fact that no guidance row's branch sets;
- a guidance row whose `step`/`branch` does not resolve, whose `source` does not match the branch,
  whose `instruction` does not equal the string-database text, or whose branch sets none of the
  target's required facts;
- a guidance row with a duplicate `step` within a target (and therefore a duplicate `(step, branch)`
  pair);
- a preset target id that does not resolve, or a preset with an empty `targets` array;
- a missing `presets.recommended` in a release check, or `recommended` whose label is not
  `Recommended endings`;
- a shipped target id beginning `fixture_`;
- placeholder tokens in shipped data: a string containing `<`, `>`, `TODO`, `TBD` or `FIXTURE`.

It MUST warn, not fail, on:

- a preset containing an exclusive pair;
- a target whose pack has no coverage row (the coverage data is stale, not the target wrong).

The checker MUST run in the release gate before `regen.py` and `cargo test`. A target that cannot
pass this check is not shipped; `not_guided_yet` is the honest alternative.

---

## 3. `settings.json` and the first-run flow

### 3.1 Keys

File: the existing per-user app folder,
`%APPDATA%\Witcher3MissablesTracker\settings.json`. It is not in `data/`, not in the game folder and
not in the saves folder.

```json
{
  "game_dir": "C:\\Games\\The Witcher 3",
  "saves_dir": "C:\\Users\\player\\Documents\\The Witcher 3\\gamesaves",
  "endings": [],
  "guidance": "off",
  "setup_v1": true
}
```

| key | type | default when absent/invalid | meaning |
|---|---|---|---|
| `game_dir` | string or `null` | `null` | manual game-folder override; `null` = auto-detect; an empty string is read as `null` |
| `saves_dir` | string or `null` | `null` | manual saves-folder override; same rules |
| `endings` | array of strings | `[]` | selected target ids, normalized to canonical order, deduplicated; unknown ids are dropped on load |
| `guidance` | `"off"` or `"on"` | `"off"` | whether exact lines are shown for the selected targets; forced `"off"` whenever `endings` is empty |
| `setup_v1` | boolean | `false` | whether the first-run card has been answered; once `true`, never show it again |

Rules:

- `game_dir` and `saves_dir` keep their current 0.2.2 meaning. A 1.0 upgrade MUST preserve them.
- `endings: []` is the spoiler-free state. `guidance` MUST be `"off"` in that state, both on read and
  on write. A file with `endings: []` and `guidance: "on"` is normalized to `"off"`; the app does
  not honour the stale value.
- `guidance: "on"` only has meaning with at least one target. Turning guidance off keeps target
  labels visible and removes every `GOAL` chip and every instruction.
- `setup_v1` is not reset by clearing a target. Clearing returns the UI to spoiler-free; it does not
  bring the first-run card back. **My game** remains the entry point.
- Unknown keys in `settings.json` are preserved on write. This is a forward-compatibility exception
  to the strict `endings.json` schema; settings belong to the user, not to the reviewed data.
- Writes happen immediately on every change (skip, apply, change, clear, guidance toggle). There is
  no save button. Write by replacing the file atomically (temporary file in the same folder, then
  rename) so a crash cannot leave a truncated settings file.
- Missing or unreadable file: use the defaults, show the first-run card, and keep auto-detection
  working. Do not crash and do not overwrite the file merely by reading it.
- Corrupt JSON: treat as missing; the next user action writes a clean file.
- `endings` contains a stale id after `endings.json` changes: drop that id in memory, keep the rest,
  and persist the normalized list on the next settings write. If none remain, the app is
  spoiler-free. An explicit `set_target` call with an unknown id is rejected instead (3.4).

### 3.2 First launch

The first-run condition is `setup_v1 != true` **and** `endings` is empty. If targets are already
selected, the user has opted in; do not show the card over guided mode, and normalize
`setup_v1` to `true`.

The card is non-blocking. The tracker behind it is usable; the card does not cover the route or
prevent the save from loading.

Exact copy:

> **Optional: choose an ending goal.** If you want the tracker to guide you, it can ask which
> endings you are aiming for. This reveals ending names and, later, exact choice lines. You can skip
> this and stay spoiler-free.

Buttons, exact labels:

- **Skip - stay spoiler-free**
- **Choose a goal (spoilers)**

Behaviour:

1. On first launch the app MUST NOT call `get_targets()`, MUST NOT load target labels into the
   payload, and MUST NOT create hidden target nodes in the DOM. The target list simply does not
   exist yet.
2. **Skip** writes `endings: []`, `guidance: "off"`, `setup_v1: true`, preserving `game_dir` and
   `saves_dir`, and dismisses the card. The target list is never fetched.
3. **Choose a goal (spoilers)** is the only first-run path that calls `get_targets()` and renders
   target labels. (The later **My game -> Choose** action uses the same picker, but that is after
   the one-time card.) The picker groups targets by pack (`Main game`, `Hearts of Stone`, `Blood
   and Wine`, `Free DLC`, `Gwent`) and shows the `Recommended endings` preset. It shows labels,
   pack, guidance status and current target state; it MUST NOT show instructions or choice text.
4. In the picker, **Apply goals** is disabled until at least one target is selected. **Cancel**
   makes no settings change on a normal reopen.
5. On first run, closing the picker without selecting (Cancel, close, Escape) behaves like **Skip**
   for the one-time card: it writes the skip defaults and `setup_v1: true`. The user has seen the
   spoiler list; the card does not return. On a later reopen, Cancel changes nothing.
6. **Apply goals** writes the selected ids in canonical order, sets `guidance: "on"`, sets
   `setup_v1: true`, dismisses the picker and re-renders from the new `get_view`. Selecting a target
   is the opt-in to exact lines; the **Guidance** control can turn them off afterwards.
7. If `endings.json` has no targets, **Choose a goal (spoilers)** is disabled; the card offers only
   Skip. An empty target file is not a reason to invent a target.

### 3.3 My game

The **My game** panel gains one row:

- No target: `Ending goal: none`, with a **Choose** action that opens the picker.
- Target(s): `Ending goal: <label>, <label>`, with **Change** and **Clear**.
- When a target is selected: `Guidance: on` or `Guidance: off`, with a toggle. This is the only
  control that changes `guidance` without changing `endings`.

Actions:

- **Change** reopens the picker with the current ids preselected. Applying replaces the set; it
  does not append. Cancel keeps the old set.
- **Clear** writes `endings: []`, `guidance: "off"` and leaves `setup_v1: true`. The UI MUST return
  to the spoiler-free payload immediately: no target label, no instruction, no `GOAL`, no hidden
  stale DOM.
- **Guidance off** keeps the target labels and states, removes every instruction and every `GOAL`
  chip. **Guidance on** restores them only for targets that are `guided`; a `not_guided_yet` target
  still shows no line.

### 3.4 Commands

The exact signatures are:

- `set_target(ids: string[]) -> View`
  - Empty array clears the target and forces `guidance: "off"`.
  - Non-empty replaces the set, deduplicates, normalizes to canonical order, sets
    `guidance: "on"`, and writes settings.
  - An unknown id is an error and the whole call is rejected; it does not partially apply.
  - The returned `View` is the new state; the UI replaces, never merges.
- `set_guidance(on: boolean) -> View`
  - With no target, `on` is ignored and the stored value is `"off"`.
  - With a target, writes `"on"` or `"off"` and returns the new `View`.
  - Turning it off removes instructions from `get_detail` immediately; it does not change
    `endings`.
- `get_targets() -> { "targets": [TargetOption], "presets": [PresetOption] }`
  - Only called after the spoiler opt-in (3.2 step 3).
  - `TargetOption` and `PresetOption` are defined in 4.7. It MUST NOT return `instruction`,
    `requires` facts, `choice_text`, or source files.
  - It is not called on startup in spoiler-free mode; it is not embedded in `get_view` or
    `get_detail`.

---

## 4. Payload contract

The existing `View` and `Detail` gain target fields. Everything else in
[BACKEND_CONTRACT.md](BACKEND_CONTRACT.md) stays. All keys are snake_case.

### 4.1 `View.target`

Spoiler-free:

```json
{
  "target": null
}
```

With a selection:

```json
{
  "target": {
    "ids": ["fixture_bw_both_sisters"],
    "labels": ["FIXTURE ONLY - Blood and Wine: both sisters live"],
    "guidance": "on",
    "states": {
      "fixture_bw_both_sisters": {
        "state": "reachable",
        "reason": null,
        "blocked_by": []
      }
    }
  }
}
```

Rules:

- `target` is always present. It is JSON `null` in spoiler-free mode; it is never omitted and never
  an empty object.
- `ids` and `labels` have the same length and the same canonical order (2.6). `labels[i]` is exactly
  the label for `ids[i]`.
- `states` has exactly one entry per id, keyed by id. No unselected target id appears.
- `guidance` is `"on"` or `"off"` and echoes the effective settings value; with `endings` empty it
  is `"off"`.
- `states[id].state` is one of the five target states in section 6.
- `states[id].reason` is `null` for `reachable` and `settled`; it is a non-empty user-facing string
  for `impossible`, `unknown` and `not_guided_yet`.
- `states[id].blocked_by` is an array. It is empty for `reachable`, `settled`, `unknown` and
  `not_guided_yet`; it has at least one element for `impossible`.

`blocked_by` element:

```json
{
  "kind": "fact",
  "id": "fixture_bw_sisters_live",
  "source": {"kind": "file", "value": "quests\\fixture\\...w2scene"}
}
```

`kind` is `fact`, `quest` or `cutoff`. `id` is the fact id, route step id or cutoff id. `source`
follows the existing evidence convention: `{ "kind": "file" | "locid" | "save", "value": "..." }`.
The UI may show `reason`; `blocked_by` is the structured evidence behind it.

### 4.2 Step fields

The existing `Step` object gains or fixes:

| field | type | meaning |
|---|---|---|
| `branch` | boolean | a scene section on this quest sets a fact when a choice is taken; this is an outcome branch, not a one-shot dialogue row |
| `dialogue_choice` | boolean | a `singleUseChoice` dialogue row exists; never a branch and never a chip |
| `ending_relevant` | boolean | at least one reviewed target names this branch; the vague `ENDING CHOICE` chip is allowed |
| `goal` | boolean | at least one selected target is `reachable` and has an `ahead` guidance row for this step; the `GOAL` chip is allowed. The flag is independent of the guidance toggle. |

Rules:

- `goal` is `false` in spoiler-free mode. With a target selected it stays true when `guidance` is `"off"`; only the exact `instruction` is gated.
- `goal` does not reveal which target or line. The detail does that.
- The old `choice` field and `choice` tag are gone. `tags` uses:
  - `{ "id": "ending_choice", "label": "ENDING CHOICE" }` when `ending_relevant`;
  - `{ "id": "branch", "label": "CHOICE" }` when `branch` and not `ending_relevant`;
  - no tag for `dialogue_choice` alone.
- `goal` is a separate boolean, not a tag. The card renders one chip: `GOAL` if `goal`, otherwise
  `ENDING CHOICE` if `ending_relevant`, otherwise `CHOICE` if `branch`, otherwise none.

### 4.3 `Detail.branches`

One summary per fact-setting branch on the step. This is the default-mode and guided-mode branch
metadata; it never contains the line.

```json
{
  "branches": [
    {
      "id": "fixture_bw_sisters",
      "ending_relevant": true,
      "label": "a choice here affects an ending"
    }
  ]
}
```

Rules:

- Keys are exactly `id`, `ending_relevant` and `label`. `choice_text`, `sets`, `tests`, `one_shot`
  and `source` MUST NOT appear here.
- `label` is the fixed string `a choice here affects an ending` when `ending_relevant` is true, and
  `a choice changes later content` when it is false. The UI does not paraphrase it.
- A one-shot dialogue row never appears in `branches`; it is not an outcome branch.
- The branch `id` is an internal stable id, not choice text. It MUST NOT be a target label or a
  target id; `endings.py check` rejects a branch id equal to a target id.

### 4.4 `Detail.guidance`

Spoiler-free, guidance off, no target, step not in a selected target's guidance, or selected target
`not_guided_yet`: JSON `null` (present, not omitted).

Guided and on, for a step a selected target requires:

```json
{
  "guidance": [
    {
      "target": "fixture_bw_both_sisters",
      "label": "FIXTURE ONLY - Blood and Wine: both sisters live",
      "step_state": "ahead",
      "instruction": "FIXTURE ONLY - not game text; the exact scene line goes here after extraction.",
      "facts": ["fixture_bw_sisters_live"],
      "note": null,
      "source": {
        "kind": "scene_choice",
        "file": "quests\\fixture\\...w2scene",
        "locid": 9900001
      }
    }
  ]
}
```

| field | type | rule |
|---|---|---|
| `target` | string | a selected target id |
| `label` | string | that target's exact `label` |
| `step_state` | enum | `ahead`, `settled`, `unreachable` or `unknown` (6.3) |
| `instruction` | string or `null` | non-null ONLY when `step_state` is `ahead`; otherwise `null` |
| `facts` | array of strings | the required facts this branch sets; at least one; sorted |
| `note` | string or `null` | non-null for `settled`, `unreachable` and `unknown`; `null` for `ahead`; names what the save says, never choice text |
| `source` | object | `kind: "scene_choice"`, the guidance row's `file` and `locid` |

Rules:

- One element per selected target that has a guidance row for this step. No element for a selected
  target without a row; no element for an unselected target.
- Order is canonical target order (2.6). If several selected targets share the step, each element
  carries only its own label, facts, line and source.
- The `instruction` is copied from the selected target's guidance row. The UI prints it as the exact
  line; it does not add an alternative option, an outcome summary or another target's text.
- A guidance element whose `step_state` is not `ahead` MUST have `instruction: null`. The line is
  not kept "for reference" after the choice is behind the save.
- Target-state consistency:
  - target `settled` => every element for that target is `settled`;
  - target `impossible` => every element whose facts are all already set is `settled`; every other
    element is `unreachable`; none is `ahead`;
  - target `unknown` => every element whose facts are all already set is `settled`; every other
    element is `unknown`; none is `ahead`;
  - target `not_guided_yet` => no element at all;
  - target `reachable` => elements carry their per-step state (some can be settled while other
    requirements are still open).

A settled row stays settled even when the target as a whole is impossible or unknown because of a
different requirement. The app may still say what the save already has; it never shows an
instruction for a target that is not reachable.

### 4.5 Spoiler-free invariant (default)

When `settings.endings` is empty (`View.target` is `null`), the serialized `get_view` and every
`get_detail(id)` MUST satisfy all of the following:

1. `View.target` is JSON `null`.
2. No target id, target label, preset label, `instruction` or choice text appears anywhere in
   either payload.
3. No key named `targets`, `presets`, `choices` or `choice_text` appears, and no key named
   `guidance` has a non-null value.
4. Every `View.steps[*].goal` is `false`.
5. Every `Detail.guidance` is JSON `null`.
6. Every `Detail.branches[*]` has exactly the keys `id`, `ending_relevant`, `label`.
7. Allowed ending-related data is limited to:
   - `View.steps[*].ending_relevant` (boolean),
   - the fixed `ENDING CHOICE` tag/label,
   - `Detail.branches[*]` with the fixed vague label.
8. Nothing is hidden in the DOM either: no target label, target id, instruction or preset label in
   `document.body.innerHTML`, including in `display:none`, `<template>` or detached-but-rendered
   nodes. The UI does not fetch `get_targets()` on startup.

The rule tests strings, not the word "ending": `ENDING CHOICE`, `ending_relevant`, `a choice here
affects an ending` and pack names are allowed. A test that bans the substring `ending` is wrong.

### 4.6 Selected-target invariant

When `settings.endings` is non-empty:

1. `View.target.ids` equals the normalized selected ids; `labels` and `states` match exactly.
2. No unselected target id, label or instruction appears anywhere in `get_view` or any
   `get_detail`. Only the selected targets' labels and states are present.
3. If `guidance` is `"on"`:
   - `View.steps[*].goal` is true exactly on steps with at least one selected target guidance row
     whose target state is `reachable` and whose step state is `ahead`;
   - `Detail.guidance` contains only selected targets that have a row for that step;
   - every non-null `instruction` belongs to the element's own target and appears only when its
     `step_state` is `ahead`.
4. If `guidance` is `"off"`:
   - `View.steps[*].goal` is unchanged from the guided selection; goal chips are not gated by the
     toggle;
   - every `Detail.guidance` is `null`;
   - no `instruction` appears anywhere;
   - target labels and states remain visible in `View.target` and the RUN header.
5. If the selected target is `not_guided_yet`, it has no `goal`, no `Detail.guidance` and no
   instruction. Its label and state still appear.
6. `set_target([])`, **Clear**, or a selection change MUST make the previous target's line and
   label disappear from the next payload immediately. No merge, no cache, no "last target" field.
7. The save is not rewritten. Changing a target does not change facts, ticks or quest status; it
   changes only which reviewed rows are allowed into the payload.

### 4.7 `get_targets` response

Called only after the spoiler opt-in.

```json
{
  "targets": [
    {
      "id": "fixture_bw_both_sisters",
      "label": "FIXTURE ONLY - Blood and Wine: both sisters live",
      "pack": "bob",
      "spoiler": true,
      "guidance_status": "guided",
      "state": "reachable",
      "reason": null,
      "blocked_by": []
    }
  ],
  "presets": [
    {
      "id": "recommended",
      "label": "Recommended endings",
      "targets": ["fixture_bw_both_sisters"],
      "reviewed": "2026-10-28"
    }
  ]
}
```

Rules:

- `targets` is ordered by canonical target order; `presets` by preset id.
- `TargetOption` keys are exactly the eight shown: `id`, `label`, `pack`, `spoiler`,
  `guidance_status`, `state`, `reason`, `blocked_by`. `state`/`reason`/`blocked_by` follow 4.1.
- The response contains no `instruction`, no `requires` facts, no choice text and no source file.
  The picker shows labels, packs, guidance status and state; it does not show lines.
- `presets` contains only explicit target-id sets (2.5); no computed `all_quests`/`all_cards`
  entries.
- If `targets` is empty, `targets` and `presets` are empty arrays; the picker shows no choices.

---

## 5. `ENDING CHOICE` versus `GOAL`

These are different objects with different jobs. Confusing them is the main way the spoiler gate
would leak.

| | `ENDING CHOICE` | `GOAL` |
|---|---|---|
| mode | spoiler-free default; also in guided mode on an ending-relevant branch not covered by a selected target | guided mode: a target is selected; the chip does not depend on the guidance toggle |
| data source | `Step.ending_relevant` from a reviewed target naming the branch | `Step.goal` from a selected target's `guidance` row at this step |
| payload | fixed tag/label only; no target id, label, option or line | target id, label, exact `instruction`, `facts`, source in `Detail.guidance` |
| meaning | "a choice here affects an ending" | "for the goal you chose, say this exact line here" |
| action | none; the detail pane opens technical branch data | click opens `YOUR GOAL` with the exact line |
| cardinality | one vague chip per quest, no matter how many targets use it | one element per selected target that requires this step |
| after the choice | the branch is behind the save; no instruction exists at all | no `GOAL`; detail says `Already settled in this save`, line omitted |
| never shows | target name, ending name, option, outcome, line | another target, another option, outcome summary, line for a different target |
| if both apply | `GOAL` wins visually on the card; `ENDING CHOICE` is suppressed on that card | `GOAL` is the only chip on that card |

Exact UI strings:

- `ENDING CHOICE` chip, tooltip `a choice here affects an ending`.
- `CHOICE` chip for a non-ending fact branch, tooltip `a choice changes later content`. A one-shot
  dialogue row gets no chip.
- `GOAL` chip, no target name on the chip. Clicking opens the detail's target section.
- Detail headings and lines:
  - `YOUR GOAL - <label>`
  - `At this step: say "<instruction>"`
  - `Why: the line sets <facts>; the target needs it.`
  - `Already settled in this save`
  - `This goal is no longer reachable`
  - `Not enough information`
  - `Not guided yet`

Precedence on a card: `GOAL` > `ENDING CHOICE` > `CHOICE` > no chip. `GOAL` is impossible when no
target is selected; with a target selected it stays visible when guidance is off, because only the
exact line is gated. Without a goal, an ending-relevant branch shows `ENDING CHOICE`, a non-ending
fact branch shows `CHOICE`, and a one-shot dialogue row shows nothing. A one-shot dialogue row never
reaches the chip logic.

What `GOAL` is not:

- It is not a quest status, a difficulty label or a recommendation for an unselected outcome.
- It is not a permanent badge on the quest. It exists only while the step can still be changed for
  the selected target.
- It is not a second copy of `ENDING CHOICE`. The vague chip says a choice matters; `GOAL` says what
  to say for the chosen target. The card never shows both.

---

## 6. Target states

State names are lowercase in the payload and in this document. The UI may capitalize them.

### 6.1 The five states

| state | exact meaning | required evidence | UI |
|---|---|---|---|
| `reachable` | not settled, impossible or unknown; at least one required fact is still settable and at least one guidance row is `ahead` | a save that can see the source step; no closed requirement | `GOAL` on ahead steps; exact line in detail; target label in RUN |
| `settled` | every `requires` fact is already set in this save; the outcome is locked in | save facts | `Already settled in this save`; no `GOAL`; no line |
| `impossible` | a required fact is absent and its branch is provably closed for this save | a failed/closed step, a fired reviewed cutoff, or a branch passed without setting the fact; at least one `blocked_by` | `This goal is no longer reachable` + reason; no `GOAL`; no line |
| `unknown` | the save or the data cannot decide the remaining requirement | missing/unreadable save, untracked step, unmodelled pack, missing branch evidence | `Not enough information` + reason; no `GOAL`; no line; never call it reachable |
| `not_guided_yet` | the target is a reviewed label with no validated facts or guidance | `guidance_status: "not_guided_yet"` and a non-empty `guidance_reason` | `Not guided yet` + reason; no `GOAL`; no line; never guess |

The state is recomputed on every view from the current save and the reviewed files. It is not
stored in `settings.json` and is not cached across saves.

### 6.2 Requirement evaluation

For each `requires` row of a guided target:

| result | when |
|---|---|
| `met` | the save's facts contain `fact` |
| `open` | `fact` is absent, and at least one guidance row whose branch sets `fact` is `ahead` |
| `closed` | `fact` is absent, and every guidance row that can set `fact` is `settled` or `unreachable`; no row is `ahead` |
| `unknown` | `fact` is absent, and the rows that could decide it are `unknown`, or there is no readable row/step/save |

Precedence within a requirement: `met` first; otherwise `open`; otherwise `closed`; otherwise
`unknown`. If there are no guidance rows that set the fact, that is a schema error (2.4), not an
`unknown` runtime state.

### 6.3 Guidance step evaluation

`Detail.guidance[].step_state` answers a different question: what can be done at this step for this
target?

| step state | when | payload |
|---|---|---|
| `ahead` | at least one of the row's `facts` is absent, and the branch is still selectable: step `Active` or `Not started`, no fired cutoff, no closed prerequisite, target not already settled/impossible/unknown | `instruction` is the exact line; `note: null` |
| `settled` | every fact in the row's `facts` is already set in the save; the outcome the row sets is present | `instruction: null`; `note` says what the save has |
| `unreachable` | at least one of the row's `facts` is absent and the branch cannot be taken: step `Done`/`Failed`/`N/A`, a reviewed cutoff fired, a prerequisite is closed, or the whole target is impossible | `instruction: null`; `note` says why |
| `unknown` | the save or data cannot decide: no save, unreadable save, unmodelled pack, missing branch row, or a mid-quest branch whose past/future cannot be read | `instruction: null`; `note` says what is missing |

A branch behind the save with one of its facts absent is `unreachable`, not `settled`: the choice is
gone and the fact was not set. `settled` requires the fact to be present. Target state overrides
step state as listed in 4.4: a settled row stays settled, and no row is `ahead` when the target is
not reachable. A `not_guided_yet` target has no rows, so there is no step state to report.

"Behind the save" is deliberately conservative: if the branch is mid-quest and the app cannot tell
whether the choice is past, the state is `unknown`, not `ahead`. A wrong `ahead` would tell the
player to replay a choice they cannot replay; `unknown` is the honest answer.

### 6.4 Target aggregation

Given the requirement results and the target's `guidance_status`:

1. If `guidance_status` is `not_guided_yet` => `not_guided_yet`. Do not evaluate facts.
2. Else if any requirement is `closed` => `impossible`. `blocked_by` names the first closed
   requirement in canonical order; `reason` names the fact/quest/cutoff.
3. Else if every requirement is `met` => `settled`.
4. Else if any requirement is `unknown` => `unknown`.
5. Else (every requirement is `met` or `open`, at least one `open`) => `reachable`.

Consequences:

- One provably closed requirement makes the target impossible even if another requirement is
  unknown. A known loss is not softened by missing data.
- A target is never `reachable` while a requirement is unknown. The app does not promise an outcome
  it cannot evaluate.
- `settled` means the outcome is locked, not "the app recommends this". The label is the user's
  goal; the save decides whether it is already fixed.
- `not_guided_yet` is a definition state, not a save state. It is valid and visible; it is not a
  failure to hide and it is not renamed `unknown`. `unknown` means the definition is complete but
  the save cannot answer; `not_guided_yet` means the definition itself is not ready.

### 6.5 Transitions

| event | resulting state |
|---|---|
| save is before the branch; required facts absent | `reachable` |
| required line chosen; facts set | `settled` |
| different line chosen; branch behind the save; facts absent | `impossible` |
| prerequisite quest failed or a reviewed cutoff fired | `impossible` |
| no save, unreadable save, or unmodelled pack | `unknown` |
| extraction adds validated facts and guidance to a `not_guided_yet` target | recomputed; no state is persisted |
| target changed | old state discarded; new target evaluated from the same save |
| target cleared | no target state in the payload |

Changing a target never rewrites the past: the save's facts, statuses and ticks are untouched. The
app may say the old goal is no longer reachable; it may not tell the player to go back and replay a
closed choice.

---

## 7. Fixture only: "both sisters live"

**This is a shape fixture, not a real target and not a real line.** The extraction probe has not
produced a Blood and Wine scene choice. Every value below is invented: `fixture_` ids, fake fact,
fake branch, fake step, fake file, fake locIds and a fake instruction. It MUST NOT be copied into
`data/endings.json`. A release check rejects `fixture_` ids and any source that does not resolve.

The fixture shows both target shapes: `fixture_bw_both_sisters` is the guided shape with a fake line;
`fixture_bw_both_sisters_pending` is the `not_guided_yet` shape the real target must use until the
probe succeeds.

```json
{
  "version": 1,
  "note": "FIXTURE ONLY. Shape example, not shipped data. The fact, branch, step, file, locId and line are invented; this is not a Blood and Wine extraction result.",
  "targets": {
    "fixture_bw_both_sisters": {
      "label": "FIXTURE ONLY - Blood and Wine: both sisters live",
      "pack": "bob",
      "spoiler": true,
      "reviewed": "2026-10-28",
      "review_note": "FIXTURE ONLY - shape of a guided target after extraction; not a reviewed goal.",
      "requires": [
        {
          "fact": "fixture_bw_sisters_live",
          "value": true,
          "source": {
            "kind": "scene_choice",
            "step": "fixture_step_bw_sisters",
            "branch": "fixture_bw_sisters",
            "file": "quests\\fixture\\...w2scene",
            "locid": 9900001
          }
        }
      ],
      "guidance_status": "guided",
      "guidance": [
        {
          "step": "fixture_step_bw_sisters",
          "branch": "fixture_bw_sisters",
          "instruction": "FIXTURE ONLY - not game text; the exact scene line goes here after extraction.",
          "source": {
            "kind": "scene_choice",
            "file": "quests\\fixture\\...w2scene",
            "locid": 9900001
          }
        }
      ]
    },
    "fixture_bw_both_sisters_pending": {
      "label": "FIXTURE ONLY - Blood and Wine: both sisters live (not guided yet)",
      "pack": "bob",
      "spoiler": true,
      "reviewed": "2026-10-28",
      "review_note": "FIXTURE ONLY - shape of the target while no Blood and Wine scene has been extracted.",
      "requires": [],
      "guidance_status": "not_guided_yet",
      "guidance_reason": "No validated Blood and Wine scene line: the extraction probe has not produced one.",
      "guidance": []
    }
  },
  "presets": {
    "recommended": {
      "label": "Recommended endings",
      "targets": ["fixture_bw_both_sisters", "fixture_bw_both_sisters_pending"],
      "reviewed": "2026-10-28",
      "note": "FIXTURE ONLY - a reviewed preference, not a game ranking."
    }
  }
}
```

What is fake, so it cannot be mistaken for evidence:

| value | why it is fake |
|---|---|
| `fixture_bw_both_sisters`, `fixture_bw_both_sisters_pending` | `fixture_` ids are reserved and rejected in shipped data |
| `fixture_bw_sisters_live` | no such fact was extracted |
| `fixture_bw_sisters` | no such branch exists in `branches.json` |
| `fixture_step_bw_sisters` | no such route step exists |
| `quests\fixture\...w2scene` | not a game resource |
| `9900001` | not a game locId and not in the string database |
| `FIXTURE ONLY - not game text; ...` | not a scene line; it is a shape placeholder |

The real target, when it exists, uses the id `bw_both_sisters`, a reviewed label without the
`FIXTURE ONLY` prefix, real extracted facts, a real scene choice locId and the exact line that locId
resolves to. Until then, only the pending shape is honest.

### 7.1 Default payload for the fixture step

Spoiler-free `get_view` excerpt:

```json
{
  "target": null,
  "steps": [
    {
      "id": "fixture_step_bw_sisters",
      "ending_relevant": true,
      "goal": false,
      "tags": [
        {"id": "ending_choice", "label": "ENDING CHOICE"}
      ]
    }
  ]
}
```

Spoiler-free `get_detail` for the same step:

```json
{
  "branches": [
    {
      "id": "fixture_bw_sisters",
      "ending_relevant": true,
      "label": "a choice here affects an ending"
    }
  ],
  "guidance": null
}
```

No fixture target label, target id or instruction is present. The vague chip is allowed; the line is
not.

### 7.2 Guided payload for the fixture step

`get_view` excerpt after selecting `fixture_bw_both_sisters`:

```json
{
  "target": {
    "ids": ["fixture_bw_both_sisters"],
    "labels": ["FIXTURE ONLY - Blood and Wine: both sisters live"],
    "guidance": "on",
    "states": {
      "fixture_bw_both_sisters": {
        "state": "reachable",
        "reason": null,
        "blocked_by": []
      }
    }
  },
  "steps": [
    {
      "id": "fixture_step_bw_sisters",
      "ending_relevant": true,
      "goal": true,
      "tags": [
        {"id": "ending_choice", "label": "ENDING CHOICE"}
      ]
    }
  ]
}
```

`get_detail` for the same step:

```json
{
  "branches": [
    {
      "id": "fixture_bw_sisters",
      "ending_relevant": true,
      "label": "a choice here affects an ending"
    }
  ],
  "guidance": [
    {
      "target": "fixture_bw_both_sisters",
      "label": "FIXTURE ONLY - Blood and Wine: both sisters live",
      "step_state": "ahead",
      "instruction": "FIXTURE ONLY - not game text; the exact scene line goes here after extraction.",
      "facts": ["fixture_bw_sisters_live"],
      "note": null,
      "source": {
        "kind": "scene_choice",
        "file": "quests\\fixture\\...w2scene",
        "locid": 9900001
      }
    }
  ]
}
```

Only the selected target's label and fake line appear. The pending target's label and reason are not
in either payload.

### 7.3 Settled fixture step

If the save already has `fixture_bw_sisters_live`, the target state is `settled` and the detail keeps
the row but drops the line:

```json
{
  "guidance": [
    {
      "target": "fixture_bw_both_sisters",
      "label": "FIXTURE ONLY - Blood and Wine: both sisters live",
      "step_state": "settled",
      "instruction": null,
      "facts": ["fixture_bw_sisters_live"],
      "note": "The save already has fixture_bw_sisters_live.",
      "source": {
        "kind": "scene_choice",
        "file": "quests\\fixture\\...w2scene",
        "locid": 9900001
      }
    }
  ]
}
```

`instruction: null` is deliberate. A settled choice must not keep the line "for reference"; that is
how a spoiler survives a reload.

### 7.4 Pending fixture state

Selecting `fixture_bw_both_sisters_pending`:

`View.target` excerpt (the real `View` still has its 414 steps; this block shows only the target):

```json
{
  "ids": ["fixture_bw_both_sisters_pending"],
  "labels": ["FIXTURE ONLY - Blood and Wine: both sisters live (not guided yet)"],
  "guidance": "on",
  "states": {
    "fixture_bw_both_sisters_pending": {
      "state": "not_guided_yet",
      "reason": "No validated Blood and Wine scene line: the extraction probe has not produced one.",
      "blocked_by": []
    }
  }
}
```

Every `get_detail` for this state has `guidance: null`. The target is visible as `Not guided yet`;
no fact, line or `GOAL` is invented.

---

## 8. Verification checklist for this specification

### 8.1 JSON examples

Every JSON block in this document MUST parse with a standard JSON parser. This includes the fixture
and the payload excerpts; excerpts are valid JSON, not fragments with comments.

### 8.2 `endings.py check`

- [ ] All schema, cross-file, exact-text, locId, preset and fixture-id checks in 2.7 run in the
      release gate.
- [ ] A target with a fake/unresolved locId fails.
- [ ] A target with a paraphrased line fails.
- [ ] A `not_guided_yet` target with a placeholder fact or line fails.
- [ ] A preset with an exclusive pair produces a visible warning, not a silent drop.

### 8.3 Payload test

The test is at the serialized payload level, not a hand-built subset and not a DOM-only check.
Build the forbidden list from `data/endings.json`, so a new target is covered automatically:

```text
forbidden = { every target id,
              every target label,
              every guidance instruction,
              every preset label }
assert forbidden is not empty
```

Default:

```text
view = get_view()
assert view["target"] is null
assert every view.steps[*].goal is false
assert forbidden strings do not occur in json(view)
for each route step id:
    detail = get_detail(id)
    assert detail["guidance"] is null
    assert forbidden strings do not occur in json(detail)
    assert every detail["branches"][*] has only id, ending_relevant, label
```

Selected target A:

```text
set_target([A])
view = get_view()
assert view.target.ids == [A]
assert view.target.labels == [label(A)]
for each step:
    detail = get_detail(step)
    assert B ids/labels/instructions do not occur, for every B != A
    if detail.guidance is not null:
        assert every element.target == A
        assert every element.instruction is not null only when step_state == "ahead"
        assert every element.facts is a subset of requires(A)
```

Positive and negative controls:

- The default test fails if `forbidden` is empty. A test with nothing to look for is not a test.
- Inject `label(A)` into a copy of `view` and assert the scanner fails. This proves the scanner can
  catch a leak.
- Select A, then clear; assert the default payload returns and no A label/instruction remains.
- Select A with `guidance: "off"`; assert labels and goal chips remain as with guidance on, every
  `guidance` is null, and no instruction exists.
- A save where A is settled must still produce a spoiler-free default payload. The default gate is
  about settings, not about whether the save happens to prove a target.

Mistakes the test MUST catch:

| mistake | caught by |
|---|---|
| target label placed in `View.target.labels` while no target is selected | default scan |
| target list included as `View.targets` or a hidden DOM container | default scan + DOM scan |
| `Detail.guidance` left populated after **Clear** | clear test |
| target B's line appears in target A's detail | selected-target scan |
| instruction retained when `step_state` is `settled`/`unreachable`/`unknown` | instruction-only-when-ahead assertion |
| `GOAL` shown when no target is selected | default scan |
| target list fetched on startup | invoke-call log in the browser mock |
| skip does not write the three default keys | settings file read after skip |

### 8.4 First-run test

- [ ] With no `settings.json`, start the app: first-run card is visible, non-blocking, and
      `get_targets` is not called.
- [ ] **Skip** writes exactly `endings: []`, `guidance: "off"`, `setup_v1: true`; `game_dir` and
      `saves_dir` are preserved; target labels are absent from the DOM and from
      `get_view`/`get_detail`.
- [ ] Relaunch after Skip: no card.
- [ ] **Choose a goal (spoilers)** fetches targets only then; the list is grouped by pack and shows
      `Recommended endings`.
- [ ] Apply writes canonical ids, `guidance: "on"`, `setup_v1: true`; only those labels appear.
- [ ] **Clear** writes `endings: []`, `guidance: "off"`; `setup_v1` stays `true`; the default
      payload returns immediately.
- [ ] **Guidance off** keeps labels and goal chips, removes every instruction, and leaves
      `Detail.guidance` null.
- [ ] A stale id in settings is dropped on load without a crash or a label leak.
- [ ] A corrupt settings file falls back to defaults and shows the card once, not a crash loop.

### 8.5 Scope note

This document does not prove that Blood and Wine scenes can be extracted and does not define a real
B&W line. The fixture is a shape. If the extraction probe fails, the real `bw_both_sisters` target
stays `not_guided_yet` with a reason; it never ships the fixture text. The checker and its negative
fixtures are implemented in `tools/endings.py` and `tools/test_endings.py`.
