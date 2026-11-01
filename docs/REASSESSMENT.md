# Reassessment, 2026-11-01

Where the tracker stands, what the new game database changes, and the ranked plan. Nothing in the
app has been changed yet: Phase 5 (execution) starts only after this plan is approved.

## Baseline

- The uncommitted 1.4.0 working tree is committed on branch `wip/1.4.0` and tagged
  `reassess-baseline`. Work continues on branch `reassess`.
- `.next-phase/reassess-baseline/view.json` is the app's `--view` dump of the newest save at that
  point (The Isle of Mists, tracked).

## What was built

`tools/gamedb/` turns the game's own editor data, the string database and the saves into one SQLite
database and LLM-readable views. See `docs/DATABASE.md` for every table. In short: 1,040 quest graph
files (288k nodes, 249k connections), 1,442 journal files (403 quests, 3,301 objectives), 6,222
dialogue scenes (7,771 choices), 408 item/loot/Gwent XML files, and all 523 saves. A full rebuild
takes about three minutes.

`tools/cr2w.py` gained one decoder: `CVariant` (script block parameters), so facts set or removed by
script blocks (`RemoveFactQuest`, `TryToAddUniqueFact`) are now readable. The older pipeline's
golden hashes (`tools/regen.py`) may change because of it; that pipeline is retired by this plan.

## What it shows

### Cutoffs: the old method saw a fraction

The shipped app knows 3 cutoff families (`data/cutoffs.json`: Brothers in Arms, and the two
statuette windows). It accepted a cutoff only when an NPC community was switched off, or after a
hand review. The game itself wires losses as journal `Failure` inputs fired by facts and journal
conditions, and the database reads all of them.

- **The Isle of Mists** fails 16 quests, not 4: the four Brothers in Arms quests, and, through the
  fact `q402_escort_completed`, A Dangerous Game, A Deadly Plot, A Favor for a Friend, A Matter of
  Life and Death, An Eye for an Eye, An Invitation from Keira Metz, Cabaret, Ciri's Room, For the
  Advancement of Learning, Now or Never, Redania's Most Wanted and Return to Crookback Bog.
