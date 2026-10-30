# Witcher 3 Missables Tracker

A small always-on-top Windows tool that reads your newest Witcher 3 save (read-only) and answers one
question: **what do I do next in this save, and what can I still lose?**

- **NOW**: a sticky band that appears only while an action can still change the outcome - a loss
  that already happened, a story event that would fail a quest you still have open, a choice that
  matters to the endings in play, or a missable quest or card window you can act on now. A card
  window that is still ahead is not a warning and never enters the band; it is a row in
  **MORE > CARDS > LATER**. When nothing is at stake the band disappears.
- **UP NEXT**: only what you can act on now - the quest you are tracking, quests already in your
  log, and the one plan step that is next. Future goal steps sit under one collapsed **PLAN
  AHEAD** line; unlocked route steps that are not in your log stay in PROGRESS. A plan step and a
  quest are one card, never two. The exact line appears only on the tracked goal step, and turning
  guidance off removes the line without removing the plan.
- **MORE**: the reference drawer, with tabs.
  - **STATUS**: quest and card completion, split into done/owned, still possible, at risk, lost and
    unknown - never one misleading percentage.
  - **CARDS**: every card with source, owned/not-owned/unknown and one reviewed window: 15 Tier B
    community windows, 17 Tier A one-time sources, or a documented no-window reason. A deck list
    is not ownership, so 24 cards carry an explicit unknown-source row rather than a false
    no-window claim. Filters are open now, later, owned and unknown. Tier B rows show their source
    and review date.
  - **COVERAGE**: measured counts per pack, so an empty section is not mistaken for a clean one.
  - **PROGRESS**: every quest in the game, including Hearts of Stone and Blood & Wine, in the game's
    own five sections: Main, Secondary, Contracts, Treasure Hunts, Gwent.
- **Ending goals (optional)**: opt into a reviewed goal (for example, both Blood and Wine sisters
  living) and the matching mission shows the exact line to say. Skip the picker and the screen stays
  spoiler-free; no ending name or line is shown.
- **Can I do this now?**: search any quest and get a safe / careful / not-yet answer.
- Click a quest for its description, current objective and any warning. The source-file trail is
  there too, but folded away under **Technical details** so it does not get in the way.
- **My game**: tell it what a save cannot show (Letho alive, Keira sent to Kaer Morhen, romances) and
  set your game and saves folders if they are not found automatically.

Unofficial fan tool. Not affiliated with CD PROJEKT RED. See `NOTICE.txt`.

## Safety

- It only **reads** your saves. It never writes to the saves folder or the game folder.
- Its own settings (ticks, level, tags, a cached quest index) go to
  `%APPDATA%\Witcher3MissablesTracker`.
- The code contains no HTTP client and makes no network connections. Source links open in your
  browser only when clicked.
- The quest index is built on your computer from your own game files. No game data is fetched at run
  time.
- You can read everything in `src/` (a few thousand lines of Rust) and `ui/` (plain HTML/CSS/JS), and
  build it yourself.

## Status and limits

- Developed and tested on the Steam PC version 5.00 (next-gen). Other versions may have different
  quest data.
- The save reading has been checked against 500+ real saves, from White Orchard to the Blood and Wine
  epilogue.
- The route is generated from the game's own journal files and level tables by `tools/questindex.py`,
  `tools/questgraph.py` and `tools/routegen.py`: **403 quest steps** (405 `CJournalQuest` entries
  minus the 2 `biddebug*` entries) plus **9 reviewed manual steps** = **412 route steps**. The 122 DLC
  journals are included. The five sections are generated from `CJournalQuest.type`, with a reviewed
  fallback for the 30 main-story entries that have no type. The 1.0.0 baseline had 11 manual rows;
  [docs/MANUAL-STEPS-AUDIT.md](docs/MANUAL-STEPS-AUDIT.md) records the audit that replaced the two
  exact duplicates (`q108eve` and `q111imlerith`) and kept the other nine labelled `manual_reviewed`.
- **What ships in the release's `data/`**: `route.json` (titles, sections, levels, descriptions),
  `derived.json` (quest-log names, objectives, the activation evidence and the reviewed cutoffs),
  `quest_graph.json` (start blocks, reviewed fact prerequisites, loss edges), the reviewed
  inputs `cutoffs.json`, `cutoff_windows.json`, `prereqs_review.json`, `prereq_relations.json` and
  `route_disputes.json`, and the 1.1 planner data `endings.json`, `outcomes.json`, `branches.json`,
  `gwent_cards.json`, `card_windows.json`, `card_window_review.json`, `coverage.json` and
  `exclusive.json`.
  Those files contain short quest-log names and objective strings read from the author's own game
  install; they are identification and commentary, not a licence to the game's text. The wiki-era
  `audit_*.json`, `guide_*.json`, `guide_alias.json`, `legacy_route.json`, `legacy_feed.json` and
  `legacy_events.json` stay in the checkout as comparison material and are **never loaded by the app**
  (see `LICENSE-DATA.md`).
