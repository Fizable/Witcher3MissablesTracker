# Dialogue options gated by another quest

369 dialogue-bearing phase files, 1310 option blocks:
**4 turn-in blocks** react to their own quest's journal *and* a fact or
journal another quest controls; **167 other blocks** are gated by a foreign
fact without being a turn-in (Gwent tables, fistfights, hero-card cameos).

A turn-in row is a candidate window, not a verdict: whether it is a deadline depends
on what the fact means and whether anything fails the quest.

## Turn-ins whose option depends on another quest

### cgnovigrad
- `cg300_novigrad.w2phase#361` CQuestContextDialogBlock on `shop_scoiatael_camp_novigrad.w2scene` - **not modelled**
  - own journal: `cgnovigrad` JS_Active
  - fact `mq3035_fdb_dijkstra_dead` value 1 - set by `mq3035_wrap_up.w2phase#55` (mq3035_emhyr)
  - fact `mq3035_fdb_roche_talar_dead` value 1 - set by `mq3035_wrap_up.w2phase#326` (mq3035_emhyr)
  - fact `q310_dijkstras_other_leg` value 1 - set by `q310_pregeels_new.w2phase#4026` (q310bombing, q310pregeels, q310preparationsnovigrad)
  - fact `witcher3_game_finished` value 1 - set by `ending_boards.w2phase#137` (q503newquest, q504ciriempress, q505cirifree)

### mq3012noblestatuette
- `mq3012_jade_statuettes.w2phase#161` CQuestContextDialogBlock on `triss_default.w2scene` - modelled by the tracker
  - own journal: `mq3012warriorstatuette` JS_Success, `mq3012noblestatuette` JS_Success
  - fact `q301_met_kob` unset - set by `q301_dreamer.w2phase#5190` (q301dreamer, q301helpdreamer)
  - fact `q309_completed` set - set by `q309_casablanca.w2phase#2493`, `q309_casablanca.w2phase#2549` (q309mages)
  - fact `q109_keira_to_km` value 1 - set by `q109_wrapup.w2phase#155` (q109wrapup)
  - fact `q310_philippa_rescued` set - set by `q310_pregeels_new.w2phase#3939` (q310bombing, q310pregeels, q310preparationsnovigrad)
  - fact `q309_completed` unset - set by `q309_casablanca.w2phase#2493`, `q309_casablanca.w2phase#2549` (q309mages)
  - fact `q301_met_kob` set - set by `q301_dreamer.w2phase#5190` (q301dreamer, q301helpdreamer)

### mq3012warriorstatuette
- `mq3012_jade_statuettes.w2phase#161` CQuestContextDialogBlock on `triss_default.w2scene` - modelled by the tracker
  - own journal: `mq3012warriorstatuette` JS_Success, `mq3012noblestatuette` JS_Success
  - fact `q301_met_kob` unset - set by `q301_dreamer.w2phase#5190` (q301dreamer, q301helpdreamer)
  - fact `q309_completed` set - set by `q309_casablanca.w2phase#2493`, `q309_casablanca.w2phase#2549` (q309mages)
  - fact `q109_keira_to_km` value 1 - set by `q109_wrapup.w2phase#155` (q109wrapup)
  - fact `q310_philippa_rescued` set - set by `q310_pregeels_new.w2phase#3939` (q310bombing, q310pregeels, q310preparationsnovigrad)
  - fact `q309_completed` unset - set by `q309_casablanca.w2phase#2493`, `q309_casablanca.w2phase#2549` (q309mages)
  - fact `q301_met_kob` set - set by `q301_dreamer.w2phase#5190` (q301dreamer, q301helpdreamer)

### q205herbarium
- `sq201_curse.w2phase#5368` CQuestInteractionDialogBlock on `sq201_00_priestess_interctive_dlg.w2scene` - **not modelled**
  - own journal: `sq201curse` JS_Active
  - fact `q203_cataclysm_complete` value 1 - set by `q203_cataclysm.w2phase#1019` (q203cataclysm)

