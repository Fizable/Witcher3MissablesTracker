# DLC extraction probe (plan step 2)

Measured 2026-10-28 against this install, the REDkit export at
`F:\SteamLibrary\steamapps\common\The Witcher 3 REDkit\r4data`, and the current `tools/` reader.
The inventory probe is read-only. Its attribution follow-up (sections 10-11) changed
`tools/questindex.py` and regenerated the route/derived outputs; no target or choice line was added.

**Verdict: the resource provider is feasible, but it is not an extraction problem.**

1. The DLC bundles carry **239 `.w2phase`, 1759 unique `.w2scene` and 231 `.journal`** resources.
2. Every one of those 2229 paths already exists in REDkit under `r4data\dlc\...`, with the same
   exact case and name. Bundle extraction adds **zero unique resources**.
3. `q704*`/`q705*` do contain real scenes: 117 scenes, 317 choice lines, and 44 choice lines whose
   section sets a fact. The data exists; the current index does not attach most of it.
4. Before the fix, a plain scan-root overlay gave the three `q705*` epilog nodes 63 scenes each and
   gave **every `q704*` node 0 scenes**, because scene folders were resolved from the phase file's
   own directory. That gap is now fixed in `questindex.py` (section 10); the pre-fix numbers stay
   here because they are what exposed it.
5. The plan's "0 DLC phases/scenes" is a **scan-root omission**, not a missing-data finding:
   `paths.QUEST_ROOT` is `r4data\quests`, and the DLC files are under `r4data\dlc`.

## What was scanned

| location | bundles | role |
|---|---|---|
| `content/content0/bundles` | 31 | the whole next-gen content tree, including `ep1.bundle`, `bob.bundle`, `dlc0.bundle` and `world_bob_startup.bundle` |
| `DLC/dlcTrissGlorifiedWardrobe/content` | 2 | cosmetic DLC only; both fail the bundle size invariant (see below) |
| `DLC/` elsewhere | 0 | only `dlc-tombstones/dlc1..dlc16` and one cosmetic folder; the old free-DLC bundles are gone |

On this install the expansions are not in `DLC/*/content`; they are merged into `content0`.
"Reads the content and dlc folders" therefore means `content/content0/bundles` plus the two
`DLC/dlcTrissGlorifiedWardrobe` bundles.

The POTATO70 layout used by the probe is documented in `tools/probe_dlc.py`: a 32-byte header,
a table of 304-byte records (name[256], 16-byte hash, offset, unknown, unpacked size, stored size,
crc), 16-byte-aligned zlib payloads. The TOC is read first; payloads are decompressed in memory and
handed to `cr2w.parse` through a temporary directory that is deleted on exit.

## 1. Inventory

Unique DLC resources, by bundle:

| bundle | `.w2phase` | `.w2scene` | `.journal` | notes |
|---|---:|---:|---:|---|
| `bob.bundle` | 177 | 1422 | 156 | Blood and Wine; also carries 1 base-game path scene |
| `ep1.bundle` | 54 | 275 | 55 | Hearts of Stone; also carries 38 base-game path scenes |
| `dlc0.bundle` | 8 | 62 | 20 | free DLC packs `dlc2/3/7/9/10/12/15` |
| `world_bob_startup.bundle` | 0 | 50 | 0 | all 50 quest entries duplicate `bob.bundle` paths |
| **unique total** | **239** | **1759** | **231** | **2229 resources** |
| entries including duplicates | 239 | 1809 | 231 | 50 duplicate scene entries |

By pack (unique):

| pack | phases | scenes | journals |
|---|---:|---:|---:|
| `bob` (Blood and Wine) | 177 | 1422 | 156 |
| `ep1` (Hearts of Stone) | 54 | 275 | 55 |
| `dlc2` | 1 | 6 | 0 |
| `dlc3` | 1 | 4 | 4 |
| `dlc7` | 1 | 31 | 2 |
| `dlc9` | 1 | 0 | 0 |
| `dlc10` | 1 | 1 | 8 |
| `dlc12` | 1 | 12 | 2 |
| `dlc15` | 2 | 8 | 4 |

