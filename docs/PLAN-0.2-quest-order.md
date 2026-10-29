# Plan 0.2 — a quest order built only from the game's files

**This revision replaces the 2026-10-28 draft.** It keeps the draft's design intention and screen
target, and corrects what the pre-execution review found: the quest scope was base-game-only, 32
entries have no `type`, the route regeneration would drop its manual steps and events, and the
"what can I still lose" half had no game-file source at all. The new step 0 is the quest graph that
the top section and DO NEXT both need.

**Scope at a glance:** 405 `CJournalQuest` entries on this install — 283 base and 122 DLC, not 283
total. Two are `biddebug*`, so the route is **403 quest steps** plus **11 manual steps** = **414 route
steps**. The five sections hold 403 quest steps; with the 11 manual steps they hold 414 route steps. The journal total is 405, including the 2 excluded debug entries.

Every number below was measured on this install: tracker
`C:\Steam\steamapps\common\The Witcher 3\w3tracker`, REDkit data
`F:\SteamLibrary\steamapps\common\The Witcher 3 REDkit\r4data`, saves
`C:\Users\Desktop-Isac\Documents\The Witcher 3\gamesaves`.

## 0. Design intention

**The app answers one question: "what do I do next in this save, and what can I still lose?"** It is
not a walkthrough, not a wiki, and not a completion tracker. Everything below follows from that.

| source | what it is allowed to decide |
|---|---|
| the game's own files | every rule: what a quest is, when it starts, what it switches off, what it costs, its level and category |
| your save | every fact about where you are: statuses, objectives, choices taken, facts set |
| the app itself | only order: what to look at first |

The rules, in the order they matter:

1. **No second-hand knowledge.** Every shipped sentence has a `source` that is one of: a game-text
   locId, a named file mechanism, or a save status. The wiki JSON and the 25 legacy events stay on
   disk, are never loaded, and exist only as comparison material. A claim without a source does not
   ship. The 11 manual steps are the one exception: they are the user's own bookkeeping, not a claim
   about the game, and they carry no warning.
2. **Only what changes a decision.** A line exists while acting on it can still change the outcome.
   The moment the save settles it, it disappears - a warning about something already done is noise,
   not care.
3. **Silence is a valid answer.** Nothing to warn about means an empty screen, not a reassuring
   message.
4. **Your word is not evidence.** A tick is bookkeeping. It can mark done what the save cannot see
   (manual steps with no journal file); it can never overrule the journal or a fired cutoff. Where
   they disagree, the app shows the disagreement instead of picking a side - it does not go quiet.
5. **No spoilers.** Say that a choice changes the outcome, never which choice or what follows. Name
   the quest that ends a resource, never the plot reason. Choice text, recommended options and
   outcome summaries never ship.
6. **Traceable, not chatty.** Every claim can be opened to the file, fact, locId or phase block behind
   it. That detail lives in the detail pane, not on the card.
7. **The screen is one column of urgency.** Lose-it-now at the top, what to do next under it, progress
   last.
8. **Universal by construction.** Data is keyed on quests and journal entries, not on anyone's save.
   The 517 saves are a test corpus - a claim that only holds for them is a failed claim.

Rule 4 is already shipped in 0.1.9: the journal wins, the disagreement is stated, and
`a_tick_never_silences_a_cutoff_the_journal_still_shows` is its regression test. The statuette pair is
the test case, not a 0.2 change.

## 1. What the app does today (0.1.9)

**Screen order** (`ui/index.html`): alerts → `QUEST ORDER` (feed, 5 items) → `HOLD OFF` → `DO NEXT` →
`PROGRESS`.

**How DO NEXT is ordered** (`src/main.rs`, `todo_order`): the quest tracked in your log is hoisted to
the top, then everything else in route order as hand-written in `data/route.json`. Level never sorts;
the level chip is decoration.

**What the route is**: 135 steps in 8 hand-named regions. 91 carry a hand-written "DON'T MISS" note,
117 a hand-typed level, 11 are manual ticks with no journal file, 5 are optional, 4 carry `when`
conditions, 3 are conditional, 4 user flags exist, and 1 `prefs` entry recommends an order.

