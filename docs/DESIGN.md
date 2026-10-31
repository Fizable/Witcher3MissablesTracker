# Design: what this tracker is for

Written 2026-10-30 from the author's own statement of the goal, after a docs sweep retired seven
plans and probes. This page is the reference the app is held against: a change is judged by whether
it serves it, and an audit is judged by whether every row below is actually delivered.

## 1. The goal

**Warn the player, at the top of the window, what is at risk right now, so the run keeps the endings
they chose.**

The warning is the product. Every other screen exists so that warning can be trusted and so the
player can find what is left.

## 2. The warnings

The top band (`NOW`) must warn about exactly these, and nothing else:

1. **A cutoff.** An action that is about to cost something still saveable, or a moment that has
   arrived and has not been taken.
2. **Order.** Do this quest before that one. A player who has chosen a quest must be told when
   finishing it fails other quests still open in their log.
3. **Gwent cards.** A card window open now. A window that closed already is `MORE > STATUS`.

The fourth warning, a **consequential choice**, belongs to the tracked quest card instead of the
band. The card for the quest the player is on carries the constant sentence "This choice affects an
ending."; the sentence never prints the choice text, the ending name or the recommended option, so
it is safe with guidance off and no goal selected. It is never a NOW row and never a separate row
under the card.

Every quest-window band row names the action, what is lost, and the quest or phase that closes the
window. If the data cannot supply all three, the row does not ship. "Actionable now" means the save
permits the action and the journal has not settled it; it does not mean the player is standing at
the NPC, and the app must never imply that.

The three band warnings apply whether or not an ending has been chosen. A chosen ending changes
which choice line is shown on the tracked card; it is never a precondition for being warned.

Each item is answered by the loaded save: a warning about something the journal has already settled
is not shown, and a choice still ahead is not a NOW item. `LOST IN THIS SAVE` and `CUTOFF PASSED -
CHECK NOW` live on `MORE > STATUS` and the quest page. `UP NEXT` is on the main surface below the
band and carries the tracked quest only.

**Silence is correct.** When nothing can still change, the band is hidden. An empty band is not a
failure state and must not be filled with reference data to look useful.

## 3. Guidance is opt-in, and it is a second layer

By default the app says only that a choice changes the outcome. It never says which choice, or what
follows. The tracked quest card carries the constant sentence "This choice affects an ending." with
no ending name, outcome or recommended option. With guidance toggled on, a goal chosen and that
quest still ahead, the card tells the player what to say in that scene, using the exact line from
the game's own scene data. Turning guidance off removes both the exact line and the choice chip,
leaving the constant sentence. That gate is why choice text can ship at all: the line is reviewed
game text, and the default payload carries none of it.

## 4. One hundred percent is supported, not the headline

The route, the card ledger, coverage and progress are there to make each warning provable and to let
the player find what remains. The tools should carry one run to the maximum obtainable set for that
run's chosen endings. They must not turn the app into a walkthrough checklist, and they must not
print a single completion percentage: one save cannot realize every branch, so the number would lie.

## 5. The surface

Every screen answers one question. If it stops answering that, it is broken even if it renders.

| surface | the question it answers | backend | must never |
|---|---|---|---|
| `NOW` band | what can I act on, right now? | `get_view.top` | show a row that cannot be acted on now, a settled loss, or an ahead card window; pad itself to look busy |
| `UP NEXT` | what do I do next? | `view.todo`, `view.tracked` | repeat an in-log quest other than the tracked one; add a plan step as a second card; show a plan chip, a plan summary or a `PLAN AHEAD` list; re-filter the payload's queue in the UI |
| quest detail | what is this quest, and am I safe to do it? | `get_detail` | put choice text in the default view |
| `can I do this now?` search | is this quest safe yet? | `search`, `check_quest` | answer without naming the blocking quest |
| `MORE > STATUS` | what is settled, and how much is done? | `view.completion`, `view.status` | print one percentage, or hide a settled loss or a passed cutoff |
| `MORE > CARDS` | which cards are left, and which have a window? | `get_cards`, `set_card` | call an invisible card `not owned` |
| `MORE > COVERAGE` | is an empty section actually clean? | `view.coverage` | report a bare zero without the measured count |
| `MORE > PROGRESS` | where am I in the whole game, by section? | `view.completion.matrix` | count a section header that disagrees with the total |
| goal picker | which endings am I aiming for? | `get_targets`, `set_target` | appear in the payload before the opt-in |
| ending quests | which quests do my chosen endings need? | `get_plan` (`packs`, `choice`) | appear without a chosen goal, or list a quest with no reviewed ending step |
| outcome matrix and tradeoffs | which outcomes can still happen, which exclude each other? | `get_outcomes`, `view.tradeoffs` | present a goal with no path as if it had one |
| guidance toggle | tell me the exact line | `set_guidance` | apply without a chosen goal |
| `my game` | what can a save not tell you? | `set_flag`, `set_level`, `set_folder`, `pick_folder` | let a flag overrule the journal |
| header | which save is this, and how old? | `view.save` | hide a read error |
| first-run setup | do you want goals, or stay spoiler-free? | `view.setup` | block the app until answered |
| pin | keep this over the game | `set_pin` | - |

## 6. Invariants

These are not features; they are conditions. A bug is an invariant broken.

1. **Read-only and offline.** Nothing writes to the saves folder or the game folder, and there is no
   HTTP client. Source links open a browser only when clicked.
2. **The journal outranks a tick.** A tick fills a gap the save cannot see; where the journal still
   has the quest open, the tick is set aside and the card says so.
3. **No spoilers by default.** No target label, ending name or choice line in the default payload.
   Proved by `cargo test`, including `top_tests::only_the_journal_can_declare_a_loss`.
