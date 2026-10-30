# Design: what this tracker is for

Written 2026-10-30 from the author's own statement of the goal, after a docs sweep retired seven
plans and probes. This page is the reference the app is held against: a change is judged by whether
it serves it, and an audit is judged by whether every row below is actually delivered.

## 1. The goal

**Warn the player, at the top of the window, what is at risk right now, so the run keeps the endings
they chose.**

The warning is the product. Every other screen exists so that warning can be trusted and so the
player can find what is left.

## 2. The four warnings

The top band (`NOW`) must warn about exactly these, and nothing else:

1. **A cutoff.** An action that is about to cost something still saveable, or a moment that has
   arrived and has not been taken.
2. **Order.** Do this quest before that one. A player who has chosen a quest must be told when
   finishing it fails other quests still open in their log.
3. **Gwent cards.** A card window closing now, or one that closed already.
4. **A consequential choice.** That this quest contains a choice that matters to the endings in play.

All four apply whether or not an ending has been chosen. A chosen ending changes which choices are
named and what line is shown; it is never a precondition for being warned.

Each item names what is lost and which quest causes it, and each is answered by the loaded save: a
warning about something the journal has already settled is not shown.

**Silence is correct.** When nothing can still change, the band is hidden. An empty band is not a
failure state and must not be filled with reference data to look useful.

## 3. Guidance is opt-in, and it is a second layer

By default the app says only that a choice changes the outcome. It never says which choice, or what
follows. With guidance toggled on and a goal chosen, it tells the player what to say in that scene,
using the exact line from the game's own scene data. That gate is why choice text can ship at all:
the line is reviewed game text, and the default payload carries none of it.

## 4. One hundred percent is supported, not the headline

The route, the card ledger, coverage and progress are there to make each warning provable and to let
the player find what remains. The tools should carry one run to the maximum obtainable set for that
run's chosen endings. They must not turn the app into a walkthrough checklist, and they must not
print a single completion percentage: one save cannot realize every branch, so the number would lie.

## 5. The surface

Every screen answers one question. If it stops answering that, it is broken even if it renders.

| surface | the question it answers | backend | must never |
|---|---|---|---|
| `NOW` band | what can I still lose, right now? | `get_view.top` | show a settled loss, or pad itself to look busy |
| `UP NEXT` | what do I do next? | `view.todo`, `view.tracked` | list future goal steps alongside actionable ones |
| `PLAN AHEAD` | what is still coming in my chosen run? | `view.target`, `get_plan` | compete with `UP NEXT` as a second to-do list |
| quest detail | what is this quest, and am I safe to do it? | `get_detail` | put choice text in the default view |
| `can I do this now?` search | is this quest safe yet? | `search`, `check_quest` | answer without naming the blocking quest |
| `MORE > STATUS` | how much is done, in six honest states? | `view.completion` | print one percentage |
| `MORE > CARDS` | which cards are left, and which have a window? | `get_cards`, `set_card` | call an invisible card `not owned` |
| `MORE > COVERAGE` | is an empty section actually clean? | `view.coverage` | report a bare zero without the measured count |
| `MORE > PROGRESS` | where am I in the whole game, by section? | `view.completion.matrix` | count a section header that disagrees with the total |
| goal picker | which endings am I aiming for? | `get_targets`, `set_target` | appear in the payload before the opt-in |
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

### 9.4 Warning lifecycle and search

A reviewed warning is rebuilt against the loaded save on every refresh. `settled` and `unknown`
are not warnings. A search answer and the quest's own detail page call the same save-aware verdict
function, so the same quest cannot be `safe` on its page and `at risk` in search. The default
payload carries no target label, ending name or instruction; only `get_plan` and `get_detail`
after the opt-in may carry an exact line.

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
| NOW band | `get_view.top` | newest: active card window + missable quest | clean and earliest: `top == []`; no `ahead` card; no instruction key | 2026-10-30 |
| UP NEXT | `view.todo` | tracked + in-log + next plan step only | clean: 0 ids; no available quest; no done/failed id | 2026-10-30 |
| PLAN AHEAD | `view.target`, `get_plan` | plan survives guidance off; instructions gone | no plan with an empty target | 2026-10-30 |
| quest detail | `get_detail` | statuette detail carries the live warning | clean: `guidance == null` | 2026-10-30 |
| search | `search`, `check_quest` | shares `verdict_for` with detail | clean payload has no ending label | 2026-10-30 |
| STATUS / PROGRESS | `view.completion` | 412 = 403 + 9; sections 96/183/35/87/11 | no sixth section; no single percentage | 2026-10-30 |
| CARDS | `get_cards`, `set_card` | 224 cards, 15 Tier B, 129/94/1 owned | ahead row is not a NOW item | 2026-10-30 |
| COVERAGE | `view.coverage` | measured counts per pack | `with_cards == 0` reads `not modelled` | 2026-10-30 |
| goal picker | `get_targets`, `set_target` | only after opt-in | absent from the clean payload | 2026-10-30 |
| outcomes / tradeoffs | `get_outcomes`, `view.tradeoffs` | engine conflict test | clean tradeoffs empty | 2026-10-30 |
| guidance toggle | `set_guidance` | plan and chips remain | instructions absent | 2026-10-30 |
| my game | `set_flag` | a flag excludes an unstarted quest | a flag never overrules `Active` | 2026-10-30 |
| header / setup / pin | `view.save`, `view.setup`, `set_pin` | read error named with file and next step | setup card below NOW | 2026-10-30 |

Invariants 1, 3, 4, 5, 6 and 7 each have a named test that fails when the guarantee is broken; the
mutation runs are recorded in `NEXT-PHASE-PLAN.md` section 11. Invariant 2 is the tick truth table
above, tested for every journal state. Invariant 8 is stated in the README and `NOTICE.txt`.

### 10.1 Six first-run scenarios at 480x820

1. **No save.** The band is hidden; UP NEXT says "Load a save to see what is next."; the folder
   panel opens once with the saves path and a Browse action.
2. **Clean save, no goal.** The band is hidden. UP NEXT carries the tracked quest and in-log
   quests only. MORE > CARDS > LATER lists the ahead windows.
3. **Cutoff passed.** NOW shows `CUTOFF PASSED - CHECK NOW` with the protected quest and the
   closing quest; the same warning is on the quest page and in search.
4. **Tick a not-started step.** The card keeps Not started, PROGRESS shows a pencil note rather
   than a green check, and the warning stays.
5. **Goal selected, guidance off.** PLAN AHEAD and the goal chips remain; no quoted line appears.
6. **Corrupt save.** The header names the file and says the tracker retries; the folder panel can
   be reopened; no stale band from the previous save is presented as current.

## 11. How an audit uses this page

- **Completeness:** every row of section 5 delivers its question, and every invariant in section 6
  holds. A row with no command, no visible element or no test behind it is an unfinished feature.
- **Bugs:** an invariant violated, or a row answering a question that is not its own.
- **Learnableness:** with the window pinned over the game, one save loaded and no goal chosen, a
  first-time player should be able to tell what is at risk, tell what to do next, find how to tick a
  step, find the goal picker, know what `MORE` holds, and recover from a missing save or a folder
  that was not found.
