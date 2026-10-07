# Witcher 3 Missables Tracker

A small always-on-top Windows tool that reads your newest Witcher 3 save (read-only) and helps you play a lock-out-free
100% run:

- **DO NEXT**: which quests to do now, in order, with the key choice for each ("DON'T MISS").
- **HOLD OFF**: story events you are about to trigger that would fail quests you still have open.
- **Can I do this now?**: search any quest or contract and get a safe / careful / not-yet answer.
- Click any quest for how to start it, what it needs, whether you can miss it, and the sources.
- **My game**: tell it what a save cannot show (Letho alive, Keira sent to Kaer Morhen, romances) and set your game and
  saves folders if they are not found automatically.

Unofficial fan tool. Not affiliated with CD PROJEKT RED. See `NOTICE.txt`.

## Safety

- It only **reads** your saves. It never writes to the saves folder or the game folder.
- Its own settings (ticks, level, tags, a cached quest index) go to `%APPDATA%\Witcher3MissablesTracker`.
- The code contains no HTTP client and makes no network connections. Source links open in your browser only when clicked.
- The quest index is built on your computer from your own game files (bundle headers). No game data is shipped.
- You can read everything in `src/` (about 1,500 lines of Rust) and `ui/` (plain HTML/CSS/JS), and build it yourself.

## Status and limits

- Developed and tested on the Steam PC version 5.00 (next-gen). Other versions may have different quest data.
- Tested on an early-game save only. Skellige, the endgame and the expansions have not been tested on real saves.
- The rules are compiled from the Witcher Wiki and public guides and may be wrong. Quests marked "quest match: low/med"
  are the least certain. The in-game quest log has the final word.
- Spoilers: quest names, events and ending choices are shown.

## Use of AI and sources

The program code was written with AI assistance (Anthropic Claude) under the author's direction; the author tested it.
The research data in `data/` was compiled with AI-assisted reading of public sources, mainly The Witcher Wiki
(CC BY-SA 3.0) and public walkthroughs, and has not been fully verified against the game. Every quest entry lists the pages
it is based on. Details: `NOTICE.txt` and `LICENSE-DATA.md`.

## Build from source

Requires Windows 10/11, [Rust](https://rustup.rs) and the Visual Studio C++ build tools. Microsoft Edge WebView2 is needed
at run time (part of Windows 11).

```
cargo build --release
```

`package.ps1` builds, assembles and zips a release, and strips local paths from the binary. To check a downloaded
build, build from the matching source and compare behaviour; the code is small enough to read.

## Layout

| Path | What it is |
|---|---|
| `src/save.rs` | Save reader (LZ4 chunks, name table, quest journal). Read-only. |
| `src/bundles.rs` | Finds the game and builds the quest index from the player's own game files. |
| `src/model.rs` | Route engine: prerequisites, cutoffs, DO NEXT, HOLD OFF, safety check. |
| `src/main.rs` | App, settings, commands. |
| `ui/` | Interface (HTML/CSS/JS, no build step). |
| `data/route.json` | The route: quests, prerequisites, events, tags. Edit this to correct the route. |
| `data/audit_*.json`, `data/guide_*.json` | Per-quest research with source links. |
| `docs/BACKEND_CONTRACT.md` | Interface between the backend and the UI. |

## Contributing corrections

Wrong prerequisite, wrong quest match, or a cutoff I missed? Open an issue with the quest, what the tool said, what the game
did, and roughly where you were. Corrections to `data/route.json` are welcome as pull requests.

## Licences

Code: MIT (`LICENSE`). Data: CC BY-SA 3.0 (`LICENSE-DATA.md`). Bundled libraries: `THIRD-PARTY-LICENSES.txt`.
