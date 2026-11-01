# Witcher 3 Missables Tracker {{VERSION}}

A small always-on-top window that reads your newest Witcher 3 save (read-only) and answers one
question: **what do I do next in this save, and what can I still lose?**

- **TRACKED**: one section at the top, always the quest your game is tracking and nothing else.
  Other quests in your log stay in **MORE > PROGRESS**; this is not a second quest log. The card
  shows the current objective, a live warning about that quest, a chip naming every quest finishing
  it would cut off, the ending choice while a reviewed goal still has a step ahead, and any missable
  Gwent card whose source, opening or closing window is one of its steps. The exact ending line
  appears only while guidance is on and that goal is selected; otherwise the card keeps the constant
  sentence "This choice affects an ending."
- **MORE**: one reference drawer, with tabs.
  - **STATUS**: your completion state, without pretending every branch fits in one save. Quests and
    cards are counted separately as done/owned, still possible, at risk, lost or unknown.
  - **CARDS**: the collection ledger, with source and owned/not-owned/unknown. Fifteen cards have a
    reviewed Tier B community closing window; fifteen more are Tier A one-time sources; the other
    194 carry a documented no-window reason. Tier B rows show their source and review date.
  - **COVERAGE**: what the game files can and cannot answer, per pack. A zero is not a clean bill of
    health.
  - **PROGRESS**: every quest in the game, including Hearts of Stone and Blood & Wine, in the game's
    own five sections: Main, Secondary, Contracts, Treasure Hunts, Gwent.
- **Ending goals (optional)**: choose a reviewed goal such as both Blood and Wine sisters living. The
  app then shows the exact line to say on the matching mission. Skip it and the app stays
  spoiler-free; no ending name or line appears until you open the goal picker yourself.
- **Can I do this now?**: search any quest and get a safe / careful / not-yet answer.
- Click a quest for its description, current objective and any warning. The source-file trail is
  there too, but folded away under **Technical details** so it does not get in the way.
- **My game**: tell it what a save cannot show (Letho alive, Keira sent to Kaer Morhen, romances) and
  set your game and saves folders if they are not found automatically.

Unofficial fan tool. Not affiliated with or endorsed by CD PROJEKT RED. The Witcher is a trademark of
CD PROJEKT S.A. See `NOTICE.txt`.

## Run it

1. Unzip the folder anywhere (keep `data` next to the exe).
2. Double-click `Witcher3MissablesTracker.exe`.
3. Needs Windows 10/11 with Microsoft Edge WebView2 (already part of Windows 11).

It finds your game (Steam, GOG or Epic) and your saves by itself, including a moved Documents folder
or OneDrive. If it cannot, open **my game**, go to **Folders**, and press **Browse** (or paste a path
and press **Use**) for the game folder (the one that contains `content` and `bin`) and for the saves
folder (the one with the `.sav` files). Leave a box empty and press **Use** to go back to automatic.

## Is it safe for my saves?

It only **reads** your save files and never writes to your saves folder or the game folder. It writes
only its own settings (ticks, level, tags) and a cached quest index to
`%APPDATA%\Witcher3MissablesTracker`. The tool's own code makes no network connections. The full
source code is public: {{SOURCE_URL}}

## Good to know

- **Spoilers**: quest names, the names of events that close a cutoff, and the fact that a loss
  occurred are shown because they are what you can act on. The app says that a choice changes the
  outcome; it never shows the choice text or recommends an option unless you opt into an ending
  goal and open that mission. The default screen contains no target label, ending name or line.
- **Where the rules come from**: the route, sections, suggested levels, one-line descriptions, start
  blocks, fact prerequisites and cutoffs are generated from the game's own journal files, level
  tables and phase graphs. Ending goals and their lines are reviewed over extracted scene choice
  rows; the app never guesses a line. The older wiki-era research is not shipped in this package and
  is never loaded by the app.
- **my game**: tell it what a save cannot show (Letho alive, Keira sent to Kaer Morhen, romances).
- **What ships**: `data/route.json`, `data/derived.json`, `data/quest_graph.json`, the reviewed
  inputs behind them, and the planner data: `endings.json`, `outcomes.json`, `branches.json`,
  `gwent_cards.json`, `card_windows.json` (the static 224-row evidence report),
  `card_window_review.json` (its reviewed input), `coverage.json` and `exclusive.json`.
  `route.json` has 403 quest steps plus 9 reviewed manual bookkeeping steps: 412 in total, across the
  base game and both expansions. The 1.0.0 baseline's other 2 manual rows were exact duplicates of
  `q108eve` and `q111imlerith` and were replaced by those file-derived steps; see
  `docs/MANUAL-STEPS-AUDIT.md`.
- **What 1.1 does not model**: no card-level window is Tier A gamefile-proven. The 15 reviewed card
  windows are Tier B community evidence and are visibly labelled with their source and review date.
  Blood and Wine card sources are measured; Hearts of Stone has no card pack. Seven cards still have
  an explicit `unknown source` row, never an inferred ownership. "All quests" means the maximum
  consistent set for the chosen goals, not every mutually exclusive branch in one save.
- **One profile is one run.** Changing a goal recomputes the guidance from the save; it does not
  promise that an already-settled choice can be undone.
- Developed and tested on the Steam PC version 5.00 (next-gen). Other versions may differ.
- The save reader has been checked against 500+ real saves, from White Orchard to the Blood and Wine
  epilogue.
- The in-game quest log has the final word.

## AI use and sources

The program code was written with AI assistance (Anthropic Claude) under the author's direction; the
author tested it. The 1.1 route and its rules are generated from the game's own files; the ending
labels and lines are reviewed over those files, not invented. The 15 card windows are community
reviewed and labelled; they are not presented as gamefile truth. The older wiki-era research stays in
the source checkout only and is not part of this package. See `NOTICE.txt`.

## Licences

Code: MIT (`LICENSE`). Game-derived data and legacy research: see `LICENSE-DATA.md`. Bundled libraries:
`THIRD-PARTY-LICENSES.txt`.

## Feedback

Tell me what looked wrong, which quest, and roughly where you were in the game.