### q210preparations
- `mq3012_jade_statuettes.w2phase#161` CQuestContextDialogBlock on `triss_default.w2scene` - modelled by the tracker
  - own journal: `mq3012warriorstatuette` JS_Success, `mq3012noblestatuette` JS_Success
  - fact `q301_met_kob` unset - set by `q301_dreamer.w2phase#5190` (q301dreamer, q301helpdreamer)
  - fact `q309_completed` set - set by `q309_casablanca.w2phase#2493`, `q309_casablanca.w2phase#2549` (q309mages)
  - fact `q109_keira_to_km` value 1 - set by `q109_wrapup.w2phase#155` (q109wrapup)
  - fact `q310_philippa_rescued` set - set by `q310_pregeels_new.w2phase#3939` (q310bombing, q310pregeels, q310preparationsnovigrad)
  - fact `q309_completed` unset - set by `q309_casablanca.w2phase#2493`, `q309_casablanca.w2phase#2549` (q309mages)
  - fact `q301_met_kob` set - set by `q301_dreamer.w2phase#5190` (q301dreamer, q301helpdreamer)

### q402ciri
- `q402_ciri.w2phase#2327` CQuestContextDialogBlock on `roche_default.w2scene` - modelled by the tracker
  - own journal: `q402novigradallies` JS_Active
  - fact `sq312_ves_died` value 1 - set by `sq312_kill.w2phase#247`, `sq312_kill.w2phase#658` (sq312vincentves)
  - fact `sq312_fdb_ves_end` value 1 - set by `sq312_quest.w2phase#111` (sq312vincentves)

### q402nilfgaardianally
- `q402_ciri.w2phase#2327` CQuestContextDialogBlock on `roche_default.w2scene` - modelled by the tracker
  - own journal: `q402novigradallies` JS_Active
  - fact `sq312_ves_died` value 1 - set by `sq312_kill.w2phase#247`, `sq312_kill.w2phase#658` (sq312vincentves)
  - fact `sq312_fdb_ves_end` value 1 - set by `sq312_quest.w2phase#111` (sq312vincentves)

### q402novigradallies
- `q402_ciri.w2phase#2327` CQuestContextDialogBlock on `roche_default.w2scene` - modelled by the tracker
  - own journal: `q402novigradallies` JS_Active
  - fact `sq312_ves_died` value 1 - set by `sq312_kill.w2phase#247`, `sq312_kill.w2phase#658` (sq312vincentves)
  - fact `sq312_fdb_ves_end` value 1 - set by `sq312_quest.w2phase#111` (sq312vincentves)

### q402skelligeallies
- `q402_ciri.w2phase#2327` CQuestContextDialogBlock on `roche_default.w2scene` - modelled by the tracker
  - own journal: `q402novigradallies` JS_Active
  - fact `sq312_ves_died` value 1 - set by `sq312_kill.w2phase#247`, `sq312_kill.w2phase#658` (sq312vincentves)
  - fact `sq312_fdb_ves_end` value 1 - set by `sq312_quest.w2phase#111` (sq312vincentves)

### q402velenallies
- `q402_ciri.w2phase#2327` CQuestContextDialogBlock on `roche_default.w2scene` - modelled by the tracker
  - own journal: `q402novigradallies` JS_Active
  - fact `sq312_ves_died` value 1 - set by `sq312_kill.w2phase#247`, `sq312_kill.w2phase#658` (sq312vincentves)
  - fact `sq312_fdb_ves_end` value 1 - set by `sq312_quest.w2phase#111` (sq312vincentves)

### sq201curse
- `sq201_curse.w2phase#5368` CQuestInteractionDialogBlock on `sq201_00_priestess_interctive_dlg.w2scene` - **not modelled**
  - own journal: `sq201curse` JS_Active
  - fact `q203_cataclysm_complete` value 1 - set by `q203_cataclysm.w2phase#1019` (q203cataclysm)

## Other foreign-fact options (checked, not turn-ins)

167 blocks in 51 quests, by file prefix: `q403` 57, `quest` 47, `q206` 7, `q402` 6, `cg` 5, `hr101` 4, `sq302` 4, `q202` 3, `ff104` 2, `cg200` 2.

Most common gate facts: `q402_invited_hjalmar_to_km` (46), `q402_invited_roche_to_km` (43), `q109_keira_to_km` (42), `q402_invited_zoltan_to_km` (37), `q402_invited_mousesack_to_km` (36), `q202_vigi_saved` (12), `q202_folan_lives` (11), `q402_know_about_battle` (8).

These are scenes offered when someone is in town, not quests being turned in. They
would be worth a card only if the tracker ever told a player to talk to that NPC.