4. **One denominator.** 412 route nodes = 403 file-derived quests + 9 reviewed manual rows, and the
   Gwent section keeps 11. Provable by `model::tests::the_generated_route_is_the_whole_game`.
5. **A card window still ahead is a count, not a warning.** It belongs to `MORE > CARDS > LATER`.
6. **Conflicts are stated, not resolved.** Two outcomes in one exclusive group produce a conflict,
   never a silent choice. Proved by `plan::tests::two_outcomes_in_one_group_are_a_conflict`.
7. **Exact lines only on the step the player is on.** Proved by
   `plan::tests::the_plan_orders_by_level_then_route_and_only_ahead_steps_carry_instructions`.
8. **No affiliation claim.** Unofficial fan tool, said in the README and `NOTICE.txt`.

## 7. Refusals

- Not a walkthrough and not a wiki. The game's files decide every rule; the loaded save decides every
  fact about where the player is.
- No second-hand knowledge, no guessed dialogue, no walkthrough text.
- No claim that one save can realize every branch, ending and card.
- No feature whose only job is to display data the band already trusts.

## 8. The check before any change

Ask one question: **does this make the top band more accurate about what is at risk now?** Reference
data may grow, but it must not move into the band. Scope that adds no warning accuracy is what this
page exists to refuse.

## 9. State model (1.3)

### 9.1 One step, four answers

A route step has four separate answers and the payload must not let one impersonate another:

| answer | field | decided by |
|---|---|---|
| the journal's state | `step.journal` | the save's own journal entry, ticks excluded |
| what the card shows | `step.status` | the journal; a manual row may use its tick |
| the six-state matrix | `step.classification.state` | the journal plus a live reviewed warning |
| whether a note disagrees | `step.tick_disagrees` | a tick present while the journal is open |

A tick on a file-derived step is a note. It never changes `status`, `journal` or the matrix, and
it never clears a live warning. A tick on a manual row is the answer, because the save cannot show
that row at all.

### 9.2 Tick truth table

| journal | tick | card | matrix | watch | note chip |
|---|---|---|---|---|---|
| Not started | off | Not started | obtainable (or at risk if a cutoff passed) | present | no |
| Not started | on | Not started | unchanged | present | yes |
| Active | off | Active | at risk / obtainable | present | no |
| Active | on | Active | unchanged | present | yes |
| Done | off | Done | done | cleared | no |
| Done | on | Done | done | cleared | no |
| Failed | off | Failed | lost | cleared | no |
| Failed | on | Failed | lost | cleared | no |

### 9.3 Card-window lifecycle

`not_yet` (no source usable yet; ledger only) -> `ahead` (the closing step has not started;
MORE > CARDS > LATER only) -> `active` (the closing step is open; the only card state in NOW) ->
`check` (the step is done or failed; a check, never a proved loss) -> `lost` only when the save
owns the failure. `owned` and `unknown` are ownership states, not window states. A window that is
`ahead` is never a TopItem. A deck definition is not ownership and not a source.

### 9.4 Warning lifecycle, the band and search

A reviewed warning is rebuilt against the loaded save on every refresh. `settled` and `unknown`
are not warnings. The band accepts `live: open` and `live: inside` window rows, and only when the
row also names its action, the titles it costs and the quest or phase that closes the window. A
row missing any of those does not ship. `lost`, `passed` and `check` are `MORE > STATUS` rows, and
`ahead` is ledger-only. A consequential choice enters the band only when its quest is Active; no
choice text, ending name or recommended option is ever in that row.

A search answer and the quest's own detail page call the same save-aware verdict function, so the
same quest cannot be `safe` on its page and `at risk` in search. Both resolve a step through
`step_short`, so a multi-file node names one journal. The detail page renders `detail.verdict` at the
top under `CAN I DO THIS NOW?`; a hit with no step renders the same `Verdict` in the search panel,
and a hit with a step opens that page. When a warning already carries the verdict's headline, the
page keeps the warning's action and does not print the sentence twice. The default payload carries
no target label, ending name or instruction; only `get_plan` and `get_detail` after the opt-in may
carry an exact line.

### 9.5 The PROGRESS bar

The per-section bar is `done / total` for that section. It is not a whole-game completion
percentage: one save cannot realize every branch, so a single number would lie. The six states and
the section totals are the honest report.

### 9.6 Where a warning may come from

The save has no player-position signal. The app may not claim "you are at the Baron"; it may only
say what the journal, the game files and the reviewed windows prove. Literal location is refused.

## 10. Acceptance record (1.3)

Verified 2026-10-30 against `route.json` (412 nodes), three copied real saves (earliest, median,
newest) and a clean profile with an empty saves folder, all under a temporary `APPDATA`.

