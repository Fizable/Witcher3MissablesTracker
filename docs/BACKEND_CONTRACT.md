# Backend <-> UI contract (Tauri v2, `withGlobalTauri: true`)

UI calls `window.__TAURI__.core.invoke(cmd, args)` and listens with
`window.__TAURI__.event.listen('view', e => render(e.payload))`. The backend emits `view` (same payload as
`get_view`) whenever a new save appears or something changes. All JSON keys are snake_case.

## Commands

- `get_view() -> View`
- `get_detail(id: string) -> Detail`
- `get_targets() -> { targets: TargetOption[], presets: Preset[] }` (only called after the spoiler opt-in)
- `get_outcomes() -> OutcomeMatrix` (spoiler-gated; the matrix of terminal outcomes, never called on startup)
- `get_plan(targets?: string[]) -> RunPlan` (spoiler-gated; defaults to the selected targets, carries
  exact lines only for steps still ahead)
- `set_target(ids: string[]) -> View` (empty clears the target and restores the spoiler-free payload)
- `set_guidance(on: boolean) -> View` (effective only while a target is selected)
- `get_cards() -> CardReport`
- `set_card(id: string, owned: boolean) -> CardReport` (manual fallback, never inferred from quest status)
- `search(q: string) -> SearchHit[]` (q length >= 2)
- `check_quest(short: string) -> Verdict`
- `toggle_tick(id: string) -> View` (manual tick / override)
- `set_level(level: number) -> View`
- `set_flag(flag: string, value: "yes"|"no"|"") -> View`
- `set_folder(kind: "game"|"saves", path: string) -> View`
- `pick_folder(kind: "game"|"saves") -> View`
- `set_pin(pin: boolean) -> void` (always on top)
- `open_url(url: string) -> void`

## View

```
{
  "save": { "name": "QuickSave_....sav", "age_secs": 140, "error": "" },
  "level": 15,                                  // 0 = unknown
  "game_dir": "C:\\...\\The Witcher 3",
  "folders": {
    "game":  { "path": "...", "ok": true, "auto": true },
    "saves": { "path": "...", "ok": true, "auto": true },
    "message": ""
  },
  "sections": ["Main", "Secondary", "Contracts", "Treasure Hunts", "Gwent"],
  "steps": [ Step, ... ],                       // all 412 route nodes, section then level then order
  "todo": ["q205lofoten", ...],                 // ordered ids for UP NEXT: the tracked quest only. Other
                                                // in-log quests and a window already in NOW are not repeated;
                                                // they live in MORE > PROGRESS / NOW. The plan adds no id.
  "tracked": null | {
    "short": "q301dreamer", "display": "Pyres of Novigrad", "status": "Active",
    "steps": ["q301dreamer"],
    "warning": null | { "level": "stop"|"warn", "headline": "...", "details": ["..."] },
    "choice": null | {
      "guided": true, "text": null,
      "lines": [ { "line": "Velen.", "target": "bw_both_sisters" } ]
    } | { "guided": false, "text": "This choice affects an ending.", "lines": [] }
  },
  "top": [ TopItem, ... ],                      // empty is a valid, tested answer; the UI hides the section
  "status": [ StatusItem, ... ],                // MORE > STATUS only: settled losses, passed cutoffs and
                                                // failed quests; same row shape as TopItem, with "live" added
  "objectives": { "<step id>": ["Follow Yennefer to Lofoten.", ...] },  // up to 4, current objective first
  "flags": [ { "id": "letho", "label": "...", "note": "...", "value": "yes"|"no"|"" }, ... ],
  "target": null | {
    "ids": ["bw_both_sisters"], "labels": ["Blood and Wine: both sisters live"],
    "guidance": "on"|"off",
    "states": { "bw_both_sisters": { "state": "reachable"|"settled"|"impossible"|"unknown"|"not_guided_yet",
                                     "reason": null|"...", "blocked_by": [...] } }
  },
  "setup": { "needed": true, "has_targets": true },  // first-run gate; needed=false after skip or a target
  "completion": {
    "quests": { "done": 135, "available": 262, "at_risk": 6, "lost": 0, "excluded": 0,
                "unknown": 0, "total": 403, "max_achievable": 403 },
    "matrix": { "total": 412, "quests": 403, "manual": 9,
                "done": 144, "obtainable": 262, "at_risk": 6, "lost": 0, "excluded": 0,
                "unknown": 0, "max_achievable": 412, "outside_route": 0,
                "sections": { "Main": { "total": 96, "done": 39, ... }, ... },
                "manual_audit": { "baseline": 11, "kept": 9, "replaced": 2, ... } },
    "manual": { "baseline": 11, "kept": 9, "replaced": 2, "reviewed": 9,
                "done": 9, "obtainable": 0, "at_risk": 0, "lost": 0, "excluded": 0, "unknown": 0 },
    "exclusions": [ { "id": "q310keira", "title": "A Final Kindness",
                       "mechanism": ["keira_sent=no"], "reason": "Excluded: ..." } ],
    "cards":  { "owned": 129, "available": 94, "at_risk": 0, "ahead": 0, "check": 0, "lost": 0,
                "excluded": 0, "unknown": 1, "total": 224, "missable": 14,
                "window_tier_a": 186, "window_tier_b": 15,
                "missable_tier_a": 0, "missable_tier_b": 14, "max_achievable": 223 }
  },
  "coverage": { "packs": { "base": { "quests": 281, "with_phases": 225, ... }, ... } },
  "tradeoffs": [ { "a": "...", "b": "...", "a_label": "...", "b_label": "...", "reason": "..." } ]
}
```

