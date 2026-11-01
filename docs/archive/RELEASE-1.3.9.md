# 1.3.9 - Ending quests

## What changed

- The optional ending goals now have a small **ending quests** button beside UP NEXT. It opens a
  scrollable panel grouped into Main game, Hearts of Stone and Blood & Wine; each part collapses
  independently.
- The list comes from the reviewed `get_plan` steps for the chosen goals, not a second quest list.
  Plan steps carry `packs` and `choice`, so the panel can group them and mark a reviewed choice while
  the exact line stays behind the guidance switch.
- A view refresh patches the panel's existing group and card nodes. Collapsed parts, keyboard focus
  and scroll position survive the tracker's 20-second refresh. A changed or cleared goal selection
  closes the panel and cancels the stale plan request.

## What was verified

The UI was served at 480x820 and 360x420 with real `--view` and `--plan` payloads from a four-goal
profile (412 view steps, 7 plan steps: 4 Main game, 1 Hearts of Stone, 2 Blood & Wine). A collapsed
section stayed closed across repeated refreshes; a focused summary and a focused quest button kept
focus; scroll positions 55px and 140px survived; 3 groups, 7 cards and 5 CHOICE chips did not
duplicate. Target state and label changes without an ID change kept the panel open and updated the
labels; an ID change or clear closed it, and a delayed plan response resolving afterwards did not
reopen it. Empty, conflict and blocked plans produced a message or notice without stale cards. Quest
detail opening, the close button and Escape worked, with focus returned to the ending-quests button.

Limitations: the actual Tauri 20-second timer and wheel input were not exercised; the same render
entry point was driven with the real payloads in a browser. The list still contains the reviewed
ending steps only, not a full main-story route.

Artifact: `dist/Witcher3MissablesTracker-1.3.9/Witcher3MissablesTracker.exe`, copied to
`w3tracker/Witcher3MissablesTracker.exe`, FileVersion and ProductVersion 1.3.9, SHA-256
`9BC91F0B1F26968AB6B095EE0F46A27C4CF0591577DD36DAA424E68907331926`. The zip is
`dist/Witcher3MissablesTracker-1.3.9.zip` (21 entries, `testzip()` clean).
