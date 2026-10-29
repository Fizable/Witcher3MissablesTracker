# Gwent card probe

**Status:** complete (2026-10-28), read-only. **Scope:** step 6 of
[PLAN-1.0-completion.md](PLAN-1.0-completion.md) only. This probe did not generate a card index,
a card list or card UI, and did not change existing tools, `data/*.json`, `src/` or `ui/`.
`regen.py` and `package.ps1` were not run.

**Short answer.** The card definitions exist and all 228 names resolve, but the source data is not
complete: only 127 of 206 main cards have a concrete or native grant row. The automated probe and
the review in §3.1 resolve the original 21 cards with no source or opponent evidence: 13 are
granted by the native Skellige base-deck function, four are in the random merchant card pool, and
four are summon-only or explicitly unobtainable definitions. No collectible main card remains
unknown; four definitions are summon tokens. Of the five source-less leaders, four are obtainable
deck defaults and one
(`eredin_copper`) remains unknown. The save does **not** expose card item GUIDs, but it does expose
the `CR4GwintManager` collection by card index, so ownership can be automatic without manual ticks
(manual ticks remain the fallback if that block is missing). Card-level missable windows are **not
proven** by the journal/phase data; quest-level windows are plausible for some grants, but none was
linked to a deadline by this probe.

## 1. Where card definitions live

The card database is XML inside the retail bundles, not a per-card CR2W entity.

| Resource | Shipping location | XML root / class | Measured content |
|---|---|---|---|
| Main cards | `content/content0/bundles/xml.bundle` → `gameplay/items/def_gwint_cards_final.xml` | `gwint_card_definitions_final` | 206 card definitions, 92,721 bytes |
| Card items | same bundle → `gameplay/items/def_item_gwint.xml` | `items` | 197 item definitions, 115,862 bytes |
| Leaders | same bundle → `gameplay/items/def_gwint_battle_king_cards.xml` | `gwint_battle_king_card_definitions` | 22 leader definitions, 9,110 bytes |
| King cards | same bundle → `gameplay/items/def_gwint_king_cards.xml` | `gwint_king_card_definitions` | 5,072 bytes; 0 active cards (all card blocks are commented out) |
| Deck collections | same bundle → `gameplay/items/def_gwint_decks.xml` | `gwint_decks` | 56 collections, 168 decks, 4,406 card lines, 172,844 bytes |
| Card origin table | `content/content0/bundles/startup.bundle` → `gameplay/globals/card_sources.csv` | CSV | 197 rows, 171 unique names, 151 cards mapped |

All five card/item XML files also exist under `gameplay/items_plus/…` in the same bundle, and under
the REDkit `r4data/gameplay/items/` tree. The copies are **byte-identical** for every one of the
five resources; the REDkit copies are therefore useful for inspection but are not a separate data
source.

DLC bundles add source definitions, not a second card database:

- `dlc/bob/data/gameplay/items/def_loot_shops.xml`, `def_loot_quest.xml`
- `dlc/bob/data/gameplay/rewards/rewards.xml`
- `dlc/ep1/data/gameplay/items/def_loot_shops.xml`, `def_loot_quests.xml`
- `dlc/ep1/data/gameplay/rewards/rewards.xml`

The Blood and Wine Skellige deck (indices 500–527) is in the base
`def_gwint_cards_final.xml`; the DLC bundles supply its shops, quest loot and rewards.

Two other facts matter for implementation:

- There is **no per-card `.w2ent`**. The only card entities found in `r4items.bundle` are the generic
  props `items/work/cards/card_deck.w2ent` and `card_single.w2ent`. `CR4GwintManager` is native; the
  script files contain only its stubs.
- `def_loot_test.xml` contains 153 test rows covering 132 cards. It is test loot and was excluded
  from all source counts below.
- The string database used for names is REDkit's
  `LocalEditorStringDataBaseW3_UTF8.db` (`W3_STRINGDB` in [paths.py](../tools/paths.py)).

## 2. How many cards, and do their names resolve?

| Measure | Count |
|---|---:|
| Main card definitions | 206 |
| Leader definitions | 22 |
| Active king-card definitions | 0 |
| Main + leader definitions | 228 |
| Unique main display names | 163 |
| Unique leader display names | 22 |
| Main definitions with a direct item definition | 178 |
| Main definitions without a direct item | 28 |

