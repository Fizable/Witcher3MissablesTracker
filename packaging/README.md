# Witcher 3 Missables Tracker {{VERSION}}

A small always-on-top window that reads your newest Witcher 3 save and tells you:

- **DO NEXT**: which quests to do now, in a lock-out-free order for a 100% run
- **HOLD OFF**: story events you are about to trigger that would fail quests you still have open
- **Can I do this now?**: type a quest or contract name and get a safe / careful / not-yet answer
- Click any quest for how to start it, what it needs, and whether you can miss it (with sources)

Unofficial fan tool. Not affiliated with or endorsed by CD PROJEKT RED. The Witcher is a trademark of CD PROJEKT S.A.

## Run it
1. Unzip the folder anywhere (keep `data` next to the exe).
2. Double-click `Witcher3MissablesTracker.exe`.
3. Needs Windows 10/11 with Microsoft Edge WebView2 (already part of Windows 11).

It finds your game (Steam, GOG or Epic) and your saves by itself, including a moved Documents folder or OneDrive.
If it cannot, open **my game**, go to **Folders**, and press **Browse** (or paste a path and press **Use**) for the game folder
(the one that contains `content` and `bin`) and for the saves folder (the one with the `.sav` files). Leave a box empty and
press **Use** to go back to automatic.

## Is it safe for my saves?
It only **reads** your save files and never writes to your saves folder or the game folder. It writes only its own settings
(ticks, level, tags) and a cached quest index to `%APPDATA%\Witcher3MissablesTracker`. The tool's own code makes no network
connections. The full source code is public: {{SOURCE_URL}}

## Good to know
- Spoilers: quest names, events and ending choices are shown.
- **my game**: tell it what a save cannot show (is Letho alive, did you send Keira to Kaer Morhen, which romances).
- Developed and tested on the Steam PC version 5.00 (next-gen). Other versions may differ.
- Tested on an early-game save only. Later regions and the expansions have not been tested on real saves yet.
- The quest rules are compiled from the Witcher Wiki and public guides and may be wrong. Quests marked "quest match: low/med"
  are the least certain. The in-game quest log has the final word.

## AI use and sources
The code was written with AI assistance (Anthropic Claude) under the author's direction and tested by the author. The research
data was compiled with AI-assisted reading of public sources and has not been fully verified. See `NOTICE.txt`.

## Licences
Code: MIT (`LICENSE`). Research data in `data`: CC BY-SA 3.0 (`LICENSE-DATA.md`), based on The Witcher Wiki.
Bundled libraries: `THIRD-PARTY-LICENSES.txt`.

## Feedback
Tell me what looked wrong, which quest, and roughly where you were in the game.
