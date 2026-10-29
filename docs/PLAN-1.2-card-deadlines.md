# Plan 1.2 - from a card ledger to real card deadlines

**Status: deferred.** The next milestone is **1.1, the outcome matrix and run planner**
([HANDOFF-1.1.md](HANDOFF-1.1.md)). This file is the card work order after that; it is kept so the
measured card probe and its reviewed decisions are not lost. It records what 1.0 shipped, what is
still unproven about cards, and the card-only work order.

Project: `C:\Steam\steamapps\common\The Witcher 3\w3tracker`

## 1. The goal, unchanged

The app answers one question: **what do I do next in this save, and what can I still lose?**

- The game's files decide every rule.
- The loaded save decides every fact about where you are.
- The app decides only order and presentation.
- No second-hand knowledge. No wiki text. No guessed choice line.
- Silence is valid: if nothing can still change, the top section is absent.
- Ticks fill gaps the save cannot see; the journal and a fired cutoff outrank a tick.
- No spoilers by default. An ending label or exact line appears only after the user opts into a
  goal.
- Universal by construction: keyed on quests, branches, cards and targets, never on one save.

The long-term user goal is still **100% completion: all obtainable quests, the chosen endings, and
no missed Gwent cards**. 1.0 gets the quest/ending/card ledger right. It does **not** yet prove
card-level deadlines.

## 2. What 1.0.0 actually contains

Release: `Witcher3MissablesTracker-1.0.0` in `dist/`, root runner
`Witcher3MissablesTracker.exe`, version `1.0.0` in `Cargo.toml`, `Cargo.lock` and
`tauri.conf.json`.

| area | current state |
|---|---|
| route | 414 steps = 403 quests + 11 manual, base + Hearts of Stone + Blood and Wine |
| sections | Main, Secondary, Contracts, Treasure Hunts, Gwent |
| reviewed ending targets | 2: `bw_both_sisters` (guided, exact scene lines) and `baron_wife_cured` (`not_guided_yet`) |
| presets | only `Recommended endings` |
| branches | 2,286 extracted scene choices; 2 ending-relevant steps (`q704bfairyland`, `q705ceremony`) |
| cards | 224 total: 202 collectible main cards + 22 leaders; 0 `missable` rows |
| card source coverage | every shipped card has at least one source row; 0 card-level missable windows |
| coverage | base 196 cards, Blood and Wine 28, Hearts of Stone 0, other DLC 0 |
| exclusivity | `data/exclusive.json` has 0 edges |
| save target fixtures | the 120 newest saves checked do not have the both-sisters facts; `settled`/`impossible` are Rust unit tests, not a real epilogue save |

Verified for 1.0.0:

```
cargo test                 23 passed
py tools/test_endings.py   24 passed
py tools/regen.py --check  all 11 outputs match
py tools/contradictions.py 0 contradicted, 0 disputed
```

The 5 saves reported unreadable by `contradictions.py` are indexed files no longer present on disk;
they are not passes.

Packaged exe was checked from its own `dist/.../data/` with `--view`, `--detail`, `--cards` and
`--targets`: the both-sisters target reads `reachable`, the exact line is present only with a target,
and the default view contains no target label or line.

## 3. The biggest remaining gap: card deadlines

`data/gwent_cards.json` is a **collection ledger**, not a deadline warning. Every card has a primary
source and optional `sources[]`, but every `missable` field is absent/null. The UI correctly says
this:

> No card-level missable window is proven. This is the collection ledger, not a deadline warning.

That is honest, but it does not yet satisfy "no missed Gwent cards". This later release should turn
card sources into reviewed deadlines **only where the game files prove one**.

Useful existing evidence:

- `tools/probe_cards.py` found 206 main definitions, 22 leaders, 228 names, and the save's
  `CR4GwintManager.SBCollectionCard` / `SBLeaderCollectionCard` collection. Ownership is automatic
  when the block exists; a missing block is `unknown`, never `not owned`.
- `tools/cards.py` generates `data/gwent_cards.json`; its own doc says `missable` is absent
  everywhere and the checker rejects a missable row without a route step and a mechanism.
