# Release 0.2.0 - a quest order built from the game's files

2026-10-28. This is the release of `docs/PLAN-0.2-quest-order.md`. The route is now generated, not
hand-written; the wiki research stays in `data/` but is never loaded.

## Scope, measured on this install

| | |
|---|---|
| `CJournalQuest` entries | 405 (283 base + 122 DLC) |
| debug entries excluded | 2 (`biddebugquest`, `biddebugquest2`) |
| route quest steps | 403 |
| manual bookkeeping steps | 11 |
| route steps | 414 |
| sections | Main 97 (91 quest + 6 manual), Secondary 184 (180 + 4), Contracts 35, Treasure Hunts 87, Gwent 11 (10 quest + 1 manual) |
| suggested level resolved | 385 of 414 (18 route quests and the 2 debug entries have none) |
| one-line description resolved | 399 of 403 route quests |
| choice tags | 79 route steps |
| reviewed cutoffs | 3 (Triss statuettes, Haunted House, Brothers in Arms) |
| steps carrying a warning | 7 |
| legacy events | 25: 1 replaced by a file edge, 24 dropped with the reason recorded |
| route prerequisites | 5 fact gates kept, 4 dropped; 0 disputed |
| route/derived coverage | 414 route ids = 414 derived ids |

The five sections contain 403 quest steps; the 414 total includes the 11 manual steps. The 405 journal
total includes the 2 excluded debug entries.

## What changed

- **Route generation.** `tools/routegen.py` writes `data/route.json` from `quest_index.json`,
  `quest_sections.json`, `route_overrides.json` and `quest_graph.json`. No hand-written note, level or
  region name survives. A correction goes into a reviewed input file, then `py tools/regen.py --update`.
- **All quests.** The base game and both expansions are included; the old 135-step base-game-only route
  is frozen as `data/legacy_route.json` for comparison.
- **Sections from the game's type.** `Chapter` -> Main, `Side` -> Secondary, `MonsterHunt` -> Contracts,
  `TreasureHunt` -> Treasure Hunts; the 30 untyped main-story entries use the reviewed fallback in
  `data/quest_sections.json`. Ten quests whose own objectives are about Gwent go to Gwent; the
  `mq7001restinpeace` false positive is excluded by review. The 11th Gwent node is the Vegelbud matches
  bookkeeping step.
- **Quest graph and frontier.** `data/quest_graph.json` carries the journal-activation block for 225
  quests, the five reviewed fact prerequisites, and the three reviewed loss edges. `src/model.rs`
  classifies every step as `done`, `in_log`, `gated`, `available` or `unknown`; `unknown` is available
  and never suppressed.
- **Top section.** `WHAT YOU CAN STILL LOSE` renders only when something has a cost: a fired cutoff over
  an open quest, a Failed quest, a cutoff you are inside, or a missable quest you have already started
  whose closer is still ahead. A quest the journal never started is shown only when you are already
  inside the closer; a distant cutoff in the prologue stays silent. `settled` and `unknown` never
  appear. An empty list hides the section - an empty prologue is the tested, correct answer.
- **DO NEXT.** Tracked quest first, then `in_log`, then safe `available` quests by lowest suggested
  level, then caution (live cutoff) quests; `order` is only the last tie-break. Gated, done, lost and
  unsafe steps never enter. Gwent and Treasure Hunts are section-only unless tracked or caution.
- **Cards and detail.** The card shows the current objective, the game's one-line description, and
  spoiler-free `choice` / `Gwent` / `missable` / `tick disagrees` chips. The detail pane keeps the
  objectives, the activation block, the reviewed cutoff mechanism and the prerequisite facts. Choice
  text, `kb`, `guide`, `start`, `conf`, `note` and `sources` URLs are gone.
- **Wiki path removed.** `src/main.rs` no longer loads `audit_*`, `guide_*` or `feed.json`;
  `package.ps1` no longer packages them. They remain on disk for comparison. `data/feed.json` is kept
  as `data/legacy_feed.json`.
- **Ticks.** The journal-first rule from 0.1.9 is unchanged; a ticked step whose journal is still
  `Active` now carries the `tick disagrees` chip, and the top section still reports the loss. This is
  the statuette case.

## Checks actually run

```
py tools/contradictions.py
  7 derived claims, 0 contradicted; 5 route prerequisites checked, 0 disputed

py tools/regen.py
  all 9 outputs match the recorded hashes

py tools/routegen.py check
  route ok: 403 quest + 11 manual = 414 steps; 11 Gwent; 385 levelled; 79 choice tags;
  7 optional; 4 when; 3 conditional; 4 flags; 3 loss edges

cargo test
  14 passed, 0 failed

py tools/compare_legacy.py
  wrote legacy_comparison.md: 106 legacy nodes with a difference; 1 event replaced, 24 dropped

py tools/fuzz.py
  60 damaged files fed to the readers, 0 unacceptable results
```

The UI was rendered against `--view` payloads from four real saves: prologue (empty top section),
early (lost + failed), mid (lost + failed), and Blood & Wine epilogue (lost). The empty and lost states
come from those saves; the inside/risk state comes from a fixture save whose closer is in the journal.
The missable state (an unstarted quest with the closer active is risk; a started quest with a future
cutoff is missable) is covered by the backend tests and a synthetic UI payload, because the 517-save
corpus contains no save where one of the three reviewed cutoffs is still ahead of a started quest.

The packaged `dist/Witcher3MissablesTracker-0.2.0/Witcher3MissablesTracker.exe --view` was run over the
prologue, mid and epilogue saves and returned the same 414 steps and top states, reading the release's
own `data/`; the tracker-folder copy `Witcher3MissablesTracker.exe` was byte-identical and did the
same over the mid save.

## Limitations

- **Three cutoffs is not a complete missables list.** 24 of the 25 hand-written 0.1.9 events had no
  reviewed `CDeactivateSpawnset` edge naming both the closing and the affected quest, so they were
  dropped rather than shipped as wiki claims. The release reports them; it does not silently keep them.
- **Some journals are unreadable.** `questindex.py` reports 20 unreadable journals on this install;
  those quests have no objectives or activations and appear with whatever the save and journal title
  provide. They are in the route, not hidden.
- **Some quests have no start activator.** 225 of 403 have one; the rest are `unknown`, shown as
  available. No activator never means unavailable.
- **The aggregate `ch1quest` journal is in the route** because it is a `CJournalQuest`; it is an
  "In Ciri's Footsteps" container, not a single playable quest. It has no special treatment yet.
- **Risk/missable top entries were not produced by the corpus with the current three cutoffs**; they
  are covered by unit tests and a synthetic UI payload, not by a real save in this checkout.
- **Choice text is deliberately absent.** The app can say a choice changes the outcome; it cannot say
  which choice or what follows.
- The save reader and the status rules are unchanged from 0.1.9.