`target` is `null` until the user selects a goal. The default payload contains no target label, no
ending name and no choice line; `setup.needed` drives the first-run card. `tradeoffs` is empty until
a goal is selected and only carries edges touching a selected outcome. `completion.quests` counts
the 403 file-derived quest steps; `completion.matrix` is the audited 412-node matrix (403 quests +
9 manual reviewed rows, each `manual_reviewed`), with all six states and `outside_route` for a journal the save carries but
the route does not. `matrix.sections` is the same classification counted per section; PROGRESS reads
it instead of recounting statuses, so its section headers always sum to the matrix total. A manual
row is never Tier A, and `manual_audit` names the 2 baseline rows replaced by file-derived journals.
`exclusions` names every in-route exclusion and its mechanism; RUN shows those names, not only the
count. Cards are counted separately, with `unknown` kept apart from `not owned`. A single completion
percentage is never printed.

### OutcomeMatrix (spoiler-gated)

```
{
  "version": 1,
  "groups": [
    { "id": "main_ciri", "label": "Main story: Ciri's fate", "pack": "base", "selection": "one",
      "outcomes": [
        { "id": "ciri_witcher", "label": "Ciri lives: witcher ending", "pack": "base",
          "state": "met"|"open"|"impossible"|"unknown", "reason": null|"...",
          "blocked_by": [...], "guidance_status": "guided"|"not_guided_yet",
          "target_id": "ciri_witcher"|null, "selected": true } ] }
  ],
  "selected": ["ciri_witcher", ...],
  "selected_outcomes": ["ciri_witcher", ...],
  "conflicts": [ { "kind": "outcome_group"|"exclusive", "targets": [...],
                    "group"?: "...", "outcomes"?: [...], "a"?: "...", "b"?: "...",
                    "reason": "...", "mechanism"?: "...", "evidence"?: [...] } ],
  "counts": { "groups": 4, "outcomes": 11, "targets": 4 }
}
```

`conflicts` contains both save inconsistencies (`outcome_group` with two set outcomes) and selected-goal
conflicts (different outcomes in one group chosen together, or a reviewed `exclusive.json` edge).
The planner uses the same selector, so the matrix and `get_plan` cannot disagree about a selected pair. No instruction, choice line or
journal description is present in the matrix; the state and the reviewed labels are the whole payload.

### RunPlan (spoiler-gated)