- `docs/GWENT-PROBE.md` is the measured probe. It says card-level windows are **not proven**;
  quest-level windows are plausible for some grants, but were not linked to a deadline.
- Card source rows with a strong channel may carry `step` (`phase_grant`, `merchant_card`, `quest`,
  `reward`). Other rows only name a container/file and need a reviewed mapping to a route step.
- The existing quest cutoff machinery is in `data/cutoffs.json`, `data/cutoff_windows.json`,
  `tools/cutoffs.py`, `tools/review_cutoffs.py` and the `cutoff_windows` data. Do not invent a
  parallel notion of "missable".

## 4. Recommended card work order (1.2.0)

### Step 1 - Build a card-window candidate report, not a promise

Add `tools/cardwindows.py` with `build` and `check`, or extend `tools/cards.py` with a separate
`windows` subcommand. It should join each card's strong source rows to route steps and reviewed quest
windows:

- accept only sources with `confidence: strong` and a concrete `step` (or a reviewed container ->
  step mapping);
- require a closing mechanism from `cutoffs.json` / `cutoff_windows.json`, or a one-time journal
  grant whose failure branch is named by a phase file;
- reject a candidate if the mechanism is a community switch with no journal failure evidence (the
  0.2.2 rule still applies);
- test the candidate against the save corpus: if a save owns the card after the window, the window
  is wrong or the grant is not exclusive;
- write a review report first, with every candidate and rejected reason. Do not write `missable`
  rows in this step.

**Check:** the report exists, every candidate names a step and a file mechanism, and the count is
reported honestly. A zero is an acceptable result; a guessed window is not.

### Step 2 - Ship only reviewed windows

Add optional `missable` to `data/gwent_cards.json` in the shape the schema already anticipates:

```json
{
  "step": "cg...",
  "event": "the quest ends",
  "mechanism": "journal | CDeactivateSpawnset | ...",
  "source": { "kind": "file", "value": "quests/...w2phase", "block": 123 }
}
```

`tools/cards.py check` must reject:

- `missable` without a valid route step;
- `missable` without a mechanism/file/source;
- a card whose only source is `unknown` or `opponent_deck` carrying a deadline.

If no card passes the review, keep the section text saying no window is proven. Do not relabel a
quest cutoff as a card deadline without the card-specific source.

**Check:** every shipped window is source-backed; `py tools/cards.py check` passes; the measured
count is in the release notes, not promised in advance.

### Step 3 - Surface card windows in the app

- `src/cards.rs` already carries `missable` through `CardReport`; keep it separate from ownership.
- A card row with a reviewed window gets a `MISSABLE` / `CLOSES ...` line and the named step.
- If the card is still obtainable and the closing event is near/open, add a card entry to the top
  section. Do not use quest status to claim card ownership.
- The top entry must be silent once the card is owned or the window has passed; if the window
  passed without ownership, say the card was lost, not "maybe".
- Keep the default ledger spoiler-free: no target label or line is involved.

**Check:** unit tests for owned/not-owned/unknown and an open/passed window; a browser render with
one proven window and one unproven card; no duplicate quest warning.

### Step 4 - Resolve the all-cards completion question explicitly

`docs/PLAN-1.0-completion.md` mentions `All still possible quests` and `All Gwent cards` presets.
`docs/TARGET-SCHEMA.md` currently says presets contain only explicit target-id sets and **no
computed `all_quests`/`all_cards` entries**. That conflict must be decided before code.

Recommended default: do not add a synthetic target. Keep the card ledger and card windows, and let
`completion.cards` answer whether cards remain. If an all-cards goal is wanted later, add it as a
reviewed planner goal with explicit fields, not as a hidden computed preset.

**Check:** the decision is recorded in `TARGET-SCHEMA.md` and the implementation matches it.

### Step 5 - Add the remaining ending evidence, one review at a time

- **Baron: his wife is cured** is `not_guided_yet` because the outcome is set by the
  `q105_evil_spirit` phase script, not a scene choice. Adding it needs a reviewed phase-script
  guidance source, not a paraphrase. The schema currently only has `scene_choice` guidance; extend
  the schema deliberately if phase evidence is supported.
