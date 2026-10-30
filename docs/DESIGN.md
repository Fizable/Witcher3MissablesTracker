# Design: what this tracker is for

Written 2026-10-30, from the author's own statement of the goal, after a docs sweep retired seven
plans and probes. This is the document to check a proposal against. If a change does not serve the
next paragraph, it is not this app's job.

## The goal

**Warn the player, at the top of the window, what is at risk right now, so the run keeps the endings
they chose.**

The warning is the product. Everything else in the app exists so that warning can be trusted and so
the leftovers stay findable.

## What the top band must warn about

1. **A cutoff.** An action that is about to cost something that can still be saved, or one whose
   moment has arrived and has not been taken.
2. **Order.** Do this quest before that one. A player who has chosen a quest should be told when
   finishing it will fail other quests that are still open in their log.
3. **Gwent cards.** A card window closing now, and one that has already closed.
4. **A consequential choice.** That this quest contains a choice that matters to the chosen endings.

These four hold whether or not an ending has been chosen. A chosen ending changes which choices are
named and what the line is; it never becomes a precondition for being warned.

When nothing can still change, the band is silent. Silence is the correct output, not a bug.

## Guidance is opt-in, and it is a second layer

By default the app says only that a choice changes the outcome. It never says which choice, or what
follows. With guidance toggled on, it tells the player what to say in that scene, using the exact
line from the game's own scene data. That gate is why choice text can ship at all: the line is
reviewed game text, and the default payload has none of it.

## One hundred percent is supported, not the headline

The route, the card ledger, coverage and progress are there to make each warning provable and to let
the player find what is left. The tools should be able to carry one run to the maximum obtainable set
for the endings that run chose. They must not turn the app into a walkthrough checklist and must not
print a single completion percentage: one save cannot realize every branch, so the number would lie.

## What it refuses to be

- Not a walkthrough and not a wiki; the game's own files decide every rule and the loaded save
  decides every fact about where the player is.
- No second-hand knowledge, no guessed dialogue, no text from a walkthrough.
- No spoilers by default.
- Read-only against saves, offline, no network client.
- Not a claim that one save can realize every branch, every ending and every card.

## The check, before any change

Ask one question: does this make the top band more accurate about what is at risk now? A change that
only adds reference data is allowed, but it must not push reference data into the band. A change that
adds scope without improving a warning is the thing this document exists to say no to.

## Where the contract actually lives

`README.md` states what NOW and UP NEXT do today, `docs/BACKEND_CONTRACT.md` is the interface the
window is handed, `docs/TARGET-SCHEMA.md` fixes the goal and outcome shapes, `docs/CARD-WINDOWS.md`
records the reviewed card windows, and `tools/README.md` documents how every number is generated and
re-checked. The 47 `cargo test` cases and the `tools/` checkers are the executable half of this page.