```
{
  "version": 1, "state": "ready"|"empty"|"conflict"|"blocked"|"unknown",
  "selected": ["ciri_witcher", ...],
  "unguided": [], "invalid": [],
  "conflicts": [ { "kind": "outcome_group"|"exclusive", "targets": [...], "reason": "...",
                    "group"?: "...", "outcomes"?: [...], "a"?: "...", "b"?: "...",
                    "mechanism"?: "...", "evidence"?: [...] } ],
  "blocked_by": [ { "target": "...", "outcome": "...", "reason": "...", "blocked_by": [...] } ],
  "steps": [
    { "step": "q110postbattle", "title": "Blood on the Battlefield", "order": 41,  // route index, not CJournalQuest.order
      "level": 20,                             // suggested level; plan sorts by level, then route index
      "state": "ahead"|"settled"|"unreachable"|"unknown", "targets": ["ciri_witcher"],
      "instructions": [ { "target": "ciri_witcher", "instruction": "All right, Velen it is.",
                           "kind": "scene_choice", "file": "...", "locid": 550164, "facts": [] } ],
      "facts": ["q110_to_emperor"], "confirmation": false,
      "note": null|"No dialogue line: the game phase sets the terminal fact...",
      "prerequisites": [] }
  ],
  "coverage": { "targets": 4, "guided": 4, "groups": 4, "steps": 7, "ahead": 5,
                "met": 1, "open": 3, "impossible": 0, "unknown": 0 },
  "note": "Suggested level, then route order. Instructions are present only for steps still ahead..."
}
```

A `confirmation` step is a terminal phase fact, not a dialogue choice: `instructions` is empty and
`note` says so. `instructions` is empty on every non-`ahead` step, so a settled choice line never
returns to the window. `unguided` lists selected targets with no reviewed guidance; such a plan is
`state: "blocked"`, has no steps, and counts only guided targets in `coverage.guided`.

No `alerts`, `holdoff`, `feed`, `kb`, `guide`, `choices`, `start`, `note`, `conf` or `src` keys. The 0.1.9
`feed.json` and the 25 events are frozen in `data/legacy_*.json` and are not part of this contract.

### Step

```
{
  "id": "q301dreamer", "title": "Pyres of Novigrad",
  "section": "Main"|"Secondary"|"Contracts"|"Treasure Hunts"|"Gwent",
  "lv": "12",                                  // string, may be ""
  "status": "Done"|"Active"|"Not started"|"Failed"|"Assumed"|"N/A",
  "journal": "Active",                         // the save's own status, ticks excluded
  "frontier": "done"|"in_log"|"gated"|"available"|"unknown",
  "manual": false,                             // true = the save cannot show it; the user ticks it
  "opt": false,                                // optional extra; still shown and counted in PROGRESS
  "kind": "main"|"side"|"contract"|"treasure"|"gwent"|"manual",
  "desc": "One short sentence from the game's own journal description.",
  "branch": true,                              // a scene section sets a fact; the text is never shipped
  "dialogue_choice": false,                    // a one-shot dialogue row exists; not an outcome branch
  "ending_relevant": false,                    // a reviewed target names a fact this step's branch sets
  "goal": false,                               // selected target still has a line ahead on this step
  "order": 2583691262,                         // CJournalQuest.order: last tie-break only
  "start_known": true,                         // false = no activation block found, not unavailable
  "provenance": "game_file"|"manual_reviewed",  // manual rows are never Tier A
  "review_reason": "",                         // manual rows: why the save cannot read it
  "review_source": "",                         // manual rows: resolver-checked docs anchor
  "reviewed": "",                              // manual rows: YYYY-MM-DD
  "in_route": true,                            // false = save-only row, not in the 412
  "classification": {
    "state": "done"|"obtainable"|"at_risk"|"lost"|"excluded"|"unknown",
    "reason": "The evidence for this state in your save.",
    "source": "journal"|"save"|"cutoff"|"world_state"|"route"|"manual_reviewed"
  },
  "tick_disagrees": false,                     // ticked, but the journal still has it open
  "conditional": false,                        // only exists in some playthroughs (when/flag)
  "locked": [ { "id", "title", "manual" } ],   // unmet prerequisites
  "held": null | { "why": "...", "blockers": [ { "id", "title", "manual" } ] },
  "lost": false,
  "tags": [ { "id": "branch"|"ending_choice"|"gwent"|"missable", "label": "CHOICE"|"ENDING CHOICE"|"Gwent"|"missable" } ],
  // attached from data/derived.json by main.rs:
  "game_title": "Pyres of Novigrad",
  "objectives": [ { "text": "...", "locid": 123 } ],
  "activators": [ { "class": "CJournalQuestBlock", "file": "quests\\...", "block": 12 } ],
  "watch": [ Watch, ... ],
  "stems": ["q301dreamer"]
}
```

