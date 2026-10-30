# Gwent opponents and what gates their option

9 hub dialogue blocks. `set` means the option needs the fact; `unset` means it
needs the fact absent. A fact tested both ways is marked ambiguous: the option exists in
more than one story state, so it is not a simple "wait for X" gate.

## crossroads innkeeper - not gated
`cg_card_minigame_meta.w2phase#371` on `crossroads_barkeep_default.w2scene` (plays `cg100_04_crossroads_innkeeper.w2scene`)
- objective: `cginnkeepers#Win unique card from crossroads innkeeper`
- cards naming this player: `card_horn`, `card_impera_brigade2`, `card_nausicaa2`, `card_combat_engineer`, `leader_emhyr_bronze`

## crossroads innkeeper - not gated
`cg_card_minigame_meta.w2phase#383` on `q101_01a_inkeep_int.w2scene` (plays `cg100_04_crossroads_innkeeper.w2scene`)
- objective: `cginnkeepers#Win unique card from crossroads innkeeper`
- cards naming this player: `card_horn`, `card_impera_brigade2`, `card_nausicaa2`, `card_combat_engineer`, `leader_emhyr_bronze`

## lambert - AMBIGUOUS
`cg_card_minigame_meta.w2phase#1370` on `lambert_default.w2scene` (plays `cg300_05_lambert.w2scene`)
- objective: `cgoldfriends#Win unique card from Lambert`; `cgoldfriends#When occasion presents itself win unique card from Lambert`
- fact `witcher3_game_finished` **set** - set by `ending_boards.w2phase#137` (q503newquest, q504ciriempress)
- fact `q403_lambert_dead` **set** - set by `q403_battle.w2phase#15701` (q110postbattle, q403battle), `q403_first_square.w2phase#2634` (q403battle)
- fact `q403_completed` **set** - set by `q403_battle.w2phase#11859` (q110postbattle, q403battle), `q403_burial.w2phase#14` (q110postbattle, q403battle)
- fact `q403_keira_saved_lambert` **set** (ambiguous) - set by `q403_battle.w2phase#14842` (q110postbattle, q403battle), `q403_first_square.w2phase#1972` (q403battle)
- fact `q401_completed` **set** - set by `q401_konsylium.w2phase#2751` (q401_hunt_with_eskel, q401_konsylium)
- fact `q401_lambert_defeated_in_gwint` **set** - set by `q401_konsylium.w2phase#3936` (q401_hunt_with_eskel, q401_konsylium)
- fact `q403_keira_saved_lambert` **unset** (ambiguous) - set by `q403_battle.w2phase#14842` (q110postbattle, q403battle), `q403_first_square.w2phase#1972` (q403battle)
- cards naming this player: `card_triss`

## olivier - AMBIGUOUS
`cg_card_minigame_meta.w2phase#526` on `shop_novigrad_kingfisher_inn_olivier.w2scene` (plays `cg300_04_olivier.w2scene`)
- objective: `cginnkeepers#Win unique card fro Olivier`
- fact `q309_saw_olivier_dead` **unset** (ambiguous) - set by `q309_casablanca.w2phase#10865` (q309mages)
- fact `q309_saw_olivier_dead` **set** (ambiguous) - set by `q309_casablanca.w2phase#10865` (q309mages)
- cards naming this player: `card_tibor`, `card_havcaaren_support3`, `card_vrihedd_brigade2`, `card_mahakam5`, `card_havcaaren_medic3`

## roche - simple gate
`cg_card_minigame_meta.w2phase#856` on `roche_default.w2scene` (plays `cg300_08_roche.w2scene`)
- objective: `cgoldfriends#Win unique card from Roche`
- fact `mq3035_fdb_roche_talar_dead` **set** - set by `mq3035_wrap_up.w2phase#326` (mq3035_emhyr)

## stjepan - simple gate
`cg_card_minigame_meta.w2phase#175` on `shop_novigrad_whitebridge_inn_stjepan.w2scene` (plays `cg300_03_stjepan.w2scene`)
- objective: `cginnkeepers#Win unique card from Stjepan the innkeeper`
- fact `cg_stjepan_discovered` **set** (or-gate) - set by tested here but no phase sets it (scene or script)
- fact `q001_talked_about_stjepan` **set** (or-gate) - set by tested here but no phase sets it (scene or script)
- cards naming this player: `card_horn`, `card_vrihedd_brigade`, `card_dwarf`, `card_mahakam2`

## thaler - simple gate
`cg_card_minigame_meta.w2phase#1070` on `talar_default.w2scene` (plays `cg100_06_talar.w2scene`)
- fact `mq3035_fdb_roche_talar_dead` **set** - set by `mq3035_wrap_up.w2phase#326` (mq3035_emhyr)

## thaler - simple gate
`cg_card_minigame_meta.w2phase#1569` on `talar_default.w2scene` (plays `cg100_06_talar.w2scene`)
- fact `sq315_fdb_quest_complete` **set** - set by `sq315_investigation.w2phase#1762` (sq315talar)
- fact `mq3035_fdb_roche_talar_dead` **set** - set by `mq3035_wrap_up.w2phase#326` (mq3035_emhyr)
- fact `cg300_talar_omitted` **set** - set by `cg_card_minigame_meta.w2phase#1001` (cginnkeepers, cgmetagatherall)

## zoltan - not gated
`cg_card_minigame_meta.w2phase#765` on `zoltan_chivay_default.w2scene` (plays `cg300_02_zoltan.w2scene`)
