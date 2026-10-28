# 0.1.7 - the nine disputed prerequisites settled, and the reading behind them fixed

0.1.5 shipped with nine route prerequisites the saves disagreed with, left as a note in the app instead
of a rule, and asked the question: is the prerequisite wrong, or is the journal status reading wrong?
This release answers that for each of the nine - and the answer turned out to be *both*, in different
places. The status reading had two real defects, and they are fixed here.

## The nine, decided

Each edge was settled from the game's own files, not from a guide. The rule the tool applies
(`tools/prereqs.py`): a prerequisite is **real but tested on the wrong signal** when the game's files
name exactly one condition that no save breaks; it is **not a rule** when the saves break it and the
files name no single condition (several, or none).

Five keep the lock, now tested on the game's own condition (`hard_facts` in `data/route.json`):

| step | still waits for | what the game actually tests | files |
|---|---|---|---|
| An Eye for an Eye | Get Junior | `q302_whoreson_found` | `sq312_quest.w2phase` waits on it; `q302_mafia.w2phase` sets it |
| Fencing Lessons | Broken Flowers | `q304_rosa_visited` | `mq3036_rosa_romance.w2phase` / `q304_dandelion.w2phase` |
| The Gangs of Novigrad | Get Junior | `q302_whoreson` | `casino.w2phase` / `q302_mafia.w2phase` |
| High Stakes | Pyres of Novigrad | `q301_burn_doppler` | `sq306_maverick.w2phase` / `q301_dreamer.w2phase` |
| Honor Among Thieves | Get Junior | `q302_freed_rico` | `king_beggar_reward.w2phase` / `casino.w2phase` |

In each case the quest really does open partway through the other one, so "finish Get Junior first"
was wrong while "Get Junior has reached this point" is right. The app now locks on the fact, and no
save in the corpus has one of these steps under way without it.

Four are dropped from the route as rules, because the two quests simply run alongside each other (or
one is created by the other's own chain): *A Favor for Radovid*, *Count Reuven's Treasure*, *Ciri's
Story: Visiting Junior*, and *Following the Thread* (from *Destination: Skellige*). Their own
"don't miss" notes stay - for A Favor for Radovid that note is the warning that matters (it never
triggers if you leave the compound without talking to Radovid's soldiers).

Every decision is recorded in `data/prereqs_review.json` and re-tested on every run: if the saves stop
supporting a decision, `tools/prereqs.py` fails.

## The status reading was wrong in two places

**1. The app kept a stale quest index.** The builder had been taught to read each quest from its
journal file's own `CJournalQuest` entry (the shipped 0.1.6 already contained that), but the cached
index was only invalidated when the *game* was patched. A player who upgraded kept the index built by
the old rule, which for 46 quests read a map pin or a `Descriptions` entry instead of the quest. The
cache stamp now includes an index version, so a corrected builder reaches players who already have a
cache. Measured over all 517 saves, the old rule read these quests differently in a large share of
them: `pirate` 315 and `giant` 270 saves in which the quest never registered at all, *Destination:
Skellige* 313, `q103secondreplacerciri` 199, `lwsb24` 171, `tombraider` 171 (`tools/statuscheck.py`).

**2. The tool chain never looked at the expansions' journal files.** It globbed one folder,
`gameplay\journal\quests`, but Hearts of Stone and Blood and Wine keep theirs under
`dlc\ep1\journal\quests` and `dlc\bob\journal\quests` - 116 of the 424 quest journal files. Those
quests were therefore read from whichever entry happened to be first in the quest database, again
usually `Descriptions`. A finished expansion quest read `Active`, which is how this was found: the
built app and the save index disagreed on exactly one quest, and the app was right.

That second fix is why the app-vs-data check no longer allows a difference at all: it used to pass as
a rate ("4 of 421 statuses, the known description-entry cases"). It now demands an exact match, and
gets one.

## What was verified, and how

- **Settlement** (`py tools/prereqs.py check`): 131 edges - every route prerequisite, plus every edge
  that was settled out of the route - re-decided from the game's files and re-tested against all 517
  saves. 0 mismatches between the decisions, the route and the saves.
- **Contradiction harness** (`py tools/contradictions.py`): 12 claims about the derived data hold
  against all 517 saves; 115 route prerequisites checked, 0 disputed. No claim has an allowance.
- **App against the data**: the built exe's `--dump` and the save index agree on all 424 quest
  statuses of the newest save (0 differences), and on which steps carry a warning.
- **Reader consistency**: 40,377 journal entries across 25 saves, each status attached to the entry
  whose GUID and journal file agree - 0 mismatches.
- **Reproducibility** (`py tools/regen.py`): the whole pipeline re-runs to the same bytes; 7 outputs
  are hash-checked. `derived.json`, `feed.json` and `cutoff_index.json` did not move at all in this
  release - the reading fix changed statuses, not any warning.
- **Unit tests**: 12 `cargo test` cases pass, including the quest-index build from the player's own
  bundles and the fact-gated prerequisite.

## Still open

- **Ten prerequisites disagree in 1-2 saves each** (`km_bia_*`, `sk_king`, `wo_deathbed`). That is
  under the threshold a dispute needs, and with two saves behind an edge there is nothing to decide:
  a single odd save looks the same as a rule that is usually right.
- **The file-derived index still covers only the base game's quest graphs.** Journal statuses for the
  expansions are read now, but 239 `.w2phase` and 1,759 `.w2scene` files under `dlc/` are not in
  `quest_index.json` yet, so the expansion steps' prerequisites can be tested on the saves but not
  settled from the files.
- **A save cannot prove a cutoff**, only refute one. The statuette cutoff still rests on its mechanism
  plus the absence of any counter-example.
- **The cutoff pool is not reviewed**: 6,276 candidates from the files, 12 consistent with the saves,
  1 reviewed and shipped.
- The GUI was not driven; verification was through `--dump`, the harness and the tests.