### TopItem

```
{
  "kind": "lost"|"failed"|"risk"|"order"|"missable"|"card",
  "level": "lost"|"stop"|"warn",
  "tag": "DO THIS NOW"|"ORDER"|"CARD WINDOW OPEN"|
         "CUTOFF PASSED - CHECK NOW"|"LOST IN THIS SAVE"|"FAILED IN YOUR QUEST LOG"|
         "CARD WINDOW PASSED - CHECK NOW"|"CARD LOST IN THIS SAVE",
  "headline": "One player-facing sentence naming the quest and why it is lost or at risk.",
  "detail": "The file mechanism behind it.",
  "action": null | "Give both statuettes to Triss during Final Preparations", // null once the journal marks the quest Failed
  "live_note": "In this save: not in your log: the end of Final Preparations.",
  "mechanism": "CDeactivateSpawnset"|"journal Failure block"|"save",
  "file": "quests\\...w2phase switches off ...w2comm (...)",
  "quests": ["The Nobleman Statuette", "The Soldier Statuette"],
  "ids": ["mq3012noblestatuette", "mq3012warriorstatuette"]  // route steps the UI can open
}
```

`StatusItem` has the same fields as `TopItem`, plus `live` for the row's win state (`lost`, `check`,
`passed`), and is read only by MORE > STATUS. `settled` and `unknown` never become a TopItem. `top`
carries only `open` and `inside` quest windows and an `active` card window; `lost`, `passed`/`check`
and `ahead` rows are STATUS or ledger rows. `Step.watch` and `Detail.derived.watch` are the same
save-aware read through `main.rs::read_warning`; a reviewed turn-in applies its both/one/neither
wording before either surface or `top` sees the row, so the card, the band and `verdict.headline`
cannot disagree about what is still missing. `kind` ordering is risk, order, then card. A choice is
not a TopItem at all: `tracked.choice` states it on the tracked quest card. With guidance off it is
only the constant sentence and empty `lines`; with guidance on and a goal selected it carries the
exact reviewed line and its target. A quest with no open `ending_relevant` step, or whose plan step
is not `ahead`, has `choice: null`.
A cutoff that has fired while the journal still has the quest open is `risk` with the tag
`CUTOFF PASSED - CHECK NOW`, not `lost`: only a `Failed` journal entry produces `lost`.
The UI shows only `tag` and `headline` on the top card; `detail`, `mechanism`, `file`, `action` and
`live_note` are kept for the detail pane's collapsed **Technical details**, not for the list.

## Detail

```
{
  "step": Step,
  "current_objectives": ["Ring Peacefully", "Find and talk to Igor, the Ringleader"],
  "derived": null | { "game_title", "objectives": [...], "activators": [...], "watch": [Watch], "stems": [...] },
  "derived_source": "tools/derive.py ...",
  "graph": {
    "starts": [ { "kind": "journal_entry", "block": 115, "class": "CJournalQuestBlock",
                  "resource": "...\\baron.journal", "file": "quests\\...w2phase",
                  "source": { "kind": "file", "value": "..." } } ],
    "requires": [ { "step": "q302mafia", "facts": ["q302_whoreson"] } ],
    "lost_when": [ { "id", "event_name", "affected", "closed_by", "resource", "mechanism", "file" } ]
  },
  "branches": [ { "id": "q704bfairyland__1154229__q704_ft_ribbon_won", "ending_relevant": true,
                  "label": "a choice here affects an ending" } ],
  "guidance": null | [ {
    "target": "bw_both_sisters", "label": "Blood and Wine: both sisters live",
    "step_state": "ahead"|"settled"|"unreachable"|"unknown",
    "instruction": "I'll pay you for the ribbon." | null,   // only while ahead
    "facts": ["q704_ft_ribbon_won"], "note": null|"...",
    "source": { "kind": "scene_choice", "file": "...w2scene", "locid": 1154229 }
  } ],
  "tracking": "Read automatically from your save (q301dreamer).",
  "overridden": false,
  "verdict": null | Verdict
}
```