Faction split of the 206 main definitions: 26 neutral, 41 Monsters (`F_NO_MANS_LAND`), 38
Scoia'tael, 37 Nilfgaard, 35 Northern Kingdoms, 29 Skellige.

**Names: 228 of 228 resolve to a non-empty display name; none is missing.**

- 225 use a `gwint_name_*` string key.
- 3 do not: `mysterious_elf` (displays as *Mysterious Elf*), `roach` (uses
  `map_location_horse`, displays as *Roach*) and `Crach_an_Craite` (literal, displays as
  *Crach an Craite*). The fallback is explicit in the probe, not an unresolved name.

The 206/228 count is **definition count, not checklist count**. Several definitions are variants
with the same display name: `gwint_name_mahakam` is used by 5 definitions, `impera_brigade` by 4,
and `dol_scout`, `dwarf`, `kaedweni_siege`, `crinfrid`, `ghoul` and
`clan_drummond_shieldmaiden` by 3 each. A later card index must decide whether its completion
denominator is definitions, item definitions or unique display names; that is a reviewed product
decision, not something this probe can settle.

The 28 main definitions without a direct item are:

- 22 Northern Kingdoms base-deck cards (`ves`, `siegfried`, `yarpen`, `keira`, `sile`, `sabrina`,
  `sheldon`, `dethmold`, `stennis`, the Trebuchets, Poor Infantry variants, Redanian variants,
  Ballistas, Kaedweni Siege variants and Dun Banner Medic);
- 3 neutral cards: `cow_czart`, `geraltGOG`, `ciriGOG`;
- 3 Skellige cards: `hemdal`, `berserker_bear`, `young_berserker_bear`.

`hemdal`'s item definition is explicitly commented `UNOBTAINABLE IN GAME` in
`def_item_gwint.xml`; there is no active item for it. The two GOG variants reuse the normal Geralt
and Ciri item display names, and `cow_czart` has no item at all (the separate `gwint_card_cow` item
belongs to the `cow` card). `poor_infantry2` and `poor_infantry3` are active standard item
definitions with no card pointing at them. Those are data-shape issues to resolve during review,
not name failures.

## 3. Can every card be mapped to a quest, vendor or opponent source?

**No.** The files do not contain a complete source table.

Counts below include only active XML rows and phase-script grant calls. Comments are stripped, and
the test loot file is excluded. Rows can cover multiple cards and a card can have multiple rows.

| Source channel | Rows | Containers | Unique item IDs | Main cards covered |
|---|---:|---:|---:|---:|
| Vendor shop loot | 156 | 22 | 75 | 65 |
| Quest loot | 8 | 8 | 8 | 8 |
| Unique loot | 2 | 2 | 2 | 2 |
| Quest/contract rewards | 11 | 9 | 11 | 6 |
| Phase-script grants | 50 | 13 phase resources | 47 | 42 |
| **Concrete union** | — | — | — | **112 / 206** |

The phase grants include 17 merchant rows for 15 cards
(`GiveSpecificGwentCardViaMerchantQuest`); the rest are direct `AddItemQuest*` calls. They name
exact card items, for example `cg100_no_mans_land.w2phase` grants `gwint_card_dijkstra`,
`gwint_card_letho` and others; `sq310_dangerous_game.w2phase` grants `gwint_card_natalis` and
`gwint_card_isengrim`; `q603_bank.w2phase` grants `gwint_card_mrmirror`; and
`cg700_gwent_players.w2phase` grants the Blood and Wine Skellige cards through the merchant path.

### Coverage is not the same as acquisition

The deck file has 56 collections: 25 named player/opponent collections, 25 generic collections,
5 player decks and 1 tutorial collection. The named collections contain 161 distinct cards; the
Northern Kingdoms starter deck contains 27. Those are evidence about **where a card is played**,
not proof that the player wins it there.

Counting those as weak evidence gives:

- **185 / 206** main cards have some source, opponent or starter evidence;
- **112 / 206** have a concrete vendor/quest/loot/reward/phase grant row;
- **21 / 206** have none of the above.

Those are the XML/phase-only counts from the original pass. Adding native script grants raises the
concrete union to **127 / 206**; adding the random pool and removing four summon tokens leaves
**202 / 202** collectible cards with any evidence and **0** unmatched.

The original raw scan's 21 with no evidence at all were:

- **16 Blood and Wine Skellige cards:** `hemdal`, `hjalmar`, `holger_blackhand`, `madman_lugos`,
  `donar_an_hindar`, `udalryk`, `birna_bran`, `blueboy_lugos`, `svanrige`, `berserker`,
  `berserker_bear`, `young_berserker_bear`, `clan_an_craite_warrior`,
  `clan_tordarroch_armorsmith`, `clan_heymaey_skald`, `clan_drummond_shieldmaiden`.
- **4 Monsters/Nilfgaard cards with items but no source row:** `vreemde`, `imlerith`, `forktail`,
  `celaeno_harpy`.
- **1 neutral:** `cow_czart` (and it has no item).

### 3.1 Reviewed decisions for the 21

The probe now performs this review automatically: it scans the shipping scripts under
`content/content0/scripts` for literal `AddCardToCollection` calls and the random merchant pool,
and derives summon tokens from each card's `summonFlags`. Its current result is **127 / 206**
cards with a concrete or native grant row, **202 / 202** collectible cards with any
source/opponent/starter evidence, and **0** unmatched collectible cards; four definitions are
summon tokens. The manual table below records the evidence pass, including the `hemdal` finding.

Decision key:

- **B — Skellige base deck:** `UnlockSkelligeGwentDeck()` in
  `content/content0/scripts/game/quests/quest_function.ws` (lines 6636–6669) calls
  `AddCardToCollection` for the card. The script is invoked from
  `dlc/bob/data/quests/minor_quests/quest_files/cg700_card_game/cg700_card_game_tournament.w2quest`
  and is one-time via `skel_gwint_base_deck_given`. This is a direct collection grant, not an XML
  loot row.
- **R — random merchant card:** `GiveMerchantRandomGwintCardToPlayerQuest()` in the same script
  file (lines 7641–7722) has the exact item in its random pool; the original phase scan counted
  82 script-block call sites in shop, community and quest phases. `card_sources.csv` also records
  the card's origin as `Random`; the exact merchant is not identified by the card files.
- **T — summon-only token:** the card definition has `item=""`, and its parent card summons it
  through `EFFECT_MORPH` or `EFFECT_SUICIDE_SUMMON` plus a `summonFlags` entry. It is not a
  collectible card.
- **U — unobtainable:** there is no active item and no collection grant; the item definition is
  explicitly commented `UNOBTAINABLE IN GAME`.

| Card | Decision | Evidence |
|---|---|---|
| `hjalmar` | obtainable | **B** |
| `holger_blackhand` | obtainable | **B** |
| `madman_lugos` | obtainable | **B** |
| `donar_an_hindar` | obtainable | **B** |
| `udalryk` | obtainable | **B** |
| `birna_bran` | obtainable | **B** |
| `blueboy_lugos` | obtainable | **B** |
| `svanrige` | obtainable | **B** |
| `berserker` | obtainable | **B** |
| `clan_an_craite_warrior` | obtainable | **B** |
| `clan_tordarroch_armorsmith` | obtainable | **B** |
| `clan_heymaey_skald` | obtainable | **B** |
| `clan_drummond_shieldmaiden` | obtainable | **B** |
| `vreemde` | obtainable | **R** |
| `imlerith` | obtainable | **R** |
| `forktail` | obtainable | **R** |
| `celaeno_harpy` | obtainable | **R** |
| `cow_czart` | not obtainable | **T** — token of `cow` |
| `berserker_bear` | not obtainable | **T** — token of `berserker` |
| `young_berserker_bear` | not obtainable | **T** — token of `young_berserker` |
| `hemdal` | not obtainable | **T** — token of `cock` (Kambi); its item is also marked `UNOBTAINABLE IN GAME`. |

Net result for the 21: **17 obtainable, 4 not obtainable, 0 unknown**. The 13 **B** cards are
collectible through the B&W Skellige base-deck unlock; the four **R** cards are obtainable from a
random merchant reward; the four **T** cards should not be counted as completion targets.

`hemdal` is the only one of the 16 Skellige cards whose item is explicitly marked unobtainable;
the `cock` card also summons it, so it is not a collectible target. The two bear cards are
transformation tokens, not alternate collectible cards, despite being separate definitions.

### Leaders

All 22 leaders resolve their names. 17 have an active item and 17 have a source row. The five with
no active item or source are reviewed separately:

| Leader | Decision | Evidence |
|---|---|---|
| `foltest_copper` | obtainable | Default Northern Kingdoms deck leader in `def_gwint_decks.xml`; present in the sampled save's leader collection. |
| `emhyr_copper` | obtainable | Default Nilfgaard deck leader; present in the sampled save. |
| `francesca_copper` | obtainable | Default Scoia'tael deck leader; present in the sampled save. |
| `Crach_an_Craite` | obtainable | Fixed Skellige deck leader assigned by `OnGwintSetupSkellige()` in `gwintManager.ws`; the deck is unlocked by the Skellige base-deck path. It is **not** a `SBLeaderCollectionCard` row, so collection-only ownership will not see it. |
| `eredin_copper` | unknown | `item=""`; its item block is commented `IN BASE DECK`; no script grant or source row; absent from the sampled save. The default Monsters deck uses `eredin_bronze`. |

Four leaders are therefore obtainable and one is unknown. The three copper leaders present in the
save prove those three are obtainable in this playthrough; they are also the default leaders for
their factions. That does not prove `eredin_copper` is granted. `Crach` is a deck default rather
than an inventory item; a card index needs an explicit special case for it.

### The origin CSV is not a source mapping

`card_sources.csv` has 197 rows / 171 unique names and maps to 151 cards, but its origins are
act/map/random labels, not vendors or opponents: `NML` 64, `Novigrad` 42, `Skellige` 28,
`Prologue` 10, `Random` 51, `KaerMorhen` 1, `Vizima` 1. `Random` is not a specific source and the
file has no quest/opponent identity. It supports the **R** decision for the four random-pool cards
as corroboration, but it cannot supply the plan's full `source` row on its own.

## 4. Does the save expose card item GUIDs?

**No.** This save does not contain a per-card item GUID ledger. It does contain the Gwent
collection itself.

The probe read one save, read-only: `AutoSave_10083f_7ea4ec00_3755550.sav`
(2,529,650 bytes, mtime 2026-10-28 13:53). The newest save was chosen by mtime.

`CR4GwintManager` is present in the save's name table and serialises:

- `SBCollectionCardSize` / `SBCollectionCard`, each row with `cardIndex` and `numCopies`;
- `SBLeaderCollectionCardSize` / `SBLeaderCollectionCard`, same shape.

Measured contents:

| Measure | Value |
|---|---:|
| Normal cards owned | 114 |
| Leader cards owned | 15 |
| Total collection rows | 129 |
| Total copies | 147 (131 normal + 16 leader) |
| Maximum copies of one card | 3 |
| Collection rows mapping to a definition | 129 / 129 |
| Unknown indices | none |

All 114 normal indices and all 15 leader indices map into the parsed definition tables. There were
17 `gwint_card_*` strings outside the save's name table, all in fact-like contexts
(`merchant_card_*_already_given` / `cg_lock_*` style), not an inventory ledger. `CInventoryComponent`
is present; this probe found no card item GUID mapping in it.

**Consequence:** automatic ownership is feasible from card indices without manual ticks. The plan's
"if the save exposes card item GUIDs" branch is false, but its fallback is not needed: parse the
collection arrays instead. Manual ticks remain necessary only when the collection block is absent,
malformed, or unreadable. This parser has been exercised on **one** save; it should be checked
against a second save (and an older/NG+ save if available) before being treated as universal. It
never infers ownership from quest state.

## 5. Can missable-card windows be derived from journal/phase data?

**Not at card level with the evidence available.** Quest-level windows exist; per-card deadlines
are unproven.

Measured facts:

- `data/route.json` has **11 `gwent` route nodes**.
- Those nodes carry **14 "Win unique card from …" objectives over 13 opponents** (Lambert has two
  objective variants). The objectives name the opponent, not the card.
- One Gwent node has a hard gate: `sq306maverick` (High Stakes) requires `q301dreamer` /
  `q301_burn_doppler`.
- `data/cutoffs.json` has **0 Gwent cutoff rows**. The tracker's current cutoff model therefore
  contributes no card windows.
- Phase scripts contain **50 grant rows / 47 item IDs / 42 main cards** across 13 phase resources.
  They name exact card items, which is the strongest card-level evidence found.
- This probe did not pair any phase grant with a journal objective or a failure socket. The
  journal reader exposes `guid`, `status` and `resource` per entry; it does not expose a card
  identity.
- The route objectives expose step IDs and files, but not card IDs. The journal status tells whether
  a quest/objective is done or failed, not which card is at risk.

