# Release 0.2.2 - a loss needs the journal to fail, not an NPC to leave

2026-10-28. This release fixes two false "cannot be completed" warnings and the rule that produced
them. The route is unchanged; the data, the cutoff review, and two presentation details are not.

## What was wrong

`tools/cutoffs.py` treated a `CDeactivateSpawnset` as proof that a quest was over: if quest E switched
off a community, and quest X referenced that community, it called X lost once E was done. That is not
what the game says. A community switch is a phase transition in most of the story, and it says nothing
about the state of X's journal entry.

Two concrete cases:

- **Haunted House** (`q301visitingdreamer`) was reported lost after Novigrad Dreaming (`q301dreamer`).
  It is the other way round: the quest is activated by
  `q311_after_q301_dreamer_godling_house.w2phase`, a phase that runs *after* Novigrad Dreaming, and
  its one objective - visit the house again - has no failure branch at all. The old review read the
  graph backwards.
- **The Nobleman Statuette / The Soldier Statuette** were reported lost after Now or Never
  (`sq301triss`) because it switches off `triss.w2comm`. Their own phase file
  (`mq3012_jade_statuettes.w2phase`) switches Triss back on for the turn-in, and the game resolves
  the two entries only when Battle Preparations (`q210preparations`) starts: the journal blocks in
  `bugfixing_phase.w2phase` have connected `Failure` inputs gated by that journal. The review had
  picked the earliest community switch instead of the actual failure branch.

In both cases the save stayed `Active` because the quest was still winnable. The app now says that
instead of calling it lost.

## What changed

- **Cutoff evidence rule.** A reviewed community cutoff is accepted only when it also has journal
  failure evidence: at least one save records the affected quest `Failed` after the closer, or the
  affected quest's own graph has a connected `Failure` input whose upstream conditions name the
  closer's journal. A deactivated community alone is not a cutoff.
- **A window must name its failure branch.** `tools/review_cutoffs.py` now walks the graph backwards
  from the `Failure` input, through the logic conditions, and rejects a window whose closer is not
  actually one of those conditions. A dangling `Failure` socket is not evidence. The old `Q310 Gather
  Lodge` statuette window fails this check and cannot come back by editing prose.
- **The statuette window is now Battle Preparations.** The window is
  `q210preparations#Novigrad` (the end of Final Preparations), not `q310preparationsnovigrad#Q310
  Gather Lodge`. The card says "before the end of Final Preparations"; Triss takes the statuettes
  during Final Preparations after the Philippa rescue.
- **Haunted House has no cutoff.** No warning, no "lost" card, just the normal quest step.
- **A passed cutoff still says CHECK NOW, not LOST,** unless the loaded journal marks the quest
  `Failed`. This was already the behaviour; it is now covered by the corrected window too.
- **The current objective is the game's own sentence.** The save carries objective GUIDs, but the
  labels built from its bundles are internal (`SQ202 At Larvik`). The app now maps each active GUID
  to the wording in `derived.json`, so a card reads `Meet Yennefer in Larvik.` instead of the label.
- **The top warning says what to do about it.** Its card now shows the action line as well as the
  sentence: for the statuettes, `Give both statuettes to Triss during Final Preparations`.
- **The save-side check no longer races the game.** The app dump in `tools/contradictions.py` uses a
  copied indexed save instead of whatever autosave the game wrote a second ago, and the reader check
  samples the saves in the index. A check that changes because the player is still playing is not a
  check.

## Data

| | |
|---|---|
| route steps | 414 (403 quest + 11 manual), unchanged |
| reviewed community cutoffs | 1 (Brothers in Arms; 2 saves record an ally quest `Failed` after The Isle of Mists) |
| reviewed journal windows | 1 (the two statuettes, closing at the start of Battle Preparations) |
| steps carrying a warning | 6 |
| saves in the local corpus at build time | 547 |
| old statuette window | rejected by the new graph check |
| old Haunted House cutoff | rejected by the start-order check |

The 25 hand-written 0.1.9 events remain frozen in `data/legacy_events.json`: one is replaced by the
Brothers in Arms file edge and 24 are dropped with their reason recorded.

## Checks actually run

```
py tools/regen.py
  all 9 outputs match the recorded hashes

py tools/contradictions.py
  5 derived claims, 0 contradicted; 5 route prerequisites checked, 0 disputed

cargo test
  16 passed, 0 failed
```

The `--view` payload was checked against the current mid-game save: the only top-section entry is
`MISSABLE` for the two statuettes, with the headline "before the end of Final Preparations" and the
action line "Give both statuettes to Triss during Final Preparations"; Haunted House is `Active` with
no warning. The same payload was rendered through `ui/` in a browser: the top card shows the action,
and the tracked quest reads `Meet Yennefer in Larvik.` rather than an internal label. The packaged
exe is checked against the release's own `data/`.

## Limitations

- **No save in the corpus reaches Battle Preparations with a statuette still open.** The window rests
  on the game's connected Failure branch, not on a save that demonstrates the loss. That is stated in
  the window's caveats.
- **Two quests still have no cutoff** even though players often lose them: the review deliberately
  ships only what the files or a save can prove. The dropped candidates are recorded in
  `data/cutoffs.json` decisions, not silently promised.
- **The corpus is not proof of a negative.** A quest no save ever finishes can be either hard or
  impossible; the review now requires positive failure evidence rather than treating absence as
  evidence.