REDkit's per-pack counts are identical (bob 177/1422/156, ep1 54/275/55, free DLC 8/62/20): the
bundle inventory adds no pack. The 39 "base-game path" scenes inside `bob.bundle`/`ep1.bundle` are not DLC resources: their
virtual paths start with `quests\...` and they map to `r4data\quests\...`. The probe counts them
separately instead of inflating the DLC totals. The 50 duplicate scene entries are `bob.bundle` paths repeated in
`world_bob_startup.bundle`: 48 Toussaint chat scenes under
`dlc\bob\data\gameplay\community\dialogues\chats\tyg_chats`, plus
`q704_geralt_oneliners_pickups.w2scene` and `mq7001_15_gp_community_chats.w2scene`.

The two `DLC/dlcTrissGlorifiedWardrobe` bundles are **unreadable** by the size invariant: the
header claims 196608 bytes for a 193988-byte `blob0.bundle`, and 1122304 for a 1122248-byte
`buffers0.bundle`. The probe reports them as errors, not as zero. They are the cosmetic Triss
wardrobe's blob/buffers bundles; their contents were not decoded.

## 2. CR2W parse

| source | phases | scenes | journals | parsed | failed |
|---|---:|---:|---:|---:|---:|
| DLC bundle payloads (unique) | 239 | 1759 | 231 counted | **1998** | **0** |
| REDkit `r4data/dlc` | 239 | 1759 | 231 | **1998** | **0** |

No `UnsupportedVersion`, `NotCr2w`, `Truncated` or zlib failure. The reader's structural guard
accepts every DLC container, including the free-DLC `.w2phase` files. Journals were counted but not
parsed, because the provider question is about phases and scenes.

Bundle payloads and REDkit files are **not byte-identical**: all 2229 pairs differ, because the
bundle holds the cooked runtime resource and REDkit holds the editor resource. The sample comparison
still produced the same choice counts on both sides. That is a source-choice decision, not a parse
failure; see risk 2.

## 3. `q704*` and `q705*`

Resources on disk:

| item | count |
|---|---:|
| phase files named `q704*`/`q705*` | 15 |
| companion phase in the same folder (`bob_equipment_phase.w2phase`) | 1 |
| unique scenes | 117 |
| journals | 16 |
| route nodes these folders serve | 10 |

Scene evidence:

| measure | count |
|---|---:|
| scenes with at least one choice line | 42 |
| choice lines | 317 |
| one-shot choice lines | 5 |
| choice lines with a fact-setting section | **44** |
| scenes containing those 44 lines | 16 |
| phase files parsed | 15 |
| fact sets in those phases | 238 |
| fact tests in those phases | 395 |

So the answer is **yes**: `q704*`/`q705*` expose real scenes with real choice lines. There is no
invented dialogue in this report; no choice text or locId is quoted.

The structural promise is not the same as an attached row. Before the fix, indexing `r4data/dlc`
as the quest root produced (kept as the evidence that exposed the bug):

| route node | phases | scenes | choice lines | fact-setting lines |
|---|---:|---:|---:|---:|
| `q704starting` | 4 | 0 | 0 | 0 |
| `q704truth` | 3 | 0 | 0 | 0 |
| `q704vampires` | 2 | 0 | 0 | 0 |
| `q704bfairyland` | 2 | 0 | 0 | 0 |
| `q704adettlaff` | 1 | 0 | 0 | 0 |
| `q704ftgoose` | 2 | 0 | 0 | 0 |
| `q705prison` | 2 | 63 | 143 | 11 |
| `q705ceremony` | 2 | 63 | 143 | 11 |
| `q705prisonstash` | 1 | 63 | 143 | 11 |
| `q705home` | 1 | 0 | 0 | 0 |

There are 63 distinct scene files behind the 189 scene rows: the same `quest_files\q705_epilog`
folder is attached to three nodes.

