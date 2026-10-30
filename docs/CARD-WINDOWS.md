# Card windows

**Status:** 4.4 reviewed layer, 2026-10-29. The generator is
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
| `one_time` | **15** | A gamefile one-time source with a route step, but no reviewed failure branch. It is a window, not a hard `LOST` claim. |
| `none` | **194** | A documented no-window reason: 187 persistent/automatic/merchant sources (Tier A) and 7 explicit unknown-source rows (Tier C). |
| **total** | **224** | No card is absent from the report. |

Tier totals: **202 Tier A** (15 one-time + 187 no-window), **15 Tier B** (all the missable rows),
**7 Tier C** (unknown source). The audited source count remains **216 sourced / 8 unknown source**:
Iorveth is one of the 8 unknown-source cards and has a Tier B window; the other 7 are Tier C and
have no asserted window.

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

- **Persistent sources.** A vendor row, random-merchant pool, starter deck or deck default remains a
  source independent of the journal. The files name no phase or journal deadline for those cards.
- **Automatic grants.** `UnlockSkelligeGwentDeck()` and `OnGwintSetupNewgame()` fill the collection
  when the deck is unlocked; no quest failure closes them.
- **One-time with a step.** A phase grant or quest reward with one route step is shown as
  `one_time`. It is a source window, but without a reviewed failure branch the app will not say the
  card was lost; a passed one-time row reads `ONE-TIME · PASSED · TIER A`.
- **Shared or unlinked phases.** A grant in a shared card-minigame phase or a container that maps to
  no single journal step has no deadline asserted. That is a documented no-window row, not a guess.
- **Unknown source.** The 8 cards with no concrete source row stay explicit `unknown source`. Seven
  have a Tier C no-window row; Iorveth has the reviewed Shock Therapy window above. Ownership is
  still tracked separately and is never inferred from a quest.

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

- `active` - the closing step is active and the card is not owned;
- `ahead` - the step is not started and the card is not owned;
- `check` - a Tier B step is done or failed; this is **not** a hard lost claim;
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

A `none` classification that rests only on a deck definition is unsafe. The first case found is
**Sigismund Dijkstra**: `cg100_no_mans_land.w2phase` contains an `AddItemQuestExt` grant for
`gwint_card_dijkstra`, so the Baron is a real source even though the card also appears in the
Northern Kingdoms deck list. The reviewed window for this card is still `none` in 1.3; the
generator and the reviewed input need the availability row before the app may claim a closing
window. Recording the finding is deliberate: the old row said the source stays available after
every route step, which the Baron's own phase does not prove.

The same audit is open for any card whose only "persistent" evidence is a deck definition or an
opponent deck. Until that row exists, the ledger shows the card and its `unknown source` or
`NO WINDOW` badge; the NOW band does not warn about it.

## Checks

```
py tools/cardwindows.py check
py tools/test_cardwindows.py
py tools/cards.py check
```

`cardwindows.py check` fails if any card is missing, a Tier B row lacks a source/URL/review date, a
window step is not a route node, the two generated files disagree, the denominator is not 224, the
pack/leader split is wrong, the missable count is a bare zero, the report does not declare itself the
static half, a no-window row has no `sources_checked`, or a no-window reason names only a category.
The test file mutates the real payload to prove those failures actually fire.
