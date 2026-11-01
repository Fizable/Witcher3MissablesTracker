# 1.4.0 - TRACKED

## What changed

- **NOW and UP NEXT are one section: TRACKED.** The sticky warning band and the separate queue
  heading are gone. The top section always shows the quest the save is tracking, even when that
  quest is not yet in the journal, has no live warning, or is already finished. Its only empty
  state is a save with no tracked quest at all.
- **The tracked card keeps only facts that belong to that quest.** It is no longer a generic card
  plus a separate band. The payload now carries:
  - `watch`: the tracked quest's own live warnings (an open window, a passed cutoff, a source not
    ready yet).
  - `cutoffs`: every reviewed loss edge the tracked quest closes. This joins the route's loss
    events with live reviewed windows whose `closed_by` names the tracked quest, and names only
    the affected quests the save still has open. The card shows a chip with the count; opening it
    shows the names, the sentence behind the edge, and the reviewed action.
  - `cards`: unowned missable Gwent cards tied to the quest by `source_step`, `window.step` or
    `window.opens.step`. The chip lists the card, its live window label, its mechanism and the
    reviewed community source when there is one.
  - `choice`: unchanged. With guidance on and a goal selected it carries the reviewed line; with
    guidance off it carries only the constant sentence.
- **One source of truth.** `get_view` no longer has a `todo` id list and `Eval` no longer has a
  queue; the UI renders `tracked` directly. There is no second quest log and no ordering step
  between the save and the card. The derivation lives in `src/tracked.rs`: one `Input` and one
  `payload` entry point own the watch rows, cutoffs, Gwent cards and ending choice, and their tests
  sit beside them.
- **Unrelated warnings keep their old reference surfaces.** A live window on another quest is not
  repeated in TRACKED. It stays on that quest's detail page, in MORE > CARDS for card windows and
  in MORE > STATUS for settled losses and checks.
- The `--dump` payload carries the same `tracked` object and no `todo` key. `--view` remains the
  exact payload the window receives.

## What was verified

- `cargo test`: 70 passed, 0 failed. The tracked tests now run under `tracked::tests` and cover the
  Gwent filter (only missable, unowned cards tied to the tracked steps), the cutoff list (names
  every open quest, ignores another quest's closer, does not warn about the quest itself), the
  ending choice and a payload built from the shipped `route.json`, `derived.json` and
  `gwent_cards.json`. `node --check ui/app.js` and `ui/api.js` pass; `cargo fmt --check` could not
  run because rustfmt is not installed in this toolchain.
- The packaged 1.4.0 exe was run with `--view` and `--dump` against the five save-bearing fixtures
  and the clean profile. Every payload has 412 steps, no `todo` key, and `--dump.tracked` equals
  `--view.tracked`; the five save profiles carry a non-null tracked quest and the clean profile
  carries `null`.
- A browser at 480x820, fed by the packaged exe's own payloads, showed one TRACKED card with no
  NOW or UP NEXT section. The median fixture (Get Junior) had no chips. An empty save showed
  "Load a save to see the quest you are tracking."
- The packaged Windows build itself was then launched three times against temporary `APPDATA`
  profiles and inspected through its WebView2 DOM, not just the mock browser. No fixture naturally
  tracks the three special quests, so each copy of the median save changed only the 16 bytes of
  `JTrackedQuest.guid`; the journal, facts, collection and every other save byte stayed untouched.
  - The Isle of Mists (`q402ciri`) rendered one chip, `CUTS OFF 4 QUESTS`, opening to Brothers In
    Arms: Novigrad, Skellige, Velen and Nilfgaard, with the Isle of Mists sentence. It showed no
    Gwent or choice block.
  - A Matter of Life and Death (`sq301triss`) rendered one chip, `GWENT · 3 MISSABLE CARDS`, opening
    to Dandelion, Milva and Vampire: Bruxa, each with `OPEN LATER · COMMUNITY WINDOW`, its
    one-time phase source and the reviewed community citation. It showed no cutoff or choice.
  - Blood on the Battlefield (`q110postbattle`) with the `ciri_witcher` goal and guidance on
    rendered `SAY THIS`, “All right, Velen it is.” and `Ciri lives: witcher ending`, with no chip.
    With guidance off the packaged payload carried the constant sentence and no line.
- Each packaged DOM had exactly one tracked article, the heading `TRACKED`, no `UP NEXT` text and
  no standalone `NOW` heading.
- FileVersion and ProductVersion are 1.4.0. The dist exe, the repo-root exe and the release build
  are byte-identical: SHA-256
  `99CD012628147A56F67C3D7574D9A6E9E20A46CED93CD68F68C466DDFE577205`, 13,646,336 bytes.

Artifact: `dist/Witcher3MissablesTracker-1.4.0/Witcher3MissablesTracker.exe`, also copied to
`w3tracker/Witcher3MissablesTracker.exe`; zip `dist/Witcher3MissablesTracker-1.4.0.zip` has 21
entries and `testzip()` is clean.

Limitations: the three special tracked quests were produced by retargeting the tracked-quest GUID
in copies of one real save, not by saves that naturally track them. The 20-second Tauri refresh was
not re-exercised in the packaged window; the 1.4.0 binary was launched directly and its DOM read
once per profile. The historical `NOW`/`UP NEXT` references in earlier release notes and in the
dated 10.2-10.11 design records were left as history; current docs describe TRACKED only.