- More Ciri/Blood-and-Wine endings require their own reviewed targets; do not assemble a "best
  endings" list from memory.
- A target can stay `not_guided_yet`; that is a valid shipped state.

### Step 6 - Add reviewed exclusivity, not guesses

`data/exclusive.json` is empty, so `max_achievable` is not reduced today. Add an edge only when a
choice or phase file proves one goal closes another, with `a`, `b`, `kind`, `reason` and evidence.
Then show the tradeoff before applying a conflicting preset. A missing edge is better than a
fabricated one.

### Step 7 - Verify against real saves

- Use `--cards` and `py tools/cards.py ownership` on several saves, including one with a missing
  collection block. `unknown` must stay unknown.
- Use the 500+ save corpus to test a candidate card window: ownership after the closing event is
  evidence against the window.
- Add Rust fixtures for `settled` and `impossible` target states; already covered for the state
  function, but keep a full payload test.
- Do not hard-code any save name, save path or card ownership into shipped data.
- If a real save has the target facts, use it as evidence; the current 120-newest sample did not.

## 5. Rules that must not regress

- No wiki prose or wiki JSON is loaded. `data/audit_*.json` and `data/guide_*.json` stay on disk,
  unused.
- No spoiler text in the default `get_view`/`get_detail` payload.
- A tick never overrules the journal or a fired cutoff.
- `LOST IN THIS SAVE` only when the journal/ownership actually says lost; `CUTOFF PASSED - CHECK
  NOW` is not `lost`.
- Every warning names its file/fact evidence in the collapsed **Technical details**, not on the card.
- A card with unreadable ownership is `unknown`, not `not owned`.
- `max_achievable` never exceeds `total`; `done + available + at_risk + lost + excluded <= total`.
- Every shipped card has a name and a source or an explicit `unknown source`.
- Presets are explicit target-id sets; no hidden computed mode.

## 6. Commands to finish a release

```
py tools/questindex.py build --all
py tools/branchgen.py build
py tools/cards.py check
py tools/cardwindows.py check        # new, if that tool is added
py tools/endings.py check --release
py tools/regen.py --check
py tools/contradictions.py
py tools/test_endings.py
cargo test
```

Then build the UI, verify these payloads from the packaged exe's own `data/`:

```
Witcher3MissablesTracker.exe --view view.json
Witcher3MissablesTracker.exe --detail q704bfairyland detail.json
Witcher3MissablesTracker.exe --cards cards.json
Witcher3MissablesTracker.exe --targets targets.json
```

Finish with `.\package.ps1 -Bump minor` (1.1.x -> 1.2.0), confirm the zip contains every new data
file, and check the packaged exe reads its own `data/` without the checkout.

## 7. Prompt for a new chat

Copy this into a new chat:

> Work in the Witcher 3 Missables Tracker at
> `C:\Steam\steamapps\common\The Witcher 3\w3tracker`.
>
> Read, in this order: `docs/PLAN-1.2-card-deadlines.md`, `docs/PLAN-1.0-completion.md`,
> `docs/TARGET-SCHEMA.md` and `docs/RELEASE-1.0.0.md`. Implement milestone 1.2: turn the
> Gwent card ledger into real card deadlines, but only where the game files and the save corpus prove
> a deadline. Start with a `cardwindows` candidate/review report; do not write `missable` rows from
> guesses. Then ship the reviewed windows through `gwent_cards.json`, `cards.rs` and the card UI, and
> keep the existing spoiler gate, journal-over-tick rule, ownership rule and 0.2.2 cutoff evidence
> rule intact.
>
> Resolve the `All Gwent cards` preset conflict explicitly between the old plan and
> `TARGET-SCHEMA.md`; do not silently add a computed target. Do not add wiki text or hard-code
> anything from one save. Keep `py tools/regen.py --check`, `py tools/contradictions.py`,
> `py tools/test_endings.py` and `cargo test` passing, verify the payloads in a browser, and finish
> with `package.ps1 -Bump minor` so the packaged exe reads its own new data. Report the measured
> number of proven windows, and say honestly if it is zero.