- **Cutoffs are file claims, and a community switch alone is not one.** A `CDeactivateSpawnset`
  only says an actor left a scene. The review rejects a candidate when the affected quest starts
  *after* that switch (Haunted House is activated by `q311_after_q301_dreamer_godling_house.w2phase`,
  after Novigrad Dreaming), when the affected quest's own phase switches the actor back on for its
  turn-in (the statuettes do this with `q310_ap_triss_dandelions`), and when nothing ever marks the
  quest failed - neither a save nor a connected `Failure` input in its own phase graph. One reviewed
  community cutoff ships (Brothers in Arms before The Isle of Mists, where two saves actually mark an
  ally quest `Failed` after the Isle) and one reviewed journal window (the statuettes, resolved when
  `q210preparations.journal` - Battle Preparations - starts, because the game's own failure branch
  is gated by that journal). The 25 hand-written 0.1.9 events are frozen in `data/legacy_events.json`:
  one is replaced by a file edge, 24 are dropped with their reason recorded. The count is reported
  honestly in the release notes, not promised.
- **Route prerequisites are settled, not asserted.** Five reviewed edges keep the lock but test the
  fact the game actually gates on; four are dropped because the saves show the two quests run
  alongside each other. `data/prereqs_review.json` records each decision and `tools/prereqs.py`
  re-checks it on every run. `data/route_disputes.json` is empty unless something new disagrees.
- **Every warning is answered by the save you have loaded.** The app names what is lost and which
  quest caused it, then looks those up in your journal on every refresh: `LOST IN THIS SAVE` (only
  when the journal marks the quest `Failed`), `CUTOFF PASSED - CHECK NOW` (the event has happened
  but the journal still has it open), `DO THIS NOW`, `MISSABLE`, or nothing at all once the save has
  settled it. A warning about something already done is never shown.
- **Your ticks fill gaps, they do not overrule the journal.** A tick is a note beside the save
  state, not a status. On a manual step it is the answer, because the save cannot show that step at
  all. On a file-derived step the card, the matrix and the warning keep the journal's answer, and a
  tick that disagrees is shown as `noted, not confirmed` rather than as a green done check.
  Otherwise a tick could hide a loss that has already happened.
- **No spoilers.** The app says that a choice changes the outcome, never which choice or what
  follows. Choice text is not shipped in the route, the view or the detail pane. Quest names, the
  closing quest of a cutoff, and the fact that a loss occurred are shown because they are the thing
  you can act on.
- The in-game quest log has the final word.

## The 1.1 planner

- **Goals are reviewed, not ranked.** `data/endings.json` names the goal, the facts it needs and the
  exact reviewed line from the extracted scene. The app never calls one ending "best"; the
  `Recommended endings` preset is a reviewed preference, not a game ranking.
- **The default payload is spoiler-free.** `get_view` has no target label, ending name or choice
  text. A target line reaches the detail pane only after the user opens the goal picker and selects
  that target. Clearing the target removes the label and line again.
- **Goal states are save facts.** A goal is `settled` only when the save has its facts, `reachable`
  while the deciding step is still ahead, `impossible` when the deciding step is already behind, and
  `unknown` when the save or branch data cannot decide. A journal that still has the step open wins
  over a tick.
- **The run plan is playable order.** Steps are sorted by suggested level, then by the route's own
  index. A step that is already settled is dropped from the visible route; a confirmation step names
  the phase fact instead of inventing a dialogue line. Conflicting or unguided goals block the plan
  rather than being merged into one route.
- **Card ownership is separate from quest completion.** The save's collection block is authoritative;
  a card the save cannot show is `unknown`, never silently "not owned". Manual ticks fill only what
  the save cannot see.
- **Card windows are reviewed, not guessed.** 15 cards have a Tier B community closing window with
  a named source and date; 15 more are Tier A one-time sources; the other 194 have a documented
  no-window reason (187 Tier A, 7 explicit unknown-source rows). No Gwent quest failure is turned
  into "every card in it is missable". See [`docs/CARD-WINDOWS.md`](docs/CARD-WINDOWS.md).
- **"All quests" means the maximum consistent set.** The route has 403 quest steps; mutually
  exclusive branches cannot all be completed in one save, and the planner reports the achievable set
  instead of claiming 100% of every branch.
- **Where the new data comes from.** `data/branches.json` is generated from scene choice rows;
  `data/gwent_cards.json` from card definitions plus reviewed sources; `data/coverage.json` from the
  measured extraction; `data/outcomes.json` is the reviewed terminal matrix (11 outcomes in four
  one-of groups, four guided goals); `data/exclusive.json` is the reviewed outcome-exclusion set.
- **What is not modelled.** Hearts of Stone has no Gwent card pack. A Blood and Wine card's random
  merchant reward may name the script but not the merchant; that is shown as `unknown source` rather
  than guessed.

## Checking the warnings yourself

