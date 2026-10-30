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

## 9. How an audit uses this page

- **Completeness:** every row of section 5 delivers its question, and every invariant in section 6
  holds. A row with no command, no visible element or no test behind it is an unfinished feature.
- **Bugs:** an invariant violated, or a row answering a question that is not its own.
- **Learnableness:** with the window pinned over the game, one save loaded and no goal chosen, a
  first-time player should be able to tell what is at risk, tell what to do next, find how to tick a
  step, find the goal picker, know what `MORE` holds, and recover from a missing save or a folder
  that was not found.
