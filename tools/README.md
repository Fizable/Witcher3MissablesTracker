# Quest-order analysis toolchain

The scripts that check this tracker's warnings against the game's own files and against your saves —
the same check that produced the `QUEST ORDER` items and the corrections in `data/route.json`.

Read-only, always: nothing here writes to the game folder or the saves folder. Derived indexes
(`*_index.json`) and `gate_report.md` are written here and are git-ignored; regenerate them freely.

Requires Python 3 (on Windows use `py`, not `python`, when the Store alias is installed), and the
REDkit data + a saves folder to point at.

## Paths

`paths.py` holds every path and reads an environment variable for each, so this is not tied to one
machine:

| variable | default |
|---|---|
| `W3_GAME_DIR` | `C:\Steam\steamapps\common\The Witcher 3` (same variable the Rust index test uses) |
| `W3_REDKIT_DIR` | `F:\SteamLibrary\steamapps\common\The Witcher 3 REDkit\r4data` |
| `W3_SAVES_DIR` | `C:\Users\Desktop-Isac\Documents\The Witcher 3\gamesaves` |
| `W3_TRACKER_DIR` | this repo (for `data/route.json`) |
| `W3_QDB` | the journal-file index in the game folder's `w3check`; only the old-vs-new comparisons need it |

## Why the old start-gate results were unreliable

The old checks inferred a start gate from **save ordering**: "quest B first appears in saves where A is
already done". That cannot separate *gated* from *not reached yet*, and it needed many saves per quest,
so most quests had no answer at all.

The game decides this in its own files, and both mechanisms are readable:

1. **Journal activation.** A quest phase graph adds a journal entry with `CJournalQuestBlock`
   (= add this entry) or `CJournalQuestTrackBlock`. Whoever adds a quest's *quest-level* entry starts
   that quest. Found this way: King's Gambit's entry is added by The Lord of Undvik's graph.
2. **Fact gates.** Where the game does not name another quest it gates on its facts database: one phase
   sets a fact (`CQuestFactsDBChangingBlock`), another waits on it (`CQuestFactsDBCondition`, or a
   condition block whose label names the fact). Joining setters to testers gives the gate.

Caveat: attribution is per phase *file*. When one file runs several quests (the Ladies of the Wood file
holds Whispering Hillock and Fleeing the Bog, for instance), an activation can only be attributed to
that chain, not to one quest. Quests whose start comes from dialogue or script have no activation row at
all, so "no activator found" never means "cannot start".

## Scripts

## The pipeline that produces the app's data

`questindex` → `cutoffs` → `derive` → `prereqs` → `contradictions`, then `regen` to prove it repeats:

| script | what it does |
|---|---|
| `stringsdb.py` | The game's own text, from REDkit's SQLite string database: quest-log names, objective lists and dialogue choices by locId. |
| `questindex.py` | Per quest: its own journal entry and objectives, the block that activates it, its facts, its scenes and dialogue choices, and what its phases switch off. Joins bundled and REDkit names by entry GUID. |
| `cutoffs.py` | Cutoff candidates: quest E switches off resource R, quest X references R. Each is then judged on the order the saves were written. |
| `derive.py` | Writes `../data/derived.json` (what the app shows) and the machine-checkable `checks` in `../data/feed.json`. |
| `prereqs.py` | Settles every route prerequisite from the game's files *and* the saves: keeps it as a lock, re-tests it on the fact the game actually gates on, or drops it. Re-checks the reviewed decisions in `../data/prereqs_review.json` and writes `prereq_relations.json`. |
| `contradictions.py` | Tests every derived claim and every route prerequisite against all saves; writes `contradiction_report.md` and `../data/route_disputes.json`. |
| `regen.py` | Runs the whole chain and compares the bytes of every output against `goldens.json` (`--update` to record). |
| `fuzz.py` | Feeds truncated and corrupted files to the readers: they must fail cleanly or parse, never misread. |

`py questindex.py build` (30s) · `py cutoffs.py build` (25s) · `py derive.py --feed` (5s) · `py prereqs.py check` (~2 min) · `py contradictions.py` (15s)

## The older checkers

| script | what it does |
|---|---|
| `cr2w.py` | CR2W reader for REDkit resources (`.w2phase`, `.w2scene`, `.journal`). Underlies everything else. Refuses container versions it does not decode instead of misreading them. |
| `questgraph.py` | One quest phase: journal paths, which blocks activate a journal entry, graph walks. |
| `gateindex.py` | Every quest `.w2phase` → every journal-activation row (`gate_index.json`). |
| `factgates.py` | Sets/tests index over the same files (`fact_index.json`). |
| `factcontext.py` | Story context around one fact: where it is set and the labelled blocks beside it. |
| `save_reader.py` | One save: LZ4 chunks, name table, journal entries, facts. |
| `saveindex.py` | Every save's quest journal status (`save_index.json`), plus `gate`/`show` queries. |
| `statuscheck.py` | Old vs new quest-status reading, over every save. |
| `cutoff_check.py` | "Does finishing quest E deactivate a spawnset or community X needs?" |
| `gatecheck.py` | The report: `route.json` vs game files vs saves → `gate_report.md`. |

