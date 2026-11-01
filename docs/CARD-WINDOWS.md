# Card windows

**Status:** 1.3 reviewed layer, 2026-10-30. The generator is
[`tools/cardwindows.py`](../tools/cardwindows.py); the reviewed decisions are
[`data/card_window_review.json`](../data/card_window_review.json); the generated report is
[`data/card_windows.json`](../data/card_windows.json). No generated file is hand-edited.

`card_windows.json` is the **static classification** half of the matrix. It deliberately has no
`owned` field: per-save ownership is read from `CR4GwintManager.SBCollectionCard` /
`SBLeaderCollectionCard` and appears only in the runtime `--cards` / `get_cards` payload, where every
row carries `owned`. The report declares this in `classification` and `ownership.in_artifact`.

## What is classified

Every one of the **224** shipped cards (202 collectible main + 22 leaders) has exactly one row:

| classification | count | meaning |
|---|---:|---|
| `missable` | **15** | A reviewed closing step. All 15 are **Tier B / community**; every row names a source, URL and review date and is labelled in the UI. |
| `one_time` | **17** | A gamefile one-time source with a route step, but no reviewed failure branch. It is a window, not a hard `LOST` claim. |
| `none` | **192** | A documented no-window reason: 169 persistent/automatic/merchant sources (Tier A) and 23 explicit unknown-source rows (Tier C). |
| **total** | **224** | No card is absent from the report. |

Tier totals: **186 Tier A** (17 one-time + 169 no-window), **15 Tier B** (all the missable rows),
**23 Tier C** (unknown-source rows). The audited source count is **200 sourced / 24 explicit
unknown source**. The 16 extra unknown rows are the basic Northern Kingdoms cards whose only
evidence was the `north` deck list: a deck definition is not ownership, and
`OnGwintSetupNewgame()` grants only `yarpen` and `redanian2` by name. Iorveth is one of the 24
unknown-source cards and keeps its Tier B Shock Therapy window; the other 23 are Tier C and have
no asserted window. Ownership is still read from the save, so an owned starter card is never
shown as unknown ownership.

Coverage reconciles with the contract: **196 base**, **28 Blood and Wine**, **0 Hearts of Stone**,
**22 leaders**.

## The 15 reviewed closing windows

| card | step | closing event |
|---|---|---|
| Dandelion, Milva, Vampire: Bruxa | `sq301triss` A Matter of Life and Death | the Vegelbud party ends; win all three rounds |
| Fringilla Vigo, Isengrim, John Natalis | `sq310dangerousgame` A Dangerous Game | the final choice; keep the cards instead of the coin |
| Foltest: The Steel-Forged, Emhyr: The Relentless, Francesca: Queen of Dol Blathanna, Eredin: Destroyer of Worlds | `sq306maverick` High Stakes | win every tournament round; one loss closes the leader pool |
| Iorveth | `mq2039vowofsilence` Shock Therapy | finish the quest; skipping or failing it closes the card |
| Geralt of Rivia | `cgtalar` Gwent: Playing Thaler | play Thaler before Reason of State |
| Triss Merigold | `cgoldfriends` Gwent: Old Pals | play Lambert at the Kaer Morhen reunion before the battle |
| King Bran | `cg700mainquest` Turn, Turn, Tournament! | win the Beauclair tournament final |
| Gaunter O'Dimm | `q603bank` Open Sesame! | finish the heist and take the auction route |

Sources used for the Tier B rows: Gwent Checklist's missable-card guide and High Stakes page,
Fextralife's A Dangerous Game page, and Witcher Wiki's Shock Therapy page. The expanded URL and
review date are stored on each row and printed beside the window in the app.

One naming discrepancy is kept visible: the gamefile reward row for the High Stakes final names
`eredin_gold` (displayed as **Eredin / Destroyer of Worlds**), while the community page calls that
slot **Eredin: Bringer of Death**. The row uses the file-attributed definition; the window is Tier B
because the closing event is community-reviewed.

## Why the other cards are not missable

- **Persistent sources.** A vendor row, random-merchant pool, native collection grant or deck
  default remains a source independent of the journal. A deck list is not a persistent source; it
  says only where a card can appear, not that the player owns it.
- **Automatic grants.** `UnlockSkelligeGwentDeck()` and `OnGwintSetupNewgame()` fill the collection
  when the deck is unlocked; no quest failure closes them.
- **One-time with a step.** A phase grant or quest reward with one route step is shown as
  `one_time`. It is a source window, but without a reviewed failure branch the app will not say the
  card was lost; a passed one-time row reads `ONE-TIME · PASSED · TIER A`.
