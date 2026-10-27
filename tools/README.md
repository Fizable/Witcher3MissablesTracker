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

| script | what it does |
|---|---|
| `cr2w.py` | CR2W reader for REDkit resources (`.w2phase`, `.journal`). Underlies everything else. |
| `questgraph.py` | One quest phase: journal paths, which blocks activate a journal entry, graph walks. |
| `gateindex.py` | Every quest `.w2phase` → every journal-activation row (`gate_index.json`). |
| `factgates.py` | Sets/tests index over the same files (`fact_index.json`). |
| `factcontext.py` | Story context around one fact: where it is set and the labelled blocks beside it. |
| `save_reader.py` | One save: LZ4 chunks, name table, journal entries, facts. |
| `saveindex.py` | Every save's quest journal status (`save_index.json`), plus `gate`/`show` queries. |
| `statuscheck.py` | Old vs new quest-status reading, over every save. |
| `cutoff_check.py` | "Does finishing quest E deactivate a spawnset or community X needs?" |
| `gatecheck.py` | The report: `route.json` vs game files vs saves → `gate_report.md`. |

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

## Two things this rebuild exposed

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

## Evidence labels in `../data/feed.json`

- `graph` — from the game's own files only. Mechanism named, saves not yet checked.
- `save` — no save contradicts it and there are saves on both sides of it.
- `save+graph` — both of the above.
- `refuted` — saves contradict it; kept so it is not repeated.

Keep the label honest when adding an entry: `graph` is a statement about the files, not a promise about
play, because a quest can also start from dialogue the files do not name in a graph block.
