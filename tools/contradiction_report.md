# Contradiction report

12 claims about the derived data tested against 517 saves: 12 hold, 0 do not.

115 prerequisites in the route were checked against the saves too.

## Prerequisites tested on the game's own condition

Not "the other quest is finished" but "its story reached the point that opens this": the fact is what the app tests, and no save breaks it (data/prereqs_review.json).

| step | requires | condition | saves under way the fact covers | violations |
|---|---|---|---|---|
| no_eye | no_junior | q302_whoreson_found | 7 | 0 |
| no_fencing | no_broken | q304_rosa_visited | 7 | 0 |
| no_gangs | no_junior | q302_whoreson | 218 | 0 |
| no_highstakes | no_pyres | q301_burn_doppler | 11 | 0 |
| no_honor | no_junior | q302_freed_rico | 13 | 0 |

## Every derived claim

| kind | claim | checked in | violations |
|---|---|---|---|
| implies_done | kg_start_gate: King's Gambit's journal entry is only added from The Lord of Undvik's graph, on the branch that | 102 | 0 |
| cutoff_consistent | now_or_never_blocks_statuettes: no save has a statuette quest finished after Triss's community was switched of | 457 | 0 |
| saves_present | now_or_never_blocks_statuettes: the cutoff rests on saves that actually reached Now or Never | 212 | 0 |
| implies_done | cave_follows_stranger: The Cave of Dreams' entry is added from the quest phase that runs Stranger in a Strange | 115 | 0 |
| not_failed | cave_follows_stranger: starting King's Gambit does not fail them | 102 | 0 |
| implies_done | kg_no_fail_phantom_stranger_cave: The Cave of Dreams' entry is added from the quest phase that runs Stranger i | 115 | 0 |
| not_failed | kg_no_fail_phantom_stranger_cave: starting King's Gambit does not fail them | 102 | 0 |
| not_failed | kg_heroesmead_refuted: no save has Coronation failed | 102 | 0 |
| reviewed_cutoff | reviewed cutoff triss_statuettes: Hand both statuettes to Triss before {binding} | 457 | 0 |
| app_dump | the built app reports what the data files say | 424 | 0 |
| settlement | every settled decision is in the route, and no route lock is refuted | 131 | 0 |
| reader | the save reader attaches statuses to the right entries | 40377 | 0 |

## Parser coverage

- *.w2phase: 522 files, {'UnsupportedVersion': 2}
- *.w2scene: 3036 files, {'Truncated': 1, 'UnsupportedVersion': 1}
- *.journal: 308 files, {'UnsupportedVersion': 20}

This is a consistency check, not a proof: the saves can refute a claim, and they can show no contradiction, but they cannot demonstrate that a quest stopped being possible. Where a claim rests on the files, the files are named in data/cutoffs.json.