So the derivation chain stops before a card-level window:

1. A phase script can say "this step grants card X".
2. A journal entry can say "this step is active/done/failed".
3. Nothing in the probed data says "card X becomes unavailable when this journal entry fails",
   nor maps the 14 opponent objectives to specific cards.

Vendor and random cards have no journal window at all; their availability is a shop/act condition,
not a quest deadline. `card_sources.csv` does not supply a window either.

The honest result is therefore:

- **Quest-level windows:** some may be derivable after a phase-graph-to-journal review, but none was
  proven here.
- **Card-level windows:** not derivable from existing journal/phase data. Do not emit
  `missable: {step, event, mechanism}` rows until a reviewer supplies the mapping and evidence.
- In particular, do not turn "this Gwent quest can fail" into "every card in it is missable".

## 6. What this means for step 6

The definition probe **passes**: the resources exist in shipping bundles, the REDkit copies match,
all names resolve, and a save collection can be read. A generated card index is technically
feasible.

It is **not ready to ship as a complete card list**:

- The scan leaves 79 of 206 main cards without a concrete XML/native grant row and **0**
  collectible cards without any evidence. The automated native/pool/token pass resolves the
  original 21; it does not create XML source rows. A generated index can use the reviewed
  decisions, but must not present a native-script or random-pool path as a vendor/quest grant.
- Of the 16 Blood and Wine Skellige cards, 13 are obtainable through the base-deck script,
  `hemdal` is a summon target of `cock` (Kambi) whose item is marked unobtainable, and the two bear
  cards are summon tokens. The B&W review is therefore complete for this group.
- The five source-less leaders are four obtainable deck defaults and one unknown
  (`eredin_copper`). `Crach` is not a collection row; ownership logic must handle the deck leader
  separately rather than reporting it as missing.
- 206 definitions and 163 unique display names are different denominators. The card index must
  choose one and record why; otherwise the completion count will be misleading.
- Ownership should use `SBCollectionCard` / `SBLeaderCollectionCard` indices. Manual ticks are a
  fallback, not the primary path.
- No `missable` row can be generated from this probe. Any such row needs reviewed evidence.

At probe time no card index, card list, card UI or new `data/*.json` was produced; this was the
stop point. The implementation now builds `data/gwent_cards.json` in [tools/cards.py](../tools/cards.py)
(224 cards: 202 collectible main + 22 leaders; 216 sourced, 8 unknown). The 4.4 reviewed layer is
[`CARD-WINDOWS.md`](CARD-WINDOWS.md): 15 Tier B community-reviewed closing windows, 15 Tier A
one-time sources, 194 documented no-window rows (187 Tier A, 7 Tier C unknown source). No window is
inferred from a failed quest; Tier B rows name a source, URL and review date.

## 7. Method and checks

The probe is [tools/probe_cards.py](../tools/probe_cards.py). It reuses the read-only bundle reader
from `probe_dlc.py`, the CR2W parser, the string database helper and the save decompressor; the
Gwent collection parser is new and specific to `CR4GwintManager`.

What was run:

```
py tools/probe_cards.py
py tools/probe_cards.py --json | py -c "import json,sys; d=json.load(sys.stdin); print(list(d))"
py -m py_compile tools/probe_cards.py
```

The human report and the JSON both complete; JSON mode parses as valid JSON. No files are written by
the probe. Bundle payloads are decompressed in memory; CR2W payloads go through a temporary
directory that is removed on exit. The game, REDkit, string database and saves are opened read-only.

The probe reads the shipping script tree `content/content0/scripts` and parses literal
`AddCardToCollection` calls, the random merchant-card pool, and each card's `summonFlags`. It does
not execute scripts. The source counts above therefore include native grants and random pools;
the decisions in §3.1 remain the evidence notes for the original XML/CR2W-only scan.

Limits:

- 33 bundles were read; `blob0.bundle` and `buffers0.bundle` were skipped because their headers
  disagree with their file lengths. The card/source resources listed above resolved from other
  bundles, but the skipped bundles are not accounted for; this is a coverage limit.
- One save only; the collection parser has not been tested against every save variant or a modded
  save.
- Source counts are file evidence, not a walkthrough. In particular, "opponent deck membership"
  is not proof of a reward, and vendor rows do not prove the vendor is reachable in a given
  playthrough.