The rules above are meant to be re-derivable, not taken on trust. `tools/README.md` documents the
pipeline; the short version is:

```
py tools/regen.py             # rebuild every data file from your install and compare the hashes
py tools/contradictions.py    # test every claim against every save; must report 0 contradicted
py tools/prereqs.py check     # re-decide every prerequisite and re-test the settled ones
py tools/compare_legacy.py    # where the frozen 0.1.9 route notes and 25 events disagree
py tools/fuzz.py              # damaged files must not be misread
py tools/outcomecheck.py --release  # terminal facts, exact lines, journals and exclusion edges
py tools/exclusivity.py --check     # accepted edges and the rejected candidate report
cargo test
```

To see what the app itself computed, run the exe with `--dump out.json` (state, statuses, top
section), `--view out.json` (exactly what the window is handed), `--detail <quest id> out.json`
(one mission, including any goal line), `--cards out.json`, `--targets out.json`, `--outcomes
out.json` or `--plan out.json [id,id]`; all exit without opening a window. `--outcomes` and `--plan`
are the headless forms of the two spoiler-gated commands. `docs/RELEASE-1.1.0.md` records what was
verified for this release and what is still open; `docs/RELEASE-1.0.0.md` is the historical 1.0
record.

## Use of AI and sources

The program code was written with AI assistance (Anthropic Claude) under the author's direction; the
author tested it. The 0.2 route, sections, levels, descriptions, start blocks, fact prerequisites and
cutoffs are generated from the game's own files. The older wiki research in `data/audit_*.json` and
`data/guide_*.json` was compiled with AI-assisted reading of public sources, mainly The Witcher Wiki
(CC BY-SA 3.0) and public walkthroughs; it is kept for comparison and no longer reaches the screen.
Details: `NOTICE.txt` and `LICENSE-DATA.md`.

## Build from source

Requires Windows 10/11, [Rust](https://rustup.rs) and the Visual Studio C++ build tools. Microsoft
Edge WebView2 is needed at run time (part of Windows 11).

```
cargo build --release
```

`package.ps1` builds, assembles and zips a release, and strips local paths from the binary. To check a
downloaded build, build from the matching source and compare behaviour; the code is small enough to
read.

## Layout

| Path | What it is |
|---|---|
| `src/save.rs` | Save reader (LZ4 chunks, name table, quest journal). Read-only. |
| `src/bundles.rs` | Finds the game and builds the quest index from the player's own game files. |
| `src/model.rs` | Route engine: frontier, prerequisites, cutoffs, UP NEXT order, tags, safety check. |
| `src/main.rs` | App, settings, NOW warnings, commands. |
| `ui/` | Interface (HTML/CSS/JS, no build step). |
| `data/route.json` | The generated route: 403 quest + 9 manual steps = 412, sections, prerequisites, events, and the manual audit. Regenerate, do not hand-edit. |
| `data/derived.json` | What the game's own files say per step (names, objectives, activators, cutoffs). Generated. |
| `data/quest_graph.json` | Start blocks, reviewed fact prerequisites, reviewed loss edges. Generated. |
| `data/cutoffs.json` | The reviewed community cutoffs and journal windows - the only ones that become warnings - each naming its mechanism. Generated. |
| `data/cutoff_windows.json` | Reviewed journal-failure windows (the statuettes are resolved when Battle Preparations starts), validated against a connected Failure input and the closer's own journal. |
| `data/prereqs_review.json` | The settled prerequisite decisions (keep on the game's fact, or drop) with their evidence. |
| `data/route_disputes.json` | Prerequisites the saves still disagree with. Generated by the contradiction harness. |
| `data/quest_sections.json` | The reviewed section fallback for the 30 untyped main-story entries, and the 2 debug exclusions. |
| `data/route_overrides.json` | The 9 kept manual steps and the 2 replacements, optional/conditional flags, the four user flags, and the Gwent file exceptions. |
| `data/audit_*.json`, `data/guide_*.json` | Frozen wiki-era research. Kept for comparison; never loaded. |
| `docs/BACKEND_CONTRACT.md` | Interface between the backend and the UI. |
| `docs/DESIGN.md` | What the tracker is for, and the one question every change has to pass. |
| `tools/` | The scripts that generate and check the route (read-only). |

## Contributing corrections

Wrong prerequisite, wrong section, or a cutoff I missed? Open an issue with the quest, what the tool
said, what the game did, and roughly where you were. Corrections belong in the reviewed input files
(`data/quest_sections.json`, `data/route_overrides.json`, `data/prereqs_review.json`,
`data/cutoffs.json`), then `py tools/regen.py --update`; edits to the generated `route.json` are
overwritten.

## Licences

Code: MIT (`LICENSE`). Game-derived data: see `LICENSE-DATA.md`. Legacy wiki research: CC BY-SA 3.0
(`LICENSE-DATA.md`). Bundled libraries: `THIRD-PARTY-LICENSES.txt`.