### Two limits worth remembering

The saves can **refute** a claim and can show no contradiction, but they cannot prove that a quest
stopped being possible: a quest nobody finishes looks the same as one that cannot be finished. A
cutoff is a claim about the files; the saves are corroboration, and `contradictions.py` says which
of the two each warning rests on.

A quest can read `Failed` in a save where it was never available (`q402skelligeallies`,
`q402novigradallies`, `q302war`), so a `Failed` reading is not on its own proof that something was
lost. That is why a disagreement between the saves and the route is *decided* rather than trusted
either way: `prereqs.py` settles it from the files and `../data/prereqs_review.json` records the
decision, including the ones that were dropped from the route. `../data/route_disputes.json` holds
whatever is still undecided, and is empty when the route and the saves agree.

## Running it

```
py gateindex.py build          # a few seconds
py factgates.py build          # a few seconds
py saveindex.py build          # ~4 minutes for 500 saves
py gatecheck.py report         # writes gate_report.md, one section per route node
```

Then:

```
py gatecheck.py activations    # every automatic start the game files name
py gatecheck.py node sk_gambit # one route node against all three sources
py questgraph.py quest q206berserkers
py factcontext.py q203_cerys_saved 2
py saveindex.py gate q203him q206berserkers    # does any save hold B without A done?
py statuscheck.py                              # regressions when the reading rule changes
```

`gatecheck.py report` answers, per route node: which quest's graph adds its journal entry, which facts
it waits on and who sets them, and for each claimed prerequisite whether any save holds the quest
without it done.

## Four things this rebuild exposed

**1. The tracker read 46 of 441 quests from the wrong journal entry.** `bundles.rs` took the first
"name GUID" string in a journal file; for those 46 that is a map pin or a description entry.
The Lord of Undvik and The King is Dead therefore never registered in any save (0 of 517), and
Destination: Skellige never registered as finished. Fixed in `src/journalidx.rs` (the quest is the
file's own `CJournalQuest` entry), verified by `statuscheck.py`: no quest registers in fewer saves,
and The King is Dead went 0 → 315 and The Lord of Undvik 0 → 270.

**2. Some quests' status lives in a description entry.** For 8 quests (Novigrad, Under Control; the four
Brothers In Arms; Destination: Skellige's siblings) the game leaves the quest's own entry `JS_Inactive`
and moves a `Descriptions` / `Quest Start` / `Quest End` entry instead, so `save.rs` falls back to the
most advanced entry of the same file rather than calling the quest not started.

**3. The app kept the index that fix 1 had just made obsolete.** The index is cached in
`%APPDATA%\Witcher3MissablesTracker\quest_index.json` and was keyed on the game's `witcher3.exe`
alone, so a player who upgraded kept an index built by the old rule and went on reading those 46
quests from a description entry - the code was right and the data on disk was not. `main.rs` now
stamps the cache with an index version (`INDEX_VERSION`) so a corrected builder reaches them. The
symptom was the app and the save index disagreeing on 4 of 421 statuses; it is 0 of 424 now, and
`contradictions.py` no longer allows a difference.

**4. The tool chain read only the base game's journal files.** `saveindex.quest_table` globbed one
folder, `gameplay\journal\quests`, but the expansions keep theirs in `dlc\ep1\journal\quests` and
`dlc\bob\journal\quests` - 116 of the 424 quest journal files. Those quests were read from the first
entry in the quest database, again usually `Descriptions`, and a finished expansion quest could read
`Active`. `quest_files()` now finds them all, and `py statuscheck.py` measures what the wrong rule
cost over all 517 saves: `pirate` 0 -> 315 and `giant` 0 -> 270 saves in which the quest never
registered, *Destination: Skellige* differing in 313 saves, `q103secondreplacerciri` 199, `lwsb24` and
`tombraider` 171 each.

## Evidence labels in `../data/feed.json`

- `graph` — from the game's own files only. Mechanism named, saves not yet checked.
- `save` — no save contradicts it and there are saves on both sides of it.
- `save+graph` — both of the above.
- `refuted` — saves contradict it; kept so it is not repeated.

Keep the label honest when adding an entry: `graph` is a statement about the files, not a promise about
play, because a quest can also start from dialogue the files do not name in a graph block.