| surface | payload | positive test | negative test | last verified |
|---|---|---|---|---|
| NOW band | `get_view.top` | newest: active card window + missable quest | clean and earliest: `top == []`; no `choice` row; a choice lives on `tracked.choice` and never enters `top`; no `ahead` card or quest window; no instruction key | 2026-10-31 |
| UP NEXT | `view.todo` | the tracked quest only, also with a goal selected | clean: 0 ids; the plan adds no card, chip or summary; no other in-log quest; no available quest; no open NOW row; no done/failed id | 2026-10-31 |
| quest detail | `get_detail` | statuette detail reads both/one/neither statuettes from the save's facts; newest says talk to Triss now | clean: `guidance == null`, `info` verdict, no live watch; a lost window keeps its journal verdict | 2026-10-30 |
| search | `search`, `check_quest` | shares `verdict_for` with detail | clean payload has no ending label; no save returns `info`, not `safe` | 2026-10-30 |
| STATUS / PROGRESS | `view.completion` | 412 = 403 + 9; sections 96/183/35/87/11 | no sixth section; no single percentage | 2026-10-30 |
| CARDS | `get_cards`, `set_card` | 224 cards, 14 Tier B missable + 18 one-time, 200 sourced / 23 explicit unknown, Dijkstra's Baron source and office fallback | ahead row is not a NOW item; a one-time reward such as Iorveth never enters `top` or `status`; a deck definition is not ownership; no `not_yet` in `top` | 2026-10-31 |
| COVERAGE | `view.coverage` | measured counts per pack | `with_cards == 0` reads `not modelled` | 2026-10-30 |
| goal picker | `get_targets`, `set_target` | only after opt-in | absent from the clean payload | 2026-10-30 |
| outcomes / tradeoffs | `get_outcomes`, `view.tradeoffs` | engine conflict test | clean tradeoffs empty | 2026-10-30 |
| guidance toggle | `set_guidance` | the tracked card shows the exact reviewed line | only the constant sentence remains; the choice chip is gone and instructions are absent | 2026-10-31 |
| my game | `set_flag` | a flag excludes an unstarted quest | a flag never overrules `Active` | 2026-10-30 |
| header / setup / pin | `view.save`, `view.setup`, `set_pin` | read error named with file and next step | setup card below NOW | 2026-10-30 |

Invariants 1, 3, 4, 5, 6 and 7 each have a named test that fails when the guarantee is broken; the
mutation runs are recorded in `NEXT-PHASE-PLAN.md` section 11. Invariant 2 is the tick truth table
above, tested for every journal state. Invariant 8 is stated in the README and `NOTICE.txt`.

Phase 2 adds the card-source audit: 224 rows = 14 reviewed missable windows (14 Tier B) +
18 one-time sources + 192 documented no-window rows, with 200 sourced and 23 explicit unknown
rows. A deck definition is no longer a persistent source. Dijkstra is a one-time Baron source
(opened by `cgnomansland` and `cg_baron_discovered`, with the office as fallback); Iorveth is a
one-time Shock Therapy completion reward with no reviewed failure branch. The statuette turn-in
reads both/one/neither on the three real saves. `cardwindows.py check` enforces every rule and 13
mutation tests prove the checker fails when the rule is removed.

### 10.1 Six first-run scenarios at 480x820

1. **No save.** The band is hidden; UP NEXT says "Load a save to see what is next."; the folder
   panel opens once with the saves path and a Browse action.
2. **Clean save, no goal.** The band is hidden. UP NEXT carries the tracked quest only; other
   in-log quests stay in PROGRESS. MORE > CARDS > LATER lists the ahead windows.
3. **Cutoff passed.** The band stays hidden, because the action is gone; MORE > STATUS shows
   `CUTOFF PASSED - CHECK NOW` with its headline and next step, and the same warning is on the quest
   page and in search. The corpus has no save in this state, so the row is exercised as a fixture in
   the real `ui/` (section 10.8).
4. **Tick a not-started step.** The card keeps Not started, PROGRESS shows a pencil note rather
   than a green check, and the warning stays.
5. **Goal selected, guidance off.** The tracked card keeps the constant sentence and no exact line;
   no choice chip, plan card or PLAN AHEAD list appears.
6. **Corrupt save.** The header names the file and says the tracker retries; the folder panel can
   be reopened; no stale band from the previous save is presented as current.

### 10.2 1.3.1 verification record

The 1.3.0 post-release audit found a no-save defect in two layers. `verdict_for` treated an empty
journal as every quest being `Not started`, so `--detail mq3012noblestatuette` returned `warn` and
"Find both statuettes..." when no save had been read. The detail pane also falls back to
`derived.watch` when the NOW band has no item for the step, so the static statuette row would still
paint a red warning after the verdict was corrected.

1.3.1 adds `save_is_ready`: a save path exists and the last read did not fail. `live_watch_for`
returns no warning without it, `verdict_for` returns `info` "Load a save to see this quest in your
game" with no details or game-file claim, and `detail_json` clears `derived.watch`; the rest of the
game-file evidence remains. The guard test is
`top_tests::a_missing_or_unreadable_save_is_not_a_live_state`.

Verified 2026-10-30 against the 1.3.1 package (`cargo test --locked`: 57 passed), with the three
real saves copied into isolated profiles and a clean profile with an empty saves folder. All four
ran under a temporary `APPDATA`; the originals were not written and the game was not launched.

| profile | save | top | todo | cards (owned/not/unknown) | detail |
|---|---|---|---|---|---|
| clean | none | 0 | 0 | 0/0/224 | `info` "Load a save..."; `derived.watch=[]`; 0 "Find both" |
| newest | `AutoSave_10d9e0_7ea4f000_581b307.sav` | 2 (`card`, `missable`) | 65 | 129/94/1 | `warn` "Both statuettes in hand - talk to Triss now" |
| median | `ManualSave_5258a_7e224000_39e1473.sav` | 3 (`failed`, `card`, `missable`) | 52 | 114/109/1 | `warn` "You still need the soldier statuette" |
| earliest | `ManualSave_53db8_7e221800_4f13d1b.sav` | 0 | 2 | 27/196/1 | `warn` "Find both statuettes, then talk to Triss" |

The earliest row is the control for the fix: its save is loaded and neither fact is set, so it must
keep the full "Find both" warning. The clean row has no save, so it must not. `--dump` top equals
`--view` top on all three saves. Cards remain 224 = 15 missable (15 Tier B) + 17 one-time + 192
no-window; 200 sourced / 24 explicit unknown. The clean view has `target=null` and `tradeoffs=[]`.

