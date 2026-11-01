# The game database

`tools/gamedb/` reads the game's own editor data (REDkit `r4data`), the editor string database and
the player's saves, and writes one SQLite database plus readable views:

```
py tools/gamedb/build.py                  every stage, in order (about 3 minutes)
py tools/gamedb/build.py semantic views   only these stages
```

| output (git-ignored) | what it is |
|---|---|
| `db/w3db.sqlite` | everything below, about 250 MB |
| `db/w3saves.sqlite` | the full journal and fact table of every save, incremental cache for the `saves` stage |
| `db/README.md`, `db/INDEX.md`, `db/MISSABLE.md`, `db/quests/*.md`, `db/*.jsonl` | the views: start here when reading as a person or an LLM |

Everything is read-only against the game, REDkit and the saves folder. Paths come from
`tools/paths.py` (environment variables `W3_REDKIT_DIR`, `W3_SAVES_DIR`, `W3_STRINGDB`, ...);
`W3_GAMEDB_OUT` moves the output folder.

Nothing in the database is hand-reviewed. Every derived row names the file and block it came from,
so a claim can be checked in REDkit. Reviewed decisions still live in `data/` and are not merged in.

## Stages and tables

### strings (`strings.py`)
`strings(loc_id, text, key, resource, property)`: every English string in
`LocalEditorStringDataBaseW3_UTF8.db`. A `{"locId": n}` value anywhere resolves here; XML item
names resolve through `key`.

### graph (`graph.py`): the quest graphs, raw
Every `.w2phase` and `.w2quest` (1,040 files, 4 unreadable older containers).

| table | meaning |
|---|---|
| `files` | shared by all stages: one row per source file, with `pack` (base, ep1 = Hearts of Stone, bob = Blood and Wine, dlcN) and a parse `error` |
| `graph_nodes` | every object in a graph file except sockets, connections and journal paths. `is_block=1` for graph blocks; other rows (conditions, spawnset switches, AI actions) carry the `owner_block` they belong to. `props_json` holds all decoded properties |
| `graph_sockets` | block sockets: input sockets have `direction` NULL, outputs `LSD_Output` |
| `graph_edges` | block-to-block connections, always output socket to input socket |
| `graph_refs` | every reference to another file (`scene`, `phase`, `spawnset`, ...), with the property it sits in |
| `graph_journal_refs` | every reference to a journal entry, resolved to the entry's guid (`leaf_guid`) |

### journal (`journal.py`)
`journal_entries` (every entry of every `.journal`: quests, phases, objectives, map pins,
descriptions, characters, bestiary), `journal_quests` (403 quests; `category='quest'`),
`journal_objectives`. Guids are the raw 16-byte hex the saves use, so they join to the save tables
directly. 73 journal files are older containers the reader refuses; none is a playable quest (demo,
test and act-group files).

### scenes (`scenes.py`): dialogue
`scene_nodes`, `scene_links` (next / branch / choice links inside a scene), `scene_lines` (spoken
lines), `scene_choices` (every dialogue choice: `loc_id`, `one_shot`, `sets_facts`,
`leads_to_outputs`), `scene_outputs`, `scene_inputs`. A scene output's name equals the output socket
name of the `CQuestSceneBlock` that plays the scene; an output or input without a name property is
the default `Output` / `Input`.

### items (`items.py`): XML game data
`items`, `item_tags`, `loot_tables`, `loot_entries` (shops are loot tables too, e.g.
`_store__Barons_Village_Trader`), `rewards`, `reward_items`, `gwent_cards`, `gwent_decks`,
`gwent_deck_cards`, and `card_sources` (imported from the reviewed `tools/card_sources.json`, not raw
game data). Most XML exists twice, in `gameplay/items` and in the next-gen `gameplay/items_plus`;
`file_id` tells them apart. Abilities, crafting schematics and recipes are not mapped yet.

### saves (`saves.py`): the oracle
`saves`, `playthroughs`, `journal_transitions`, `fact_transitions`. Saves form a tree because players
reload: a save's `parent` is the earlier save whose finished-quest set it contains (at most 3
misses), choosing the most advanced one. Transitions are parent to child, so "quest B became
`JS_Failed` between these two saves" is something the game recorded.

### semantic (`semantic.py`): what the graph means
| table | meaning |
|---|---|
| `phase_tree` | which phase file includes which |
| `file_quest` | the quest a phase file belongs to: `journal` (the quest its journal blocks name most), `parent` (inherited from the including phase), `shared` (global fix-up graphs such as `bugfixing_phase.w2phase`, which belong to no quest) |
| `journal_ops` | every journal block and what it does to which entry: `activate`, `success`, `failure` (from which input socket is wired), `track`, `unwired` |
| `journal_tests` | every condition that tests a journal entry's status |
| `fact_ops` | every fact set, added, removed, tested or forbidden, by a phase block, a script block or a dialogue choice (`source`) |
| `spawnset_ops` | every community (NPC group) a phase switches on or off |
| `fail_triggers` | for each wired `Failure` input, the fact and journal conditions upstream of it within 12 graph steps |
| `choice_effects` | what a dialogue choice leads to in the quest graph: the facts and journal changes reachable from the scene output it ends in (within 8 steps, stopping at the next conversation) |
| `quest_relations` | quest A to quest B, with `kind`, count `n` and JSON `evidence` |

## Evidence strength (`quest_relations.kind`)

- `fails`: a journal block in A's own files has its `Failure` input wired for B's entry. Direct.
- `fail_when_journal`, `fail_when_fact`: B's `Failure` input is fired by a condition testing A's
  journal status or a fact A writes. `hops` in the evidence is the number of graph steps between the
  condition and the failure; small is strong. Example: `q402_escort_completed`, set in The Isle of
  Mists, fails Now or Never, Redania's Most Wanted, Cabaret, A Matter of Life and Death and others.
- `completes`, `starts_or_advances`: A completes or activates B's entries.
- `fact_test`, `fact_forbid`, `journal_test`: a dependency, not a loss.
- `removes_community`: weak. A switches off an NPC group that B's files reference. This was the
  only mechanism the 1.x cutoff review accepted, which is why it found Brothers in Arms and little
  else.

A forward walk (`choice_effects`) or backward walk (`fail_triggers`) can pass through blocks that
other paths also reach, so it shows what is reachable, not what is exclusive to one path.

## Known gaps

- Phase files with no journal block of their own and no including phase (mostly Blood and Wine
  world points of interest) have no `file_quest` row.
- Merchant inventories defined in entity templates (`.w2ent`) are not read; shop loot tables are.
- The saves cover one player's choices: a quest the player always finished before its cutoff has no
  observed failure, so the oracle can contradict a claim but rarely confirm one.
- `cr2w.py` refuses older container layouts (4 phase files, 3 scenes, 73 journal files).