**Still hand/wiki research reaching the screen**: `data/guide_1..4.json` (52 entries) and
`data/audit_1..4.json` (260 quest entries) in the detail pane; the route's notes, levels and region
names; `start` (wiki prose); `kb`/`guide` blocks; `choices[].text` in the detail pane; and all 25
hold-off events carry `"src": "wiki: ..."` with no `verified: true`.

**Already game-file derived**: quest-log names, objective lists, dialogue choices, the block that adds
a journal entry (98 of 135 steps), and the reviewed cutoffs with their mechanism (`data/derived.json`,
135 steps / 99 with objectives / 79 with choices; 2 `watch` entries, both the one reviewed statuette
cutoff). `data/cutoffs.json` has 1 reviewed item and 1 pending.

**Ticks are already journal-first** (0.1.9): a tick fills a gap, but a ticked step whose journal still
reads `Active` keeps its warning and says `You ticked ... done, but the journal still has it open`.
The card still reads `Done`; the remaining 0.2 work is the `tick disagrees` chip, not the rule.

**Saves are used for verification only** - `tools/contradictions.py` against all 517. A typical save
has 57 quest-level `Active` entries (53 after removing seven aggregate containers); only 9 of the
current route's 136 stems are Active. 424 distinct quest stems appear across the corpus.

**What that means**: the top section is one reviewed cutoff plus 25 wiki-sourced events. DO NEXT is
135 hand-ordered steps. Neither is a model of where the save is in the game.

## 2. What the game's files actually carry

| need | source | measured |
|---|---|---|
| quest set | `CJournalQuest` in `gameplay\journal\quests\**\*.journal` and the DLC journal folders | **405**: 283 base + 122 under `dlc\ep1`, `dlc\bob`, `dlc\dlc*` |
| section | `CJournalQuest.type` | 62 `Chapter`, 189 `Side`, 35 `MonsterHunt`, 87 `TreasureHunt`, **32 none** |
| untyped fallback | journal id family, `baseName`, folder; reviewed | **30 of the 32 are main-story entries**, including q001, q002, q110, q111, q210preparations, q310preparationsnovigrad, q401_konsylium, q402 Isle of Mists, q403 Battle of Kaer Morhen, q501-q505, ch1quest, all HoS q601-q605, and B&W q701/q702/q705ceremony; the other 2 are `biddebug*` and are excluded |
| suggested level | the six `quest_levels.csv` files | 401 rows, **385/405** matched by normalised `baseName` (277/283 base, 108/122 DLC); 20 unlevelled, of which 2 are the debug entries and 18 are route quests |
| order | `CJournalQuest.order` | present on every entry, but **not a story sequence** (see 2.2) |
| one-line description | lowest-order `CJournalQuestDescriptionEntry.description` locId | one entry per phase, not one per quest (see 2.3) |
| "there is a choice here" | scene choice rows that set facts or are one-shot | 2,701 choice rows / 541 fact-setting / 66 one-shot in the draft's base measurement; re-measure over 405, do not carry the base-only 63 as a target |
| "Gwent here" | the quest's own objective text | **10 quests**: every `cg*` entry, `q302mafia`, `sq306maverick`; `mq7001restinpeace` is excluded by review. Gwent is not a `type`; plus 1 manual step = 11 Gwent nodes |
| start gate | `activators` (`CJournalQuestBlock` / `CJournalQuestTrackBlock`) and `gate_index.json` | 98/135 route steps have an activator; 6,208 activation rows. No activator does **not** mean "cannot start" - dialogue/script starts exist |
| fact gate | set/test facts in phase files and scenes | `quest_index.json` `facts`, `hard_facts`, `fact_index.json` |
| loss edge | story-phase `CDeactivateSpawnset` / community switch | `cutoffs.py` pool; **1 reviewed** cutoff, 1 pending |
| hold-off event | currently hand-written | **25 events, all `src: wiki`, 0 `verified`** |

### 2.1 The route unit

405 is not a synonym for "playable quests". It includes 87 `TreasureHunt` entries, many of them map
POIs (`ep1poi*`, `bara*`, `san_a*`, `plegmundpoi*`, `lw_*`), plus 2 debug entries and 32 untyped
entries.

The route is therefore:

- **403 quest steps**, one per `CJournalQuest`, excluding the 2 `biddebug*` entries.
- **11 manual steps** kept as bookkeeping (the prologue tutorial, the pre-Isle check, the Ciri
  dialogue choices, the Shani/Shakeslock visit, the Vegelbud Gwent matches, etc.). They have no
  journal file and carry no warning; they are the only steps the save cannot show.