The band's 52vh cue is the container's own thin scrollbar (`#topSec` is `max-height:52vh;
overflow-y:auto`); no extra control was added. The five warning tags are fixed strings: `LOST IN
THIS SAVE`, `CUTOFF PASSED - CHECK NOW`, `DO THIS NOW`, `MISSABLE`, and `ENDING CHOICE AHEAD`, with
`WATCH OUT` as the fallback; no legend is needed because each tag is its own label.

Binary scan: `cargo tree -i reqwest` and `cargo tree -i hyper` print nothing. In the 12,826,112-byte
1.3.1 exe, `reqwest`, `ureq`, `winhttp` and `httpclient` are 0; the seven `hyper` hits are the
keyboard key name `Hyper` in the Windows key-name tables; the 65 `http://` and 14 `https://`
literals are embedded WebView/dictionary text. There is no HTTP client library and no application
call site. This is inspection, not proof about every syscall.

Logs from the last game session (2026-10-29 22:01): W3LoadFix 1.0.8 completed its load stages;
ReShade finished its exit and uninstalled 45 hooks; RenoDX detached and logged process-exit;
NativeBridge registered its functions OK; Beardmos logged its rain timer alive and its water list
grown; OptiScaler's log is older (2026-09-29 14:42) and ends in a normal DLL detach; `scskiller.log`
ends normally. These logs are from the user's session, not from a launch by this work.


### 10.3 1.3.2 verification record

1.3.0 and 1.3.1 put a quest cutoff whose closing quest had not started into the NOW band and turned
it into a `warn` verdict on the quest page. The statuettes were the visible case: the band told the
player to hand them in before Final Preparations while that quest was not in the log. 1.3.2 keeps
`ahead` out of the band (as card windows already were), stops `verdict_for` overriding the route
answer for it, and removes the row from the step payload and the detail pane. A quest with only a
future window is `obtainable`, not `at_risk`. The gate is unchanged - the closing quest's journal -
so the row returns as `DO THIS NOW` when Final Preparations is Active.

Verified 2026-10-30 on `QuickSave_10aa70_7ea4f400_4141f72.sav` in a temporary profile: `--view` top
held the Iorveth card alone where 1.3.1 also carried the statuette row; the statuette step's watch
was empty and its classification `obtainable`; `--detail mq3012noblestatuette` returned `safe` with
`derived.watch=[]` where 1.3.1 returned `warn` and "Both statuettes in hand - talk to Triss now".
`cargo test --locked` reports 57 passed, and the band test now asserts that an `ahead` window on an
Active quest yields an empty top.

### 10.4 1.3.3 verification record

1.3.2 stopped an ahead quest window from padding the band, which removed a false warning and also
silenced the real first chance. Triss is the statuette turn-in and she leaves Novigrad on Now or
Never; the statuette phase switches her community back on for its own scene, so the journal does not
fail the quests when she goes. Missing her is an availability gap, not a loss.

1.3.3 adds a reviewed window with `mechanism: "availability"` that closes at `q309mages#To Triss`,
the first phase of Now or Never. `tools/review_cutoffs.py` accepts it without a Failure branch
because none exists, after checking the phase against the journal and requiring named file evidence.
`model::live_cutoff` evaluates it separately: closer not started gives `live: "open"` and a
`DO THIS NOW` band row with the save's turn-in wording; closer started or done gives `live: "later"`,
level info, and the sentence naming Final Preparations, which is never a band item and never a loss.
The existing `q210preparations#Novigrad` window still covers the second chance, and `live_watch_for`
ranks `inside` above `later` so the quest page shows the actionable window when both apply.

Verified 2026-10-30 on four saves copied into temporary profiles: the earliest
(`ManualSave_53db8_7e221800_4f13d1b.sav`, both quests not started) answered `warn` with "Find both
statuettes, then talk to Triss"; the median (`ManualSave_5258a_7e224000_39e1473.sav`, quests Active,
Now or Never not started) put `DO THIS NOW` "Hand both statuettes to Triss before she leaves
Novigrad" in the band; the newest (`AutoSave_10d9e0_7ea4f000_581b307.sav`) and the reported
`QuickSave_10aa70_7ea4f400_4141f72.sav` (both after Now or Never) returned `info` "Triss has left
Novigrad - the next chance is Final Preparations" with only the Iorveth card in the band.
`cargo test --locked` reports 59 passed; the two new tests cover the open window and the closed one.
`py tools/regen.py --check` reports all 11 outputs matching.

### 10.5 Band and main-surface restoration (2026-10-30)

An uncommitted post-1.3.3 realignment removed `ENDING CHOICE AHEAD` from `top`, moved `UP NEXT` and
`PLAN AHEAD` under `MORE > PLAN`, and replaced the queue with a tracked card. That contradicted the
locked decisions: the choice warning is a NOW item and `UP NEXT` is the main surface under the band.
This pass restored both, kept the correct part of the realignment (settled losses and checks on
`MORE > STATUS`), and removed the tracked card and the extra `PLAN` tab. `view.tracked` is back to
its 1.3.3 shape, so no choice sentence is duplicated outside the band.

| copied save | band tags | UP NEXT ids | statuette watch | detail verdict |
|---|---|---|---|---|
| clean | `[]` | 0 | `[]` | `info` "Load a save" |
| earliest | `[]` | 2 | 1 | `warn` "Find both" |
| median | `DO THIS NOW`, `CARD WINDOW OPEN` | 51 | 1 | `warn` "You still need the soldier statuette" |
| newest | `CARD WINDOW OPEN` | 60 | 1 | `info` "Triss has left" |
| goal (newest, four goals) | `CARD WINDOW OPEN` | 61, includes `q110postbattle` | 1 | `info` |