The cause is `questindex.quest_folder`: it looks only at
`<phase dir>/quest_files/<phase stem>`. The covered `q704*` phases live at
`...\quest_files\q704_truth\phases\q704_03_monster_hunt.w2phase`, so the lookup returns `None` and
their scenes are never collected. `q705*` works only because `main_quests\q705_epilog.w2phase`
mentions `q705ceremony`/`q705prison`/`q705prisonstash` journals and resolves
`main_quests\quest_files\q705_epilog`. `q705home` fails because its only covered phase,
`q705_house.w2phase`, is nested in the same folder but does not resolve the folder itself.

Consequence for step 2's acceptance check: "at least one Blood and Wine quest has a real scene row"
**passes** (the three `q705*` nodes), but "`q704*`/`q705*`" as a family does **not**. Any B&W target
whose step is a `q704*` node has no scene source until attribution is fixed.

## 4. Virtual bundle paths to REDkit paths

The mapping is identity after replacing `\` with the path separator:

| virtual bundle path | REDkit path |
|---|---|
| `dlc\bob\data\quests\main_quests\...` | `r4data\dlc\bob\data\quests\main_quests\...` |
| `dlc\ep1\data\quests\quest_files\...` | `r4data\dlc\ep1\data\quests\quest_files\...` |
| `dlc\dlc10\data\quests\scenes\...` | `r4data\dlc\dlc10\data\quests\scenes\...` |
| `quests\dialogues_junk\...` (inside a DLC bundle) | `r4data\quests\dialogues_junk\...` (base game) |

Measured:

- 2229 unique DLC resource paths, **2229 exact-case matches** in `r4data\dlc`, 0 case differences.
- **0 bundle-only** paths and **0 REDkit-only** paths: the two sets are equal.
- 50 duplicate entries (`bob.bundle` and `world_bob_startup.bundle`); the provider must dedupe by
  virtual path and pick one copy deterministically.
- 0 byte-identical pairs; all 2229 differ as cooked vs editor resources.

No hash table or name translation is needed for the DLC overlay: the bundle path already is the
REDkit relative path. The existing base-game name discrepancy (`mq3012noblestatuette` vs
`mq3012_jade_statuettes`) is handled by the journal GUID alias, not by these paths.

## 5. Is a resource provider feasible?

**Yes.** The cheapest correct shape is a root provider, not a bundle extractor:

1. **Quest roots.** Add `r4data\dlc` to the phase/scene roots. Journals are already found:
   `quest_journal_files()` walks `REDKIT_R4.rglob("journal")`, which is why the DLC quests exist in
   the index as journal-only rows today. Only phases and scenes are missing.
2. **Scene attribution.** Resolve a covered phase to its nearest `quest_files\<quest>` ancestor
   (or to the quest folder implied by the journal it names), not only to
   `<phase dir>/quest_files/<phase stem>`. This is what turns the q704/q705 scenes into rows, and
   it also fixes `q705home`. Implemented for DLC in section 10.
3. **Source precedence.** Use REDkit as the analysis source. It is the same data the base game
   already uses, it contains all 2229 resources, and it avoids the cooked/editor byte split. Use
   bundles only as a validation layer, never as a second copy for the same path.
4. **One root set for every reader.** `questindex`, `questgraph`, `cutoffs`, `contradictions`,
   `gateindex`, `factgates`, `gatecheck`, `cutoff_check` and `fuzz` scan `QUEST_ROOT` directly;
   `derive` reads their generated output. Wiring only `questindex` makes the graph, cutoffs and
   contradiction checks read a different world than the one that produced the index.
5. **Filter the DLC tree.** `bob` has 177 phases, including `living_world` POIs and prefab phases;
   `ep1` has living-world encounters. They are not all route quests. The provider must key on the
   route quests/journals, or the index will grow with POI phases and generic journal mentions.

The bundle reader itself is proven: 1998/1998 CR2W, 0 failures, TOC version 5. It is simply
unnecessary for coverage.

## 6. The three biggest risks

**1. Attribution, not extraction, is the blocker.** The naive overlay attaches 0 scenes to all six
`q704*` nodes and 63 scenes to three `q705*` nodes (and 0 to `q705home`). Fixing `quest_folder` can
also move base-game output: base quests have nested `quest_files/<quest>/phases` files too, and an
ancestor lookup would return folders those phases return `None` for today. Whether that adds a scene
depends on whether another covered phase already found the same folder, which is exactly the kind of
thing the step must measure before claiming "base outputs byte-identical". This is the largest piece
of work in the step, and it lives in `questindex.py`, which step 1 is actively editing.

**2. Every resource has two divergent copies.** All 2229 paths match exactly, but all 2229 payloads
differ between the cooked bundle and the editor copy. There is no byte-identical resource to use
as a control. The ten sampled scenes produced the same choice counts on both sides, but that is a
sample, not a guarantee for all 2229. If a provider overlays bundles on REDkit without a strict
precedence, `regen.py` goldens move depending on which copy is read. The 50 duplicate
`bob`/`world_bob_startup` entries add a second precedence decision. Pin the source in code and
compare counts per resource.

**3. The base-game blast radius is not zero.** Five DLC phases name base-game journals: four `ep1`
living-world phases name `livingworld`, and
`dlc\bob\...\q701_wine_festival\phases\_prefab_blocks.w2phase` names `sq102letho` and `sidequests`.
Adding the DLC root can therefore add phase or scene rows to base quests as well as DLC ones. Combined with nine modules scanning `QUEST_ROOT`
directly, "only the DLC counts change" is not something the current code guarantees. The step-2
check has to be a real before/after diff, not an assumption.

## 7. Step-2 check status

| plan check | result |
|---|---|
| provider reports DLC phase/scene counts, recorded in `coverage.json` | measured: 239 phases / 1759 scenes / 231 journals, 2229 unique |
| at least one B&W quest (`q704*`/`q705*`) has a real scene row | **pass after the fix**: all 10 nodes attach; pre-fix only `q705*` did |
| base outputs byte-identical except the known counts | **not established**; 5 DLC phases name base journals and nine modules share the root |
| zero extraction fails loudly | n/a: 1998/1998 phase+scene payloads parse, 0 failures |

No `data/coverage.json` was written; that file does not exist in this tree yet. The counts above are
probe output, ready for the step that owns `coverage.json`.

## 8. Limits and what was not done

- The inventory probe itself made no `data/*.json`, `tools/questindex.py`, `src/` or `ui/` change,
  and ran neither `regen.py` nor `package.ps1`. The follow-up attribution fix changed
  `tools/questindex.py` (section 10), then section 11 applied the regenerated outputs; that is the
  only data change in this report.
- No target data and no Blood and Wine choice line. The 44 fact-setting lines are counted, not
  quoted; selecting and reviewing one for the "both sisters" target belongs to step 5.
- The `section_sets` count depends on step 1's concurrent fix to `scene_choices`. An earlier run of
  this probe, before that fix was in the tree, read **0**; the current reader reads **44**. The count
  is evidence about the scene, but it is coupled to that code, so step 5 still needs a fixture.
- The two `dlcTrissGlorifiedWardrobe` bundles fail the size invariant and were not decoded.
- The POTATO70 layout is observed here (version 5), not a documented CDPR contract. The probe fails
  loudly on a size/TOC mismatch instead of guessing.

## 9. Reproduce

```text
py tools/probe_dlc.py             # inventory, CR2W, path mapping, q704/q705; about a minute
py tools/probe_dlc.py --json      # the same facts as JSON
```

## 10. Attribution fix (same day)

The fix is in `tools/questindex.py` and is deliberately DLC-scoped:

- `quest_phase_files()` scans the base `r4data\quests` tree plus each DLC pack's `data` tree, and
  drops `living_world` POI phases.
- `quest_folder()` resolves a DLC phase to its nearest `quest_files\<quest>` ancestor, so phases
  under `quest_files\q704_truth\phases\` find the `q704_truth` scene folder. The base game keeps
  its previous rule.
- A DLC phase is attributed only to DLC journals, so it cannot add phase/scene rows to a base
  quest. `set_activators` uses the same filter.
- Scene folders are deduplicated before their scenes are collected, so a folder named by several
  covered phases is read once per quest.

Base game after the change: **0 base quest entries changed**, 225 quests with phases, 186 with
scenes, 4857 scene rows, exactly the baseline. The global `phaseless` list drops from 192 to 108
because DLC steps are no longer phaseless, and `aggregate_phase_files` grows from 9 to 15 with the
DLC aggregate phases; those are the expected count changes, not base quest changes.

B&W route coverage (83 route nodes):

| measure | after the fix |
|---|---:|
| route nodes with phases | 53 / 83 |
| route nodes with scenes | 31 / 83 |
| scene rows | 948 |
| distinct scene files | 307 |
| choice lines (summed over nodes) | 2144 |
| distinct choice locIds | 676 |
| choice lines with fact-setting sections | 346 |
| distinct facts set by those choices | 98 |

For context, Hearts of Stone is 18 / 26 nodes with scenes, 556 scene rows, 179 distinct files. The
free DLC packs gain 13 phased quests but 0 scene folders.

`q704*` and `q705*` now all attach:

| node | phases | scenes | choice lines | fact-setting lines |
|---|---:|---:|---:|---:|
| `q704starting` | 4 | 48 | 127 | 23 |
| `q704truth` | 3 | 29 | 62 | 9 |
| `q704vampires` | 2 | 29 | 62 | 9 |
| `q704bfairyland` | 2 | 19 | 65 | 14 |
| `q704adettlaff` | 1 | 29 | 62 | 9 |
| `q704ftgoose` | 2 | 19 | 65 | 14 |
| `q705prison` | 2 | 63 | 143 | 11 |
| `q705ceremony` | 2 | 63 | 143 | 11 |
| `q705prisonstash` | 1 | 63 | 143 | 11 |
| `q705home` | 1 | 63 | 143 | 11 |

Two limits remain visible in those numbers. Attribution is folder-level, so the shared
`q705_epilog` folder gives the same 63 scenes to four nodes, and `q704starting` collects both the
`q704_truth` and `q704b_fairy_tale` folders. The other 52 B&W route nodes have no scenes: 30 have no
phase file at all and 22 have phases whose folders do not resolve. `cutoffs.py` and `derive.py`
need no second root: both consume the index, so section 11 measures the propagation instead.

## 11. Propagation into cutoffs, route and derived (same day)

`cutoffs.quest_refs` resolves every path in a quest's index rows under `r4data`, and `derive.py`
reads `quest_index.json` plus the route. Neither has a phase/scene root of its own, so once the
index carries `dlc\...` paths both stages carry them. Neither needed a behavioral change.

The chain was first measured in a temporary tree, then applied to the repo on 2026-10-28 with
`py tools/regen.py`; the numbers below are the applied outputs, not a projection. The old index was
replayed byte-for-byte through the current `routegen`/`derive` in the temporary tree, so every
difference is attributable to the DLC root.

| stage | before | after |
|---|---:|---:|
| cutoff candidates | 9012 | 13238 (+4226) |
| added candidates | 0 | 4226 |
| of those, with a DLC `deactivated_in` | 0 | 4125 |
| base candidates whose `specificity` grew | 0 | 256 (no verdict change) |
| `consistent` DLC candidates | 0 | 4 (all `ep1`) |
| reviewed cutoffs | 1 community + 1 window | unchanged |
| route `branch` | 102 | 141 |
| route `dialogue_choice` | 79 | 111 |
| route `start_known` | 225 | 308 |
| derived quests with DLC rows | 0 | 84 |

### Route diff

414 nodes before and after; 83 changed, all DLC, 0 base. Node ids and every non-node key are
unchanged; no route step was added or removed.

| field | changed | `bob` | `ep1` | free DLC |
|---|---:|---:|---:|---:|
| `start_known` | 83 | 52 | 18 | 13 |
| `branch` | 39 | 25 | 14 | 0 |
| `dialogue_choice` | 32 | 20 | 12 | 0 |

The route gained no node: the 122 DLC quests were already journal steps. The diff is the evidence
attached to them. `routegen.py check` passes (403 quest + 11 manual, 141 branch, 111 dialogue,
0 contract branches, 1 loss event).

### Derived diff

403 quests and 414 steps before and after; ids unchanged. 84 DLC quests changed, 0 base. 83 steps
changed, and only in `activators`.

| field | quests changed |
|---|---:|
| `activators` | 83 |
| `phase_files` | 72 |
| `scenes` | 49 |
| `has_branch` | 39 |
| `global_phase_files` | 24 |
| `has_dialogue_choice` | 32 |

B&W coverage, before and after the 40-scene cap in `derive.py`:

| measure | index | derived payload |
|---|---:|---:|
| route nodes with phases | 53 / 83 | 53 / 83 |
| route nodes with scenes | 31 / 83 | 31 / 83 |
| scene rows | 948 | 731 |
| distinct scene files | 307 | 253 |

The 53 phased nodes are 48 with a non-global `phase_files` row plus 5 whose only phase file is
global. In the derived payload, 25 B&W nodes carry `branch`, 20 carry `dialogue_choice` and 52 carry
`start_known`. Hearts of Stone is 18 / 26 nodes with scenes, 556 rows and 179 distinct files in the
index; the cap ships 382 rows from 140 files. Free DLC is 13 phased quests with 0 scenes. All ten
`q704*`/`q705*` nodes now carry `branch`; the six `q704*` nodes also carry `dialogue_choice`.

### Cutoff diff

The pool gains 4226 candidates by key and no old candidate was removed. 4125 of the new rows name a
DLC phase as `deactivated_in`; the other 101 pair a DLC affected quest with a base-game phase and
resource. 256 base rows changed only `specificity` (13 -> 18) because DLC phases now count as
reactivations; no verdict changed on any shared row. Four of the new candidates are `consistent`,
all Hearts of Stone (`mq6001merchant`, `mq6005enchanterlevel0`), none Blood and Wine.
`review_cutoffs.py` still ships only the reviewed brothers-in-arms family and the one journal
window, so the route's single loss event is unchanged. DLC cutoffs are therefore **candidates**,
not warnings; promoting one is a review decision, not an extraction result.

### Limits

- The 40-scene cap in `derive.py` ships 731 of the 948 B&W scene rows. The index has all 948.
- Folder-level attribution still gives the four `q705*` nodes the same 63 scenes and gives
  `q704starting` both the truth and fairy-tale folders.
- The repo now carries these numbers. `tools/goldens.json` records the new hashes; the pre-DLC
  hashes are in the applied-outputs table below for rollback.

### Applied outputs

`py tools/regen.py` wrote six outputs and left the other three byte-identical. The route and derived
schemas are unchanged, so the app read the new data without a rebuild: `routegen.py check` passes,
`contradictions.py` reports 5 derived claims and 5 route prerequisites with 0 violations, and its
app `--dump` check covers 424 reads. All 4913 phase/scene paths in the derived payload resolve in
the REDkit tree.

| output | before | after |
|---|---|---|
| `tools/quest_index.json` | `0c93567dc9077e79` | `4549c944cbce5cd9` |
| `tools/cutoff_index.json` | `a9883aa79b0016dc` | `5526659623a2d4fb` |
| `data/cutoffs.json` | `eba81fe4e7dd3cde` | `4c8e86fe1796ac49` |
| `data/quest_graph.json` | `cd18ae3cd37c3a1c` | `2d0a790bfb4ddeff` |
| `data/route.json` | `19599705ae7a579e` | `402ea94d3eb3c226` |
| `data/derived.json` | `0a034487ee0e3c91` | `fb918e1eb5585490` |

`data/cutoffs.json` changed only its row-count note; `items`, `windows` and `decisions` are equal.
`tools/contradiction_report.md`, `data/prereq_relations.json` and `data/route_disputes.json` did not
move.


