# Quest-order analysis toolchain

The scripts that generate this tracker's route from the game's own files and test every claim against the
game files and the saves. Read-only, always: nothing here writes to the game folder or the saves folder.
Derived indexes (`*_index.json`) and reports are written here and are git-ignored; regenerate them freely.

Requires Python 3 (on Windows use `py`, not `python`, when the Store alias is installed), the REDkit data
and a saves folder to point at.

## Paths

`paths.py` holds every path and reads an environment variable for each, so this is not tied to one machine:

| variable | default |
|---|---|
| `W3_GAME_DIR` | `C:\Steam\steamapps\common\The Witcher 3` (same variable the Rust index test uses) |
| `W3_REDKIT_DIR` | `F:\SteamLibrary\steamapps\common\The Witcher 3 REDkit\r4data` |
| `W3_SAVES_DIR` | `C:\Users\Desktop-Isac\Documents\The Witcher 3\gamesaves` |
| `W3_TRACKER_DIR` | this repo (for `data/`) |
| `W3_QDB` | the journal-file index in the game folder's `w3check`; only old-vs-new comparisons need it |

## The pipeline that produces the app's data

`questindex` → `cutoffs` → `review_cutoffs` → `questgraph` → `routegen` → `derive` → `prereqs` →
`contradictions`, then `regen` to prove it repeats:

| script | what it does |
|---|---|
| `stringsdb.py` | The game's own text, from REDkit's SQLite string database: quest-log names, objective lists and dialogue choices by locId. |
| `questindex.py` | Every `CJournalQuest` in the base game and both expansions (405 here): journal entry and objectives with their phase names, the block that activates it, the `Failure` inputs attached to its journal blocks, type/order/description/level, choice and Gwent flags, facts, scenes, and what its phases switch off and back on. |
| `questgraph.py` | Reads the phase graphs for activation blocks, connected `Failure` inputs and the conditions gating them; writes `../data/quest_graph.json`: the journal-activation block (`starts`), the reviewed fact prerequisites (`requires`), and the reviewed loss edges (`lost_when`). The 25 hand-written 0.1.9 events in `legacy_events.json` are the acceptance corpus; each is replaced by a file edge or recorded as dropped with its reason. |
| `cutoffs.py` | Every candidate cutoff: quest E switches off resource R, quest X references R; each is judged on the order the saves were written, including whether any save actually marks X `Failed` after E. |
| `review_cutoffs.py` | The review pass over that pool. Writes `../data/cutoffs.json`. A community cutoff is rejected when the affected quest starts after the switch, its own phase switches the actor back on, or nothing marks it failed; reviewed journal windows from `../data/cutoff_windows.json` are accepted only when the affected quest has a connected `Failure` input whose upstream conditions name the closer's journal, and `closes_at` is a real phase of that journal. Every kept and excluded family is recorded with a reason, and regression self-checks fail the build if Haunted House, the old Triss cutoff, or the old early `Q310 Gather Lodge` window is accepted again. |
| `routegen.py` | Writes `../data/route.json` from `quest_index.json`, `../data/quest_sections.json`, `../data/route_overrides.json` and `../data/quest_graph.json`: 403 quest + 9 reviewed manual steps = 412, five sections, levels, descriptions, fact locks, loss edges, and the 11-step manual audit. No hand-written note or level. |
| `branchgen.py` | Writes `../data/branches.json`: 2,286 fact-setting scene-choice rows on 141 route steps. A one-shot dialogue row and a contract are never branches; each row keeps its scene, locId, set/test facts and exact text for the opt-in guidance path. |
| `coverage.py` | Writes `../data/coverage.json`: per-pack route/quest/phase/scene/branch/cutoff counts, plus the measured card column. It refuses an untallied pack and a DLC family with zero scene rows. |
| `matrixcheck.py` | Checks the audited 412-node matrix and the 11-step manual audit: 403 quest + 9 `manual_reviewed` rows, 2 replacements, every source anchor and review date, every named exclusion, the four chosen targets and the six-state payload counts. `test_matrix.py` proves it rejects each missing label. |
| `cards.py` | Writes and checks `../data/gwent_cards.json`: 224 collectible cards (202 main + 22 leaders), sources, summon-only exclusions, one `window` per card, and save ownership from `SBCollectionCard` / `SBLeaderCollectionCard`. |
| `cardwindows.py` | Writes and checks `../data/card_windows.json` and attaches the reviewed windows to every card. Fails on an unaccounted card, a Tier B row without a source/URL/review date, a no-window row without concrete `sources_checked`, a category-only no-window reason, a stale payload, or a bare zero. |
| `derive.py` | Writes `../data/derived.json` (what the app shows per step: game name, objectives, activation block, reviewed cutoff). |
| `prereqs.py` | Settles every route prerequisite from the game's files *and* the saves: keeps it as a lock, re-tests it on the fact the game actually gates on, or drops it. Re-checks the reviewed decisions in `../data/prereqs_review.json` and writes `prereq_relations.json`. |
| `contradictions.py` | Tests every derived claim, every cutoff and every route prerequisite against all saves; checks route/derived coverage and the built app's `--dump`; writes `contradiction_report.md` and `../data/route_disputes.json`. |
| `regen.py` | Runs the whole chain and compares the bytes of every output against `goldens.json` (`--update` to record). |
| `endings.py` | Validates the reviewed ending targets against `branches.json`, the route, the string database and the reviewed presets. Outcome-backed targets are checked against `../data/outcomes.json`; the rows themselves are validated by `outcomecheck.py`. Read-only; `--release` adds the release-only rules. |
| `outcomecheck.py` | Validates `../data/outcomes.json`: every terminal fact resolves in the phase index or a branch, every exact line resolves in the string database, every journal outcome is a real description entry, every group is `selection: one`, every recommended target covers one group, and every pair in a group has an evidence-bearing exclusion edge. Read-only; `--release` adds the group/edge completeness rules. |
| `exclusivity.py` | Audits `../data/exclusive.json` and writes `exclusivity_report.md`: accepted edges with their mechanisms, then rejected cutoff candidates and the unlisted cross-group pairs. Read-only except for the report. |
| `compare_legacy.py` | One-shot report: where the frozen 0.1.9 route notes, levels and 25 events differ from the generated route and graph. Writes `legacy_comparison.md`. |
| `fuzz.py` | Feeds truncated and corrupted files to the readers: they must fail cleanly or parse, never misread. |