The earliest band is empty because its statuette window is on a quest the journal never started:
an open window is only a NOW item when the quest is in the log. The clean profile has no save, so
`view.steps` and the plural matrix now report no live watch and `at_risk` 0 instead of two statuette
rows; `live_watch` is the single gate both `view()` and `detail_json` use.

The queue is the backend's `view.todo` as-is. The UI no longer re-derives which plan steps are
"current", so the next plan step (`q110postbattle` with a goal selected) reaches UP NEXT even though
it is not in the log.

Checks: `cargo test --locked` reports 64 passed; `cargo build --release` is warning-free. The two
new guards are `a_choice_in_an_active_quest_is_a_now_item_without_the_choice_text` and
`a_watch_needs_a_usable_save_on_every_surface`; removing the `ending_relevant` check or the
save-ready check makes its test fail. `--view` and `--dump` agree on `top` and `todo` in all six
profiles; 412 nodes and section totals 96+183+35+87+11 hold; the clean payload has no target,
tradeoff, goal step or watch.

No real save among all 518 in the corpus has one of the three `ending_relevant` route steps Active,
so the choice row is proved at the payload level by the unit test and at 480x820 by serving the real
`ui/` with the row added to an otherwise unmodified goal-profile payload. RECORDED LIMITATION: the
choice row is not exercised end to end from a real save; the data has three ending-relevant nodes,
none currently in the log.

### 10.6 Search verdict parity (2026-10-30)

The search box used to dead-end on every route hit: all hits carry a step, so a click opened the
detail pane, and the detail pane never rendered `d.verdict`. The answer existed in the payload and
was invisible. The detail page now renders `detail.verdict` under `CAN I DO THIS NOW?`; a hit
without a step still renders the same `Verdict` in the search panel. Both surfaces use
`verdict_for`, and `step_short` makes search and detail name the same journal for a multi-file step.
When a warning carries the verdict's headline, its action moves into the verdict card and the
duplicate sentence is not printed.

Verified at 480x820 through the real `ui/` and real `--detail` payloads, in a temporary `APPDATA`.
For `mq3012noblestatuette`, typing `Nobleman` and pressing Enter opens the page; the rendered
`.verdict-text` was asserted equal to the `--detail` headline:

| profile | `--detail` verdict | rendered headline | equal |
|---|---|---|---|
| clean | `info` "Load a save to see this quest in your game" | the same | yes |
| earliest | `warn` "Find both statuettes, then talk to Triss" | the same | yes |
| median | `warn` "You still need the soldier statuette" | the same | yes |
| newest | `info` "Triss has left Novigrad - the next chance is Final Preparations" | the same | yes |
| goal (newest, four goals) | the newest headline | the same | yes |

Opening the same step from its UP NEXT card rendered the same headline. An empty (`zzzz`) and a
one-letter query leave the verdict panel hidden and show no hit. The new unit test
`a_step_names_one_journal_for_search_and_detail` covers the multi-file resolution;
`cargo test --locked` reports 65 passed and `cargo build --release` is warning-free.

RECORDED LIMITATION: no real save in the 518-file corpus has one of the three `ending_relevant`
route steps Active, so the choice warning still has no real-save end-to-end run.

### 10.7 Card and statuette truth tables (2026-10-30)

The release binary was run on four copied saves in temporary `APPDATA` profiles: clean (no save),
earliest `ManualSave_53db8_7e221800_4f13d1b.sav`, median `ManualSave_5258a_7e224000_39e1473.sav`,
and newest `CheckPoint_10083c_7ea4f400_4f324d3.sav`. The statuette facts were read with `--facts`;
the card ownership and window with `--cards`; the band, step watch and verdict with `--view`,
`--dump` and `--detail`. A direct scan of all 518 saves supplied the corpus counts below. The
temporary assertion script is `.next-phase/truth/assert.py`; it exited 0 and printed
`PASS: 4 real profiles, 518 corpus saves, 418 Baron-fact card rows`.

| statuette case | save | facts | `top` | step `watch` | `--detail` verdict |
|---|---|---|---|---|---|
| neither | earliest | neither | `[]` (quests not in the log) | `open` "Find both statuettes, then talk to Triss" | `warn`, the same |
| one (noble) | median | `mq3012_noble_statuette` | `DO THIS NOW` "You still need the soldier statuette" | `open`, the same | `warn`, the same |
| both | newest | both | `[]` (Triss has left) | `later` "Triss has left Novigrad - the next chance is Final Preparations" | `info`, the same |
| both, window open | none | both with Now or Never not done: 0 saves | expected `DO THIS NOW` "Both statuettes in hand - talk to Triss now" | the same | `warn`, the same |

The last row is unreachable in the corpus: all 174 saves with both facts have Now or Never Done,
and no save has Battle Preparations Active. It is proved at the data level by
`model::tests::the_shipped_statuette_windows_name_both_one_and_neither`, which reads the shipped
`data/cutoffs.json` and asserts the exact both, noble-only, soldier-only and neither wording for both
reviewed windows. At 480x820 the real `ui/` rendered that exact row and verdict from a fixture
payload built from the shipped wording; the DOM read back the same headline. There is no save with
the soldier statuette and not the noble one, so that one-fact branch has a unit test only.

The median run exposed one seam before this record: `view.steps[].watch` and the band carried the
generic "Hand both statuettes" while `--detail` already named the missing soldier. `read_warning` is
now the one save-aware read used by the step card, the band and `live_watch_for`; it applies
`turn_in_text` before any surface sees the row. The three surfaces now carry the same wording.

