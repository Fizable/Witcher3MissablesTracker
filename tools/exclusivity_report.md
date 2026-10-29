# Exclusivity audit

Reviewed data: `data/exclusive.json`. Accepted edges are terminal outcomes that share a
`selection: one` group or a file-backed fact partition. The app never infers an edge from two
quests looking related.

## Accepted

| A | B | Mechanism | Evidence rows |
|---|---|---|---|
| Ciri lives: witcher ending (`ciri_witcher`) | Ciri lives: empress ending (`ciri_empress`) | q110_to_emperor is set only by the Emhyr line and is absent on the Velen line; q505 and q504 are the alternative journal endings. | 4 |
| Ciri lives: witcher ending (`ciri_witcher`) | Ciri dies in the White Frost (`ciri_dead`) | q502_ciri_survives and q502_ciri_dead are set in the same q502_avallach phase; q505 and q503 are the alternative journal endings. | 3 |
| Ciri lives: empress ending (`ciri_empress`) | Ciri dies in the White Frost (`ciri_dead`) | q502_ciri_survives and q502_ciri_dead are set in the same q502_avallach phase; q504 and q503 are the alternative journal endings. | 3 |
| Baron: his wife is alive (`baron_wife_cured`) | Baron: his wife is lost (`baron_anna_lost`) | q107_anna_is_crazy and q107_baron_hanged_himself are alternative terminal facts set in q107_swamps; 1002193 and 1002197 are alternative journal descriptions. | 3 |
| Hearts of Stone: Olgierd is saved (`olgierd_saved`) | Hearts of Stone: Olgierd dies (`olgierd_dead`) | q605_mirror_banished is set in q605_finale only when Gaunter is defeated; its absence after q605_finale is the fulfilled-pact branch. 1124241 and 1124242 are alternative journal descriptions. | 3 |
| Blood and Wine: both sisters live (`bw_both_sisters`) | Blood and Wine: Anna Henrietta dies (`bw_henrietta_dies`) | q705_henrietta_alive and q705_henrietta_dead are set by alternative ceremony lines; 1154626 and 1154625 are alternative journal descriptions. | 4 |
| Baron: his wife is alive (`baron_wife_cured`) | Baron: his wife burns (`baron_anna_burnt`) | The q107 terminal facts are alternatives set in q107_swamps; 1002193 and 1002195 are alternative journal descriptions in the same description group. | 3 |
| Baron: his wife is alive (`baron_wife_cured`) | Baron: his wife dies after the curse (`baron_anna_disenchanted`) | The q107 terminal facts are alternatives set in q107_swamps; 1002193 and 1002196 are alternative journal descriptions in the same description group. | 3 |
| Baron: his wife is lost (`baron_anna_lost`) | Baron: his wife burns (`baron_anna_burnt`) | The q107 terminal facts are alternatives set in q107_swamps; 1002197 and 1002195 are alternative journal descriptions in the same description group. | 3 |
| Baron: his wife is lost (`baron_anna_lost`) | Baron: his wife dies after the curse (`baron_anna_disenchanted`) | The q107 terminal facts are alternatives set in q107_swamps; 1002197 and 1002196 are alternative journal descriptions in the same description group. | 3 |
| Baron: his wife burns (`baron_anna_burnt`) | Baron: his wife dies after the curse (`baron_anna_disenchanted`) | The q107 terminal facts are alternatives set in q107_swamps; 1002195 and 1002196 are alternative journal descriptions in the same description group. | 3 |

## Rejected candidates

| Candidate | Source | Why it is not an edge |
|---|---|---|
| mq3012noblestatuette / mq3012warriorstatuette | cutoffs.json#triss_statuettes_window | both quests share the same closing window; the cutoff is a deadline, not a partition, and no failure block or CDeactivateSpawnset makes them exclusive |
| q402nilfgaardianally / q402novigradallies | cutoffs.json#brothers_in_arms | the same cutoff closes their window; both can be completed before it, so the pair is not an exclusion edge |

Cross-group outcome pairs not listed: 44. None has a shared failure block, cutoff or
`CDeactivateSpawnset` proof, so they are omitted rather than guessed. The groups are:

- `main_ciri`: `ciri_witcher`, `ciri_empress`, `ciri_dead`
- `baron_family`: `baron_wife_cured`, `baron_anna_lost`, `baron_anna_burnt`, `baron_anna_disenchanted`
- `hos_olgierd`: `olgierd_saved`, `olgierd_dead`
- `bw_sisters`: `bw_both_sisters`, `bw_henrietta_dies`

## Summary

4 groups, 11 outcomes, 11 accepted outcome edges, 44 cross-group pairs rejected, 2 cutoff candidates rejected