- **Shared or unlinked phases.** A grant in a shared card-minigame phase or a container that maps to
  no single journal step has no deadline asserted. That is a documented no-window row, not a guess.
- **Unknown source.** The 24 cards with no concrete source row stay explicit `unknown source`.
  Twenty-three have a Tier C no-window row; Iorveth has the reviewed Shock Therapy window above.
  Ownership is still tracked separately and is never inferred from a quest.

Every `none` row also carries `sources_checked`: the concrete source rows (kind, text, file,
function, container and step where present) the decision was based on. Its `reason` must name at
least one of those concrete rows and explain why no deadline can close the card; a category-only
reason such as “Persistent source row(s): vendor” is rejected by the checker.

## How it is surfaced

`data/gwent_cards.json` carries the same `window` object on each card, so the app has one payload.
The card row prints `window_live.label` and uses `window_live.tone` for its colour; the UI does not
re-derive a second label from `window.kind`. The row also prints the closing step, the mechanism,
and, for Tier B, the source name and review date. The source and review date stay visible on an
owned Tier B row even though the deadline sentence is suppressed. Every `missable` or `one_time`
row also has a collapsed **Technical details** block with its tier, step, event, mechanism, source
URL, review date and evidence entries. A `window_live` state reads the route status:

- `not_yet` - an `opens` fact gate is not met in this save; it is ledger-only;
- `active` - the opening step is active and the card is not owned;
- `ahead` - the opening step is not started and the card is not owned;
- `check` - a Tier B step is done or failed, or a one-time source with a fallback is past; this is
  **not** a hard lost claim;
- `passed` - a Tier A one-time source is done or failed;
- `owned` - the save (or a manual tick) owns the card, so the deadline sentence is silent; the
  classification badge and Tier B source/date remain visible;
- `unknown` - the save collection block is unavailable or ownership is unknown.

`AT RISK NOW` groups the open/check rows by step, so a party with three cards is one entry, not
three. The card row keeps the individual names. A missing collection block makes every card
`unknown`, never `not owned`.

## Source availability (1.3)

A card's **source**, its **availability** and its **missability** are three different claims. A
deck list in `def_gwint_decks.xml` is evidence that a card can appear in a deck; it is not evidence
that the player owns it, and it is not a collection grant. The reviewed layer separates:

- `collection_grant` - a native grant such as `OnGwintSetupNewgame` or `UnlockSkelligeGwentDeck`;
- `phase_grant` / `reward` / `loot` - a scripted grant with a route step;
- `vendor` - usable only while that vendor exists;
- `deck_definition` / `opponent_deck` - not ownership and not a reward.

A `none` classification that rests only on a deck definition is unsafe. The first case found was
**Sigismund Dijkstra**: `cg100_no_mans_land.w2phase` block 551 contains an `AddItemQuestExt` grant
for `gwint_card_dijkstra`, so the Baron is a real source even though the card also appears in the
Northern Kingdoms deck list. The row is now reviewed as **one_time**, with the bookkeeping in
`data/card_window_review.json`:

| save state | `window_live` |
|---|---|
| `cg_baron_discovered` not set | `not_yet` - the source is not open yet |
| `cgnomansland` not started, fact set | `ahead` - ledger only |
| `cgnomansland` active, fact set, not owned | `active` - the one-time window is open |
| `cgnomansland` done, not owned | `check` - the office fallback may still exist |
| owned | `owned` - the row is silent |

The row names `The Baron's office` as the fallback and never becomes a Tier B missable claim. It
is a one-time source, so it never becomes a live warning on TRACKED; MORE > CARDS shows the exact
source. The
newest and median saves own the card; the earliest save is `not_yet` because the Baron has not
been discovered. The active/check rows are Rust fixtures because no corpus save is after the
Baron line with the card still unowned.

The same rule now covers every card whose only "persistent" evidence was a deck definition or an
opponent deck: the generator emits the explicit unknown-source row instead of a false no-window
claim. The 16 basic Northern Kingdoms cards in that position are the audit's visible result.

## Checks

```
py tools/cardwindows.py check
py tools/test_cardwindows.py
py tools/cards.py check
```

`cardwindows.py check` fails if any card is missing, a Tier B row lacks a source/URL/review date, a
window step is not a route node, the two generated files disagree, the denominator is not 224, the
pack/leader split is wrong, the missable count is a bare zero, the report does not declare itself the
static half, a no-window row has no `sources_checked`, a no-window reason names only a category, a
`missable` or `one_time` row has no `opens` step, an `opens` fact is not in the game's fact index,
a `none` row hides a one-time source, or a no-window row rests only on a deck definition. The test
file mutates the real payload to prove those failures actually fire (13 tests).