| Dijkstra case | real save | owned | `window_live` | `top` / `status` |
|---|---|---|---|---|
| no save | clean | `unknown` | `unknown` | none |
| Baron undiscovered | earliest | `not_owned` | `not_yet` "SOURCE NOT YET · ONE-TIME · TIER A" | none |
| owned | median, newest | `owned` | `owned` | none |
| pre-line, unowned | none | `not_owned` | expected `active` | none; a one-time row is never a band row |
| post-line, unowned | none | `not_owned` | expected `check`, "PASSED - CHECK FALLBACK · ONE-TIME · TIER A" | none |

The two unowned rows cannot be produced by the corpus: all 418 saves with `cg_baron_discovered`
and Gwent: Velen Players Active or Done own the card (411 Done, 7 Active). The 97 saves with the
quest not started have no Baron fact and are `not_yet`; the 3 Active saves without the fact also own
the card. `cards::tests::the_shipped_dijkstra_window_is_open_before_the_baron_line_and_gone_after`
reads `data/gwent_cards.json` and asserts the not-yet, ahead, active, check-fallback and owned
states, and that no one-time row enters `top` or `status`. Dijkstra is `check`, not `passed`, after
the line because the office fallback is reviewed; a one-time window without a fallback still reaches
`passed` in the synthetic test.

`cargo test --locked` reports 67 passed; `cargo build --release` is warning-free. `--view` and
`--dump` agree on `top` and `todo` on all four profiles; the 412 steps and section totals
96+183+35+87+11 hold; the clean profile has `at_risk` 0 and no watch.

### 10.8 1.3.4 verification record (2026-10-31)

1.3.4 packages the band and surface work recorded in 10.5-10.7. The 1.3.3 artifact predated those
changes, so this release was built again from the tree and the checks below were run against the new
package, not against a previous pass's claim.

The headless commands ran on four copied saves in temporary `APPDATA` profiles: clean (no save),
earliest `ManualSave_53db8_7e221800_4f13d1b.sav`, median `ManualSave_5258a_7e224000_39e1473.sav`,
newest `CheckPoint_10083c_7ea4f400_4f324d3.sav`, plus the four-goal profile and the same profile with
guidance off. Every profile had 412 steps, section totals 96+183+35+87+11, and `--dump` matched
`--view` on `top`, `todo` and the warning rows (`dump.status_rows` equals `view.status`).

| profile | `top` tags | `todo` | cards owned/not/unknown | statuette answer |
|---|---|---|---|---|
| clean | `[]` | 0 | 0/0/224 | `info` "Load a save to see this quest in your game"; no watch |
| earliest | `[]` | 2 | 27/196/1 | `warn` "Find both statuettes, then talk to Triss" |
| median | `DO THIS NOW`, `CARD WINDOW OPEN` | 51 | 114/109/1 | `warn` "You still need the soldier statuette" |
| newest | `CARD WINDOW OPEN` | 60 | 129/94/1 | `info` "Triss has left Novigrad - the next chance is Final Preparations" |
| goal | `CARD WINDOW OPEN` | 61, includes `q110postbattle` | 129/94/1 | the newest answer |
| goal, guidance off | `CARD WINDOW OPEN` | 61 | 129/94/1 | the newest answer; 7 plan steps, 0 instructions, 4 goal chips |

The six first-run scenarios were driven at 480x820 in the real `ui/` against payloads produced by
the release binary. The no-save payload hid the band, read "Load a save to see what is next" in UP
NEXT, and opened FOLDERS with the saves path and Browse. The earliest save hid the band and carried
only the tracked and in-log quests; MORE > CARDS > LATER held 31 ahead cards. The cutoff-passed row
has no real save, so a fixture row was rendered in MORE > STATUS: the tag and action appeared there,
the band stayed hidden, and the quest and search pages returned the same `warn` verdict. A
note-only tick on `q110postbattle` kept the card `Not started`, showed the pencil in PROGRESS and
the NOTE block on the detail page, and left the band's statuette warning in place. The goal-off
profile kept PLAN AHEAD and the GOAL chip and rendered no exact line. The corrupt-save payload,
loaded twice, named `CheckPoint_corrupt.sav` both times, said the tracker retries, reopened FOLDERS
and painted no band.

`cargo test --locked` reports 67 passed; `cargo build --release` is warning-free; `node --check
ui/app.js` passes. `py tools/regen.py --check`, `py tools/cardwindows.py check`, `py
tools/test_cardwindows.py` (13 tests), `py tools/cards.py check`, `py tools/endings.py check
--release` and `py tools/outcomecheck.py --release` are green. The temporary payload assertion
exited 0 with `PASS: 4 real profiles, 518 corpus saves, 418 Baron-fact card rows` and statuette
combos `{'both': 174, 'noble': 263, 'soldier': 0, 'neither': 81}`.

The artifact is `dist/Witcher3MissablesTracker-1.3.4/` with FileVersion 1.3.4. Its exe SHA-256 is
`9b7d8454a50e185754b785f338ef810ac2ecd118c8574c59c2209b1cac4cf02d`, identical to the freshly built
`target/release/witcher3-missables-tracker.exe`; the packaged binary matched the target build on every
median `--view` field except the save's elapsed age, and on `--cards`. The zip has 21 entries and
`testzip()` is clean.

RECORDED LIMITATIONS: no save has both statuettes with the window open, a soldier-only statuette, an
unowned Dijkstra past the Baron line, an Active ending-relevant quest, or a passed cutoff check.
Those rows are proved by shipped-data unit tests or fixture payloads, not by a real save. The native
Tauri WebView was not automated; the real `ui/` was driven in Chromium at 480x820 with a mock built
from the release binary's payloads.

### 10.9 UP NEXT simplification (2026-10-31)

The 1.3.4 window still listed every in-log quest in UP NEXT, so The Nobleman Statuette and The
Soldier Statuette appeared there even when their only live action was a later Triss turn-in. That
made the queue a second quest log and contradicted the README's "only what you can act on now".