No wiki prose and no `choices` text. `current_objectives` is what the save itself marks active;
`derived.objectives` is the journal's full list, used as the fallback and behind "Show all
objectives". `guidance` is `null` without a selected target; the fact names and the scene source are
evidence for the collapsed **Technical details**, not text printed next to the instruction.

The UI does not print `graph.starts`; file paths and the mechanism prose in `derived.watch` sit under
**Technical details**, collapsed by default.

## TargetOption / CardReport

```
TargetOption = { "id", "label", "pack", "spoiler", "guidance_status", "state", "reason", "blocked_by" }
Preset       = { "id", "label", "targets": ["..."], "reviewed", "note" }
CardReport   = { "cards": [ { "id", "name", "deck", "pack", "collection",
                              "owned": "owned"|"not_owned"|"unknown",
                              "source_text", "source_kind", "note",
                              "window": { "kind": "missable"|"one_time"|"none",
                                          "tier": "gamefile"|"community"|"unknown",
                                          "tier_rank": "A"|"B"|"C",
                                          "step"|"reason", "sources_checked", ... },
                              "window_live": { "state", "tone", "label", "step", "step_title",
                                                "event", "mechanism"|"reason" } } ],
                 "counts": { "owned", "not_owned", "unknown", "total", "missable",
                             "missable_tier_a", "missable_tier_b", "one_time", "no_window",
                             "tier_a", "tier_b", "tier_c", "active", "ahead", "passed",
                             "check", "lost" },
                 "block_ok": true, "reason": "",
                 "missable_windows": { "proven": false, "reviewed": true,
                                       "tier_a": 202, "tier_b": 15, "tier_c": 7 } }
```

`TargetOption.reason` can contain a file-level explanation for a `not_guided_yet` target; the picker
shows only the state and does not print that reason. Card ownership is `unknown` when the save has no
collection block; a quest being done never implies a card is owned. `window` is the reviewed
classification and never changes ownership. `window_live` reads the same route statuses the quest
matrix reads: a Tier B `missable` row becomes `check` when its step is done or failed, never a hard
`lost`; `one_time` becomes `passed`. `window_live.label` is the only card-window label the UI
prints, and `window_live.tone` selects its colour; the UI no longer re-derives a label from
`window.kind`. A `none` row carries `reason` and `sources_checked`, including the concrete source
rows behind the decision; a category-only reason is rejected. Tier B rows carry `source.name`,
`source.url` and `source.reviewed`, and the UI prints the community label, source and date even on
an owned row.

## Search / Verdict

```
SearchHit = { "short": "mq1015lynch", "display": "Lynch Mob", "status": "Not started", "step": "mq1015lynch" }
Verdict   = { "verdict": "safe"|"warn"|"stop"|"info", "headline": "...", "details": ["..."],
              "display": "Lynch Mob", "from_game_files": true, "evidence": "files"|"files+saves" }
```

Every hit resolves through `step_short`, so a node carrying several files reports the first
journal in `short`; opening the hit cannot change the answer. `check_quest(short)` and
`get_detail(id)` both call `verdict_for`. The detail page renders `detail.verdict` at the top under
`CAN I DO THIS NOW?`; a hit without a step renders the same `Verdict` in the search panel. `--detail`
is the parity oracle for the rendered headline.