`py questindex.py build --all` (about a minute) · `py cutoffs.py build` (about two minutes) ·
`py review_cutoffs.py build` · `py questgraph.py build` · `py routegen.py build` · `py derive.py` ·
`py prereqs.py check` (~2 min) · `py contradictions.py` (15s) · `py regen.py`

## The checks the release must pass

```
py tools/endings.py check --release  # schema, branches, locIds and exact lines; 4 targets, 4 guided
py tools/outcomecheck.py --release    # 4 groups, 11 outcomes, 11 exclusion edges, 0 warnings
py tools/exclusivity.py --check       # accepted edges and the rejected candidate report
py tools/contradictions.py           # 5 derived claims, 0 contradicted; 5 route prerequisites, 0 disputed
py tools/regen.py --check            # all 11 outputs match the recorded hashes
cargo test                           # ordering, frontier, tags, empty top section, tick rule
```

The checker's own fixtures are the fast way to see its rules:

```
py tools/test_endings.py -v
py tools/test_outcomes.py -v
```

The route is not hand-edited. A correction belongs in `../data/quest_sections.json`,
`../data/route_overrides.json`, `../data/prereqs_review.json` or `../data/cutoffs.json`, followed by
`py tools/regen.py --update`.

## Why the old start-gate results were unreliable

The old checks inferred a start gate from **save ordering**: "quest B first appears in saves where A is
already done". That cannot separate *gated* from *not reached yet*, and it needed many saves per quest, so
most quests had no answer at all.

The game decides this in its own files, and both mechanisms are readable:

1. **Journal activation.** A quest phase graph adds a journal entry with `CJournalQuestBlock` (= add this
   entry) or `CJournalQuestTrackBlock`. Whoever adds a quest's *quest-level* entry starts that quest.
2. **Fact gates.** Where the game does not name another quest it gates on its facts database: one phase sets
   a fact (`CQuestFactsDBChangingBlock`), another waits on it (`CQuestFactsDBCondition`, or a condition
   block whose label names the fact). Joining setters to testers gives the gate.

Caveat: attribution is per phase *file*. When one file runs several quests, an activation can only be
attributed to that chain, not to one quest. Quests whose start comes from dialogue or script have no
activation row at all, so "no activator found" never means "cannot start". `routegen` treats those as
`unknown` and available, never suppressed.

## The older checkers

| script | what it does |
|---|---|
| `cr2w.py` | CR2W reader for REDkit resources (`.w2phase`, `.w2scene`, `.journal`). Underlies everything else. Refuses container versions it does not decode instead of misreading them. |
| `gateindex.py` | Every quest `.w2phase` → every journal-activation row (`gate_index.json`). |
| `factgates.py` | Sets/tests index over the same files (`fact_index.json`). |
| `factcontext.py` | Story context around one fact: where it is set and the labelled blocks beside it. |
| `save_reader.py` | One save: LZ4 chunks, name table, journal entries, facts. |
| `saveindex.py` | Every save's quest journal status (`save_index.json`), plus `gate`/`show` queries. |
| `statuscheck.py` | Old vs new quest-status reading, over every save. |
| `cutoff_check.py` | "Does finishing quest E deactivate a spawnset or community X needs?" |
| `gatecheck.py` | The report: `route.json` vs game files vs saves → `gate_report.md`. |

### Two limits worth remembering

The saves can **refute** a claim and can show no contradiction, but they cannot prove that a quest stopped
being possible: a quest nobody finishes looks the same as one that cannot be finished. A cutoff is a claim
about the files; the saves are corroboration, and `contradictions.py` says which of the two each warning
rests on.

A quest can read `Failed` in a save where it was never available (`q402skelligeallies`,
`q402novigradallies`, `q302war`), so a `Failed` reading is not on its own proof that something was lost.
That is why a disagreement between the saves and the route is *decided* rather than trusted either way:
`prereqs.py` settles it from the files and `../data/prereqs_review.json` records the decision, including the
ones that were dropped from the route. `../data/route_disputes.json` holds whatever is still undecided, and
is empty when the route and the saves agree.

## Running it

```
py questindex.py build --all
py cutoffs.py build
py review_cutoffs.py build
py questgraph.py build
py routegen.py build
py derive.py
py prereqs.py check
py contradictions.py
py regen.py
py compare_legacy.py
```

For a single question:

```
py questgraph.py starters q206berserkers
py questgraph.py gates quests\part_1\q206_berserkers.w2phase q206berserkers
py gatecheck.py node q206berserkers
py factcontext.py q203_cerys_saved 2
py saveindex.py gate q203him q206berserkers    # does any save hold B without A done?
py statuscheck.py                              # regressions when the reading rule changes
```

## The legacy material

`../data/legacy_route.json`, `../data/legacy_events.json` and `../data/legacy_feed.json` are the frozen
0.1.9 inputs. They are used by `questgraph.py` as an acceptance corpus and by `compare_legacy.py` as the
comparison target. They are never loaded by the app. `../data/audit_*.json` and `../data/guide_*.json` are
the wiki-era research, kept on disk for comparison and not packaged.