The rule is now: `view.todo` is the tracked quest plus the single next unblocked plan step. Other
in-log quests stay in `MORE > PROGRESS`; a quest whose open window is already a NOW row is removed by
the remaining guard. A tracked quest still enters even when its journal has not opened, and the one
next plan step enters by name; nothing else does.

Superseded by 10.10: the plan step no longer enters `view.todo`; the queue is the tracked quest
only. The statuette result below still holds.

| copied profile | `view.todo` | queue content | statuettes in queue |
|---|---|---|---|
| clean | 0 | none | no |
| earliest | 1 | tracked `q001beggining` | no |
| median | 1 | tracked `q302mafia`; band still says "You still need the soldier statuette" | no |
| newest | 1 | tracked `q401_phylactery` | no |
| goal (newest) | 2 | tracked + next plan step `q110postbattle` | no |

At 480x820 the real `ui/` rendered one tracked card on the newest profile, one tracked card plus the
statuette warning in NOW on the median profile, and two cards on the goal profile. The page stayed
480 wide with no horizontal overflow and no console errors. The packaged 1.3.5 WebView showed the
same one-card queue on the newest copied save, read through WebView2's debugging port. `--dump`
matched `--view` on `todo` for all seven profiles. `cargo test --locked` reports 67 passed; `cargo
build --release` is warning-free; `node --check ui/app.js` passes.

### 10.10 Choice on the tracked card and tracked-only UP NEXT (2026-10-31)

Supersedes 10.9. The plan step no longer enters `view.todo`; the queue is the tracked quest only.
The consequential-choice warning is no longer a NOW row: it is stated inside the tracked quest card.

What changed, in the shipped `ui/` and payload:

- `get_view.top` carries three warning kinds only: cutoff, order and an active card window. No
  `choice` TopItem is built. A choice is answered by `tracked.choice`.
- `tracked.choice` is null when the tracked quest has no open `ending_relevant` step or its plan step
  is not `ahead`. With guidance off it is `{"guided": false, "text": "This choice affects an
  ending.", "lines": []}`. With guidance on and a goal selected it carries the exact reviewed line
  and its target, e.g. `I'll pay you for the ribbon.` / `bw_both_sisters`.
- `view.todo` is the tracked quest and nothing else, with or without a goal. The removed plan card,
  `PLAN` chip, plan summary (`5 ahead · 1 set · ready`) and `PLAN AHEAD` list have no element left
  in `ui/index.html`, and `ui/app.js` no longer renders them.
- Guidance off removes both the exact line and the choice chip from the tracked card, leaving the
  constant sentence. Informational quest tags (for example `Gwent` on Get Junior) are not choice
  chips and stay.
- Iorveth is a one-time Shock Therapy completion reward (`kind: "one_time"`), so it is in the card
  ledger but never in `top` or `status`.

Payloads from the packaged 1.3.7 exe, each run with its own temporary `APPDATA` and a copied save
folder. No Documents save or setting was read.

| profile | save | `top` | `todo` | tracked card | `tracked.choice` |
|---|---|---|---|---|---|
| clean | no save | `[]` | `[]` | none | null |
| earliest | `ManualSave_53db8_7e221800_4f13d1b.sav` | `[]` | `[q001beggining]` | Kaer Morhen | null |
| median | `ManualSave_5258a_7e224000_39e1473.sav` | `[DO THIS NOW]` soldier statuette | `[q302mafia]` | Get Junior | null |
| newest | `AutoSave_10d9e0_7ea4f000_581b307.sav` | `[]` | `[wolfupgrades2b]` | Wolf School Gear Part 4 | null |
| goal | newest + `bw_both_sisters`, guidance on | `[]` | `[wolfupgrades2b]` | Wolf School Gear Part 4 | null |
| goaloff | same, guidance off | `[]` | `[wolfupgrades2b]` | Wolf School Gear Part 4 | null |

`--cards` on the same exe reports 224 cards: 14 missable (14 Tier B), 18 one-time, 192 no-window,
23 explicit unknown, 1 unknown ownership; `windows.tier_a` 186, `windows.tier_b` 15,
`windows.tier_c` 23. `py tools/cardwindows.py check` passes. `cargo test --locked` reports 68
passed, including the shipped-data test that Iorveth is `one_time` and never a band or status row.

No copied save tracks an ending-relevant quest, so no real profile exercises `tracked.choice`. The
choice render is a documented fixture assembled from the release payloads, not invented text: the
tracked step is `q704bfairyland` (Beyond Hill and Dale...), and the line
`I'll pay you for the ribbon.` and target `Blood and Wine: both sisters live` come from the same
exe's `--plan` output for `bw_both_sisters`. This is the only place in 10.10 where the input is a
fixture rather than a save.

The real `ui/` was driven in Chromium inside a 480x820 iframe, one root per profile, with a mock
built by the release exe. Every profile stayed 480 wide (`scrollWidth == clientWidth == 480`) with
no horizontal overflow and no console errors. Each non-clean profile rendered exactly one tracked
card; median also rendered the soldier-statuette `DO THIS NOW` row. No page had `#planNote`,
`#planAhead` or a plan summary. On the choice fixture the block was inside the card
(`card.contains(choice)` true), above the footer (`choice.bottom == 382`, `footer.top == 391`), with
no `SAY THIS` heading, no exact line and no chip when guidance was off; the paragraph
"This choice affects an ending." occupied the same slot (`choice.bottom == 337`,
`footer.top == 346`). With guidance on the block read `SAY THIS`, the exact line and the target
label. Screenshots were captured at 480 wide for clean, earliest, median, newest, goal, goaloff and
both choice fixtures; this model cannot view images, so the pixel check was a rendered DOM and
layout measurement, not an eyeball read. The images were left for the user to open.