- **Statuettes**: the database finds the reviewed window independently (Battle Preparations, a
  journal-status condition three steps from the statuettes' `Failure` input), plus a later hard
  close at On Thin Ice (`q501_naglfar_arrived`).
- Across the game, 88 quest-level loss relations (`fails`, `fail_when_fact`, `fail_when_journal`)
  plus 8 inverted ones (`fail_unless_fact`).

### Checked against the saves

`py tools/gamedb/oracle_check.py`: of 61 fact-triggered loss claims within 6 graph steps, 1 is
confirmed by a save (The Gangs of Novigrad lost once `q302_whoreson` is set), 2 are contradicted,
58 are untested. Untested is expected: one player who finishes quests before their cutoff never
records the loss. The two contradictions (Brothers in Arms: Velen and Nilfgaard against
`q109_keira_to_km`) sit on a failure path that needs several conditions together; the backward walk
does not yet evaluate AND/OR logic. Two earlier rounds of contradictions were real bugs and are
fixed: connections were read in both directions, and objective failures were counted as quest
losses.

### The current objective is in the save

Every save stores the game's own highlighted objective, `JHighlightedObjective`, next to the
tracked quest (`JTrackedQuest`, which the app already reads). In the six newest saves it reads
"Travel to the Isle of Mists.", "Follow the firefly." and "Look for Ivo in the cave.", which is
exactly the line under the quest name in the game's HUD. The app instead lists every journal
objective still marked active, and the game leaves stale ones active: the baseline dump shows 13
objectives for The Isle of Mists and old ones such as "Find out if Ciri is in Velen." for other
quests. That is the source of the extra fragments.

### Why the app stops updating

The save watcher (`src/main.rs`, the thread in `setup`) and all 18 commands take the state with
`lock().unwrap()`. Any panic inside a command while it holds the lock poisons the mutex; from then
on the watcher thread panics on its next `lock().unwrap()` and exits silently, and every command
fails. The app keeps showing the last view and never reads a new save. There are 95 `.unwrap()`
calls and 7 `expect`/`unreachable!` in `src/`, so a rare input (an odd save, a detail page for an
unusual quest) is enough after a long session. The release profile unwinds, so nothing is logged.
This is the leading hypothesis; the fix below includes a soak test that would show it.

### The repo

| area | state | proposal |
|---|---|---|
| `data/audit_*.json`, `guide_*.json`, `guide_alias.json` | wiki-era, read by nothing | delete (in git history) |
| `data/legacy_*.json` | read only by comparison tools | delete with `compare_legacy.py` |
| `data/cutoffs.json`, `quest_graph.json` (3.6 MB), `derived.json`, `prereq_*`, `route_disputes.json` | live, hand-reviewed output of the old pipeline | replace with data generated from the database, keeping reviewed decisions as overrides |
| `data/branches.json` (1.3 MB) | live (guidance) | regenerate from `scene_choices` + `choice_effects` |
| `data/gwent_cards.json`, `card_windows.json`, `card_window_review.json` | live, reviewed | keep; re-derive sources from `loot_entries` / `reward_items` and diff |
| `data/endings.json`, `outcomes.json`, `exclusive.json` | live, reviewed | keep; check against `choice_effects` |
| `tools/` (68 files, 24 scripts over 14k lines) | the old pipeline, many one-off probes and reports | keep `cr2w.py`, `save_reader.py`, `stringsdb.py`, `paths.py` and the card checks; retire the rest once the database feeds the app |
| `docs/RELEASE-*.md` (22 files), `NEXT-PHASE-PLAN.md` (89 KB), `FINISH-MISSION-PROMPT.md`, `FINAL-REPORT.md` | history | move to `docs/archive/` |
| `.next-phase/` (118 MB), `dist/` (636 MB), `target/` (9.5 GB) | generated | leave ignored; clean `.next-phase/` after the baseline is no longer needed |

## Plan (ranked; each item names its acceptance check)

1. **Watcher survives panics.** Replace every `lock().unwrap()` with poison recovery, run the watch
   loop body under `catch_unwind`, install a panic hook that appends to
   `%APPDATA%\Witcher3MissablesTracker\tracker.log`, and log a heartbeat each minute.
   *Check:* a soak script copies saves into a test saves folder every few seconds for an hour while
   a test build is pointed at it, with one deliberately corrupt save; the log shows a view emitted
   at least every 20 s throughout, and an injected panic is logged and survived.
2. **Current objective from the save.** Read `JHighlightedObjective` in `save.rs` (same shape as
   `tracked_guid`) and show that one objective on the TRACKED card; fall back to the newest active
   objective of the tracked quest only when the save has none.
   *Check:* for 20 saves spread over the playthrough, the card's objective equals the text of the
   save's highlighted objective (scripted from `db/w3db.sqlite`), and in-game screenshots for 3 of
   them match.
3. **Database v1.1: condition logic.** Evaluate AND/OR blocks and pause conditions on the path to a
   `Failure` input, so a relation says whether a fact is sufficient or only part of a condition.
   *Check:* `oracle_check.py` has 0 contradictions and the confirmed claim stays confirmed.
4. **Cutoffs from the database.** Generate the app's cutoff data from `quest_relations` (`fails`,
   `fail_when_*`), with `data/cutoffs.json` reduced to reviewed overrides (wording, merges,
   rejections with a reason). Every shipped cutoff cites its file and block.
   *Check:* the Isle of Mists list above appears in the app; the statuette and Brothers in Arms
   windows still appear; `oracle_check.py` clean; a review list of every new cutoff is signed off by
   the user before release.
5. **Cards from the database.** Re-derive each card's sources from `loot_entries` (shops are loot
   tables), `reward_items` and `card_sources`, and diff against `gwent_cards.json`.
   *Check:* every difference is listed and explained; the 224 collectible cards are all accounted for.
6. **Repo cleanup.** Do the table above in one commit per row group.
   *Check:* `package.ps1` still builds, `cargo test` passes, the app's `--view` dump of the baseline
   save is unchanged except for intended items 1-5.
7. **UI faults.** Collect the faults from the user with a screenshot each, reproduce with a `--view`
   dump, fix one per commit.
   *Check:* each fault's screenshot redone after the fix.
8. **Ending choices on the tracked card** (requested 2026-11-01, after items 1 and 2). When the tracked
   quest holds a reviewed ending choice, the card always shows a warning: with guidance on, the exact
   line to say; with guidance off, only that the quest matters for an ending. When the save's
   highlighted objective is the one during which that line is offered, the warning changes state
   (with guidance on, the line itself is highlighted in a different colour): "say it now" rather
   than "coming up". Needs a new database table linking each scene block to the objective that is
   active when it plays (walk back from the `CQuestSceneBlock` to the nearest objective activation),
   joined to the reviewed lines in `data/endings.json` / `outcomes.json`.
   *Check:* for each reviewed ending line, a save taken on that objective shows the "say it now"
   state and a save on an earlier objective shows "coming up"; with guidance off no line text
   appears anywhere.

Execution follows the agreed split: the planner writes the brief and the acceptance check for each
item, a Haiku worker implements it, and the planner reruns the check and reads the diff before it is
accepted.