- **414 route steps total.** The check is 403 quest steps + 11 manual steps, not "step count = 405".

`TreasureHunt` and `Gwent` steps are **section-only**: they appear in PROGRESS and their own sections,
but do not enter DO NEXT unless they are the tracked quest or missable. This is what keeps the app
from becoming a map-icon completion tracker while still covering every quest.

`data/quest_sections.json` is the reviewed fallback for the 30 untyped main-story entries. It records
one row per stem with a `reason` (`id family`, `journal text`, `parent group`) and is checked by
`routegen`. It is not the game's own `type`; it exists only where the game omits one. The 3 Ciri
manual steps (`ci_c1`, `ci_c2`, `ci_c3`) are rewritten to spoiler-free bookkeeping ("A choice in
<quest> changes the ending") because their current titles contain the choice and a recommended
option.

### 2.2 `CJournalQuest.order` is a sort key, not a story sequence

Counterexamples on this install: `q002griffin` is `3221225470` and sorts after `q301dreamer`
`2583691262`; `q703allforone` is `2683830270` and interleaves with base-game act 2; the values include
`0x2AAAAAAA`-style and `0xFFFFFFFC`-style keys. It is a stable arbitrary tie-break, not play order.
The plan uses it **only** as the last tie-break inside a section. Story sequence comes from the quest
graph (section 3), not from `order`.

### 2.3 The description is a phase summary, not a blurb

`baron` has four `CJournalQuestDescriptionEntry` rows. The draft's example, "The guards at the castle
gate...", is the second (`order 3221225470`); the pre-quest entry is the lowest order
`2684354558` ("Nilfgaard's agent had determined Ciri had stayed with the baron..."). Using the first
row in file order would describe the first step, not the quest.

The card uses the **lowest-order** description, markup stripped, first sentence, clipped to ~120
characters. A test asserts the chosen row is the lowest order and does not contain the current
objective's text.

### 2.4 What the files do not give

- Which quest choices are "good" - the app will only say that a choice exists.
- A start activator for every quest - `unknown` is a valid start state.
- A `type` for 32 entries - the reviewed fallback fills 30; 2 are debug.
- A single description - the lowest-order phase entry is used.
- A story sequence - the graph supplies it.
- A failure edge for every event - the 25 legacy events are replaced only where a file mechanism is
  found; the rest are dropped and reported.

## 3. The missing model: quest graph and frontier

The plan's sources so far describe **what each quest is**. The screen needs **when it becomes
possible** and **when it stops being possible**. Those are the same relation graph:

```
quest --starts--> (activator block | fact | dialogue | unknown)
quest --requires--> (quest done | fact set | reviewed hard edge)
quest --ends--> (resource switched off by a closing quest)
quest --lost_when--> (closing quest | fact | choice fact)
```

`tools/questgraph.py` (new) reads `quest_index.json`, `gate_index.json`, `cutoffs.json`,
`prereqs_review.json`, and `data/legacy_events.json`, and writes `data/quest_graph.json`. The exact
schema is the implementer's choice, but every edge carries `mechanism`, `file`, and `source`. The
graph is generated; the reviewed exceptions live in `data/quest_sections.json` and
`data/route_overrides.json`.

### 3.1 Frontier states

For each step in the save:

| state | rule |
|---|---|
| `done` | journal `Done` / `Assumed` / `N/A`, or a tick that the journal does not contradict |
| `in_log` | journal `Active`, or `Failed` |
| `gated` | not in the log, and the files positively name an unmet quest/fact prerequisite |
| `available` | not in the log, no positively named unmet prerequisite, and an activator is satisfied **or** no activator is known |
| `unknown` | no activator and no positive gate; treated as `available` but flagged in the detail pane |

The conservative rule is the point: a quest is only hidden from DO NEXT when the files name the gate.
"No activator found" never becomes "cannot start". `unknown` is shown, not suppressed.

### 3.2 The next deadline

The top section groups by **closing event**, not by quest. Each group has:

- the closing quest or fact (the thing that ends something),
- the open quests it costs,
- the single action that avoids it,
- the mechanism and file behind it.

The nearest group is the one whose closing quest is `in_log`; then one whose closing quest is
`available`; then one whose closing quest is `gated` (shown as missable, not urgent). This is the
"what can I still lose" answer at the level a player can act on, instead of 25 separate paragraphs.

### 3.3 The 25 legacy events

All 25 current hold-off events are wiki-sourced and unverified. They are moved to
`data/legacy_events.json` (frozen, not loaded) and become the acceptance corpus for the graph: for each
event, the graph either names a `file`/`fact`/`block` that produces it, or the event is dropped and the
loss is reported. The release notes report the replacement count. Nothing wiki-sourced ships in 0.2.
`data/legacy_feed.json` (5 items: 3 `save+graph`, 2 `refuted`) is kept the same way, as
`data/legacy_feed.json`; it is not loaded either.

## 4. Target behaviour

### 4.1 Top section - only what still has a cost

Rendered only when at least one of these is true, and never otherwise (no heading, no placeholder):

1. **Already lost**: a quest `Failed`, or a loss edge that fired while the quest was still open. A tick
   does not hide it; the entry says `you ticked this done; the journal never finished it and the
   cutoff has passed`.
2. **About to lose something**: a closing quest is `in_log` or `available` and the quests it costs are
   still open. The entry names the closing quest and the single action.
3. **Missable and still winnable**: the closing quest is `gated` but reachable, and the protected quest
   is not done. This is the "missable" line; it disappears the moment the save settles it.

Deliberately **not** in this section: anything `settled`, anything `Done`, anything the save has
already answered, and the old `QUEST ORDER` reference notes. The predicate is over the `live` state:
`settled` and `unknown` never render at the top; `lost`, `passed`, `inside`, `missed` and `ahead` do,
with `ahead` as at-risk or missable. Each entry is one sentence, the quest names, the mechanism, and
the action. No corpus statistics, no evidence paragraphs.

### 4.2 Mission card

Under the title, in this order:

1. **Current objective** - the objective the journal has active for that quest in your save, in the
   game's own words (up to 2). When the quest is not started, the first objective from the index.
   When neither exists, show nothing.
2. **One-line description** - lowest-order phase description, first sentence, clipped to ~120
   characters. Same for every player; it never describes the current phase.
3. **Spoiler-free tags**, only where the files justify them:
   - `choice` - the quest has fact-setting / one-shot choice rows. The text is never shown.
   - `Gwent` - the quest's own objectives are about a card game.
   - `missable` - it carries a reviewed loss edge; the mechanism is named in the detail pane.
   - `tick disagrees` - a ticked step whose journal is still `Active`; the card keeps the real state.

What disappears: the hand-written "DON'T MISS" note, `start` wiki prose, `conf` ("quest match"), and
every long explanatory paragraph on the card. Choice text never appears on the card, in the detail
pane, or in the manual step titles.

### 4.3 DO NEXT

Order, strictly:

1. the quest tracked in your log (top, labelled),
2. `in_log` quests that are safe,
3. `available` quests that are safe,
4. `available` quests with a caution tag,
5. never `gated`, never `done`, never `lost`.

Within each group: **nearest deadline**, then **lowest suggested level**, then `CJournalQuest.order`
as the tie-break. Unlevelled quests sort after levelled ones in their group. Gwent and Treasure steps
are not in this list unless they are tracked or missable.

"Safe" means: no closing quest is `in_log`, and no confirmed loss edge has fired. A `near` signal
alone is **not** unsafe - `near` is proximity, not causation (the code and its test already say so).
An unverified proximity becomes a `caution` chip on the card, and the quest stays in DO NEXT unless a
named mechanism makes it unsafe.

The first 4 cards render; the rest collapse behind "show all", as today.

### 4.4 The detail pane keeps the evidence

Clicking a quest opens the long version:

- the mechanism and file behind each loss edge,
- the prerequisite decisions and the fact/file that settles each one,
- the game's objective list, with the current objective marked,
- the `In this save: ...` lines from 0.1.8,
- the start block (`Added to your quest log by X in Y`), not wiki prose.

Removed: `kb`, `guide`, `choices[].text`, `start` wiki prose, and every `sources` URL. The
`BACKEND_CONTRACT.md` is updated accordingly.

### 4.5 Sections

`Main`, `Secondary`, `Contracts`, `Treasure Hunts`, `Gwent` - presented in that order, keyed on the
game's `type` with the 30-entry fallback:

| section | key | current count |
|---|---|---|
| Main | `Chapter` + 30 untyped main, minus the Gwent entries, plus 6 manual | 97 (91 quest + 6 manual) |
| Secondary | `Side` minus the Gwent bucket, plus 4 manual | 184 (180 quest + 4 manual) |
| Contracts | `MonsterHunt` | 35 |
| Treasure Hunts | `TreasureHunt` (POIs marked `minor`) | 87 |
| Gwent | 10 objective-text quests + 1 manual | 11 |
| excluded | `biddebug*` | 2 |

The counts are generated by `routegen` and checked, not hand-maintained. The section column holds 414 route steps (403 quest + 11 manual); the journal total is 405
including the 2 excluded debug entries. A Gwent or treasure quest that
is missable still escalates to the top section as well.

### 4.6 Provenance and no-spoiler checks

- Every shipped claim has a `source`: `{kind: "locid"|"file"|"save", value, file?}`.
- Every top-section item has `mechanism` and `file`.
- Every tag has a source (`choice` -> the choice row file; `Gwent` -> the objective locId; `missable`
  -> the loss edge).
- `--view` and `--dump` contain no `choices` array, no `kb`, no `guide`, no `start` wiki string, and
  no `src: wiki`.
- A test asserts all of the above; a violation fails the build, not just the release notes.

## 5. Implementation order, each step with its check

### 0. Quest graph and frontier (new, before routegen)

First copy the 25 current hold-off events out of the old `data/route.json` into
`data/legacy_events.json`, and copy the old feed to `data/legacy_feed.json`; the old route is then
only a migration input. Build `tools/questgraph.py`. Inputs: `quest_index.json`, `gate_index.json`,
`fact_index.json`, `cutoffs.json`, `prereqs_review.json`, and `data/legacy_events.json`. Output
`data/quest_graph.json` with `starts`, `requires`, `ends`, `lost_when`, and the frontier helpers.

Check:

- for each of the 25 legacy events, a `mechanism`/`file` or an explicit `dropped` row; report the
  replacement count;
- every `lost_when` edge names a mechanism and a file; `contradictions.py` finds no save contradicting
  it;
- for every save, every quest is `done`/`in_log`/`gated`/`available`/`unknown`; no `gated` quest is
  ever in DO NEXT;
- `unknown` is non-empty and is treated as available, never suppressed;
- the statuette cutoff still reproduces `CUTOFF PASSED - LOST IN THIS SAVE` on the ticked profile.

### 0b. Route unit and sections

Add `data/quest_sections.json` (the 30 untyped main entries, the 2 debug exclusions, and the `minor`
POI list) and `data/route_overrides.json` (the 11 manual steps, 5 `opt`, 4 `when`, 3 `conditional`,
4 flags, the 3 rewritten Ciri steps, and the Gwent objective-file exceptions).

Check: 405 journal entries = 403 route quests + 2 excluded; 414 route steps = 403 quest + 11 manual;
every untyped stem has a reason; every manual step has an id and no choice text; Gwent = 11 (10 quest + 1 manual); no
duplicate ids.

### 1. `tools/questindex.py`

- rglob the DLC journal folders, or reuse `saveindex.quest_files()` - the current
  `journal_index()` globs only `gameplay\journal\quests\*.journal`.
- add `type`, `order`, `description` (lowest-order description locId resolved through the string DB),
  `level` (joined from all six CSVs), `has_choice` (fact-setting / one-shot rows), `has_gwent`
  (objective-text match).
- keep the existing `activators`, `facts`, `switches`, `objectives`, `choices`.

Check: 405 entries; 385/405 levelled (list the 20); 0 route quests untyped after the fallback; every
`type` is one of the four values or `None`; description resolves for >90% (list the misses); Gwent = 11 (10 quest + 1 manual);
choice count measured and reported (do not assert 63); no `biddebug*` in the route output.

### 2. `tools/routegen.py` (new)

Write `data/route.json` from `quest_index.json`, `quest_sections.json`, `route_overrides.json`, and
`prereqs_review.json`.

- 403 quest steps + 11 manual steps.
- `id` = journal stem; manual ids unchanged.
- `title` = game title (string DB) or the manual title.
- `section` = the section table; `kind` = `main|side|contract|treasure|gwent|manual`; `dlc` boolean.
- `lv` = CSV or `""`.
- `files` = `[stem]`; for the Gwent steps whose quest-level entry is a placeholder, the old
  objective-level files.
- `hard` / `hard_facts` re-keyed from `prereqs_review.json`; manual targets preserved.
- `by` = loss edges that name the quest; re-keyed.
- `note` omitted only after `Node` gets `#[serde(default)]` (or emit `note: ""`); `conf` dropped.
- `opt`, `when`, `conditional` from overrides; `flags` = 4.
- `events` = graph-derived with `mechanism`/`file`/`verified: true`; `legacy_events.json` not loaded.
- `prefs` dropped (the one rule it encoded is the statuette cutoff; the old text is legacy-only).

Check:

- 403 + 11, no duplicate ids, every section non-empty, every `files` stem in the journal index;
- 25 events either replaced or recorded as dropped; every event has a mechanism;
- every hard edge has a target; 5 `opt`, 3 `conditional`, 4 `when`, 4 flags, 11 manual;
- `derive.py` writes a derived entry for **every** route id; `contradictions.py` asserts
  `route ids == derived ids`;
- `py tools/contradictions.py` reports 0 contradicted claims and 0 disputed prerequisites;
- `py tools/regen.py` is byte-identical.

### 3. Widen the reviewed cutoffs

Run `cutoffs.py` over all 403 route quests. Keep only candidates whose mechanism is a
`CDeactivateSpawnset`/community switch naming a resource another quest references, and require the
saves not to contradict them. `data/legacy_events.json` and `data/legacy_feed.json` are the frozen
copies made in step 0; do not ship them.

Check: every shipped cutoff names its file mechanism; `contradictions.py` passes; the count is
reported honestly in the release notes (no promised number); the 25-event replacement report is
included.

### 4. `src/model.rs`

- the frontier states and the DO NEXT order of 4.3;
- the top section of 4.1, including hiding it when empty and excluding `settled`/`unknown`/`Done`;
- the `tick disagrees` chip (the journal-first rule is already 0.1.9);
- the spoiler-free tags and the provenance fields.

Check (`cargo test`):

- tracked first; `in_log` before `available`; safe before caution; level ascending; `order` only as
  tie-break; `gated` never in DO NEXT;
- empty top section renders nothing; `settled`/`unknown`/`Done` never render at the top;
- a ticked step whose journal is open and whose cutoff has fired appears at the top with the
  disagreement;
- `unknown` start is available, not suppressed;
- no `choices`/`kb`/`guide`/`start` in the view;
- every top item has `mechanism`/`file`.

### 5. `ui/`

Order becomes top section → DO NEXT → PROGRESS. Remove `QUEST ORDER`, `HOLD OFF`, and the separate
alerts section; the top section is the only list-level alert surface. The card shows the current
objective, then the description, then the tag chips. The detail pane shows evidence only.

Check: render `ui/` against `--view` for early, mid, and epilogue saves, plus one save for each top
state (lost, at risk, missable, empty); no console errors; no choice text in the DOM.

### 6. Remove the wiki path and update the documents

- Remove the `audit_*`/`guide_*` loader from `src/main.rs`, the `kb`/`guide`/`choices`/`start` fields,
  and the copy from `package.ps1`.
- Remove the `feed` loader and keep the frozen copy as `data/legacy_feed.json`.
- Keep `data/audit_*`, `data/guide_*`, `data/legacy_events.json` and `data/legacy_feed.json` on disk
  for comparison; never load them.
- Update `docs/BACKEND_CONTRACT.md` (no `kb`/`guide`/`choices`/`start`/`feed`/`holdoff`/`alerts`).
- Update `README.md` ("No game data is shipped" is false while `derived.json` ships 3.5 MB of game
  text; either generate descriptions at runtime or say exactly what ships), `NOTICE.txt`, and
  `LICENSE-DATA.md` (name `derived.json`, `cutoffs.json`, `quest_graph.json`, `legacy_feed.json`,
  `prereqs_review.json` and their provenance).
- Update `package.ps1` to copy `quest_graph.json` and `quest_sections.json` if the app needs them at
  runtime; drop `guide_alias.json`. `route_overrides.json` is a build input, not runtime data.
- Rewrite the 3 Ciri manual steps to spoiler-free bookkeeping.

Check: the app starts with the wiki files present and never mentions them; `--view` contains no wiki
string and no choice text; a `tools/compare_legacy.py` one-shot prints where the old notes/events
disagree with the graph.

### 7. Package 0.2.0

`.\package.ps1 -Bump minor`, then confirm the packaged exe with `--view` over the same saves and each
top-section state, reading its own `data/`. The release notes report the measured counts: 403 route
quests (405 journal entries, 2 debug excluded), 385 levelled, 30 fallback, 11 manual, N legacy events
replaced, N cutoffs reviewed.

## 6. Not in scope

- No new wiki or guide text, and nothing that describes one save's history.
- No spoilers: no choice text, no outcome, no "pick X" - only "there is a choice".
- The save reader and the status rules stay as they are.
- No hard-coded per-save or per-profile claims.
- No POIs or Gwent matches in DO NEXT except the tracked quest or a missable one; they remain
  section-only by default.

## 7. Decisions

| # | question | answer |
|---|---|---|
| 1 | route scope | **403 quest steps (405 journal entries, 2 debug excluded) plus 11 manual steps** |
| 2 | wiki files | **kept in `data/`, no longer read**; the 25 legacy events and 5 feed items are frozen too |
| 3 | top section | already-lost + about-to-lose + missable-still-winnable; never `settled`/`unknown`/`Done` |
| 4 | summary | **current objective first**, then the lowest-order description, plus `choice`/`Gwent`/`missable`/`tick disagrees` tags |
| 5 | Gwent / Treasure Hunts | **own sections**, section-only in DO NEXT; escalate to the top when missable |
| 6 | tick vs journal | **journal wins**; 0.1.9 already does this; add the disagreement chip |
| 7 | untyped quests | **30 main-story fallback entries** in `data/quest_sections.json`, 2 debug excluded |
| 8 | `CJournalQuest.order` | **last tie-break only**; it is not story order |
| 9 | "what can I still lose" source | **quest graph** (`starts`/`requires`/`ends`/`lost_when`), not the 25 wiki events |
| 10 | failed/unknown starts | **`unknown` is available and flagged**; never suppress a quest the files do not gate |
| 11 | provenance | every shipped claim has a `source`; a claim without one does not ship |
| 12 | manual steps | **11 kept as bookkeeping**; the 3 Ciri steps are rewritten with no choice text |

## 8. Prompt for a new chat

> In the Witcher 3 Missables Tracker at `C:\Steam\steamapps\common\The Witcher 3\w3tracker`, implement
> plan `docs/PLAN-0.2-quest-order.md` end to end, following its section order and its acceptance
> checks. Read that file first: it records the 405-journal-entry scope (403 route quests, 2 debug
> excluded, plus 11 manual steps), the type fallback for the 30 untyped main-story entries, the route
> preservation rules, and the quest-graph/frontier step.
>
> The outcome: everything the app shows about quests comes from the game's own files. The route covers
> 403 quests including Hearts of Stone and Blood & Wine, plus the 11 manual steps, sectioned by the
> game's own type with a reviewed fallback; the wiki JSON, the 25 legacy events and the 5 feed items
> stay on disk but are never loaded.
>
> The screen becomes: a top section that exists only when something still has a cost - a loss that
> already happened, a closing quest about to cost an open quest, or a missable quest that is still
> winnable - grouped by the closing event and silent otherwise. Then DO NEXT: the tracked quest first,
> then in-log, then available, safe before caution, nearest deadline then lowest level then the
> game's sort key; gated quests never appear. Each card shows the current objective, a one-line
> description from the lowest-order phase entry, and only spoiler-free tags. No choice text, no wiki
> prose, no per-save hard-coding.
>
> Use the existing toolchain (`tools/questindex.py`, `tools/questgraph.py`, `tools/cutoffs.py`,
> `tools/derive.py`, `tools/prereqs.py`, `tools/routegen.py`) and keep its checks passing:
> `py tools/contradictions.py` with 0 contradicted claims and 0 disputed prerequisites,
> `py tools/regen.py` with all outputs byte-identical, `cargo test`, and the route-preservation and
> derived-coverage checks. Verify the UI against a `--view` payload for early, mid, and epilogue saves
> plus each top-section state, and the packaged exe over the same saves. Finish with
> `.\package.ps1 -Bump minor`, which must leave the newest exe in the tracker folder as well as a new
> zip in `dist/`.