The render found one pre-existing 480px defect unrelated to the plan work: the clean-state
`#saveError` prints a long saves path, which did not break, so the page scrolled to 510 wide.
`ui/style.css` now gives `.save-error` `overflow-wrap: anywhere`, the same rule the other text
rows already use. The error text is unchanged; it wraps inside its 449px box and the page measures
480 again. This is why the package is 1.3.7 and not the 1.3.6 built before the render.

Artifact: `dist/Witcher3MissablesTracker-1.3.7/Witcher3MissablesTracker.exe`, copied to
`w3tracker/Witcher3MissablesTracker.exe`, FileVersion and ProductVersion 1.3.7, SHA-256
`883515640D4C79D44B4FCEC33C1C3A5720A3416C5228C3CA3038C1D113023589`. The 1.3.6 folder built
earlier in this pass is left untouched.

RECORDED LIMITATION: `missable_windows.note` still calls all 15 Tier B community rows "windows";
14 are missable and one (Iorveth) is a one-time source. The counts are right and the card ledger
shows the difference; only that generated sentence is imprecise.

### 10.11 Short-window fix for the my game panel (2026-10-31)

The gear panel sat inside the header, and the header was `flex: none` while `body` was
`overflow: hidden`. Opening the panel therefore grew the header by the panel's full content
height. At 480x820 that fit; below roughly 820px it did not, and the window has its own
`minHeight` of 420 in `tauri.conf.json`. The panel is 719px tall on the newest copied save, so a
resized window clipped the goal row and the folder pickers with no way to scroll them: the page
itself is not scrollable by design.

Reproduced at 480x520 and 480x360 before the change: `#hdr` measured 823px (`clientHeight` 822),
`#flagsPanel` 719px starting at y=93, `flagsBottomVisible` false, body overflow `hidden`,
`window.scrollY` 0 and no scrollable ancestor. The panel's last row ("Use" for the saves folder)
was unreachable at any window height below 812px.

The fix is purely CSS in `ui/style.css` and adds no element and no script:

- `#hdr` keeps `flex: none` but gains `max-height: 100vh`, `display: flex` and
  `flex-direction: column`, so the header can never be taller than the window.
- `#hdr > :not(#flagsPanel) { flex: none; }` keeps the two title rows, the band and the setup
  gate at their natural height; only the panel is allowed to shrink.
- `#flagsPanel` becomes `flex: 0 1 auto; min-height: 0; overflow-y: auto`, so the panel takes the
  leftover height and scrolls inside itself.

The title rows, the gear button, the close behaviour, `#listPane` and the goal picker markup are
unchanged; `app.js` still just toggles `hidden` on `#flagsPanel`.

Measured on the real `ui/` in Chromium, one root per window height:

| viewport | `#hdr` | panel client | panel scroll | scrollTop | last control in view | pane when closed |
|---|---|---|---|---|---|---|
| 480x360 | 360 (max 360px) | 256 | 719 | 463 | "Use" at 301-331 | 266 |
| 480x420 | 420 (max 420px) | 316 | 719 | 403 | "Use" at 361-391 | 326 |
| 480x520 | 520 | 416 | 719 | 303 | last control in view | 426 |
| 480x820 | 94 (unchanged) | 716 | 719 | 0 | whole panel in view | 726 |

The gear button stayed visible (y 21-45) at every height, the page never scrolled horizontally
(`scrollWidth == clientWidth == 480`), and closing the panel returned the header to 94px and the
list pane to its full height. At 360 the goal picker still fits: `.picker-box` scrolls
(`clientHeight` 187 of 260 content) and `Apply goals` stays in view at y 233-261 without the
matrix and y 269-298 with it open. The outcome matrix, the goal row and the folder pickers were
all reachable after scrolling the panel, with no console errors.

The packaged 1.3.8 exe was then driven in its own WebView2, with a temporary `APPDATA` whose
`settings.json` points at a copied save folder, through the WebView2 debugging port. The window
refuses to go below its `minHeight` of 420, so the smallest real client area measured 464x381: the
header capped at 381px, the panel scrolled 277px of 719px, and "Use" landed at y 322-352 inside the
window. At the default size (464x781) the header stayed 94px, the panel showed 677px of 719px and
scrolled 42px to reach "Use" at y 722-752, and closing the panel returned the header to 94px and
the pane to 687px. This confirms the shipped binary carries the new CSS, not just the source tree.

Screenshots of the open panel at 360, 420 and 820 are in
`%TEMP%\opencode\w3realign\shot-final-panel-{360,420,820}.jpeg`. This model cannot read images,
so the check above is a rendered DOM and layout measurement, not an eyeball read; the images are
left for the user.

Artifact: `dist/Witcher3MissablesTracker-1.3.8/Witcher3MissablesTracker.exe`, copied to
`w3tracker/Witcher3MissablesTracker.exe`, FileVersion and ProductVersion 1.3.8, SHA-256
`DEC36362BC24FBC34B5BFB705543DAE8532C11C592F1DD634BDE2568E4CA027D`.

## 11. How an audit uses this page

- **Completeness:** every row of section 5 delivers its question, and every invariant in section 6
  holds. A row with no command, no visible element or no test behind it is an unfinished feature.
- **Bugs:** an invariant violated, or a row answering a question that is not its own.
- **Learnableness:** with the window pinned over the game, one save loaded and no goal chosen, a
  first-time player should be able to tell what is at risk, tell what to do next, find how to tick a
  step, find the goal picker, know what `MORE` holds, and recover from a missing save or a folder
  that was not found.
