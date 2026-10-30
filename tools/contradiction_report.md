# Contradiction report

5 claims about the derived data tested against 547 saves: 5 hold, 0 do not.

5 prerequisites in the route were checked against the saves too.
The route is 403 quest steps + 9 reviewed manual steps = 412; the legacy feed and the 25 hold-off events are frozen and not claims of this release.

## Prerequisites tested on the game's own condition

Not "the other quest is finished" but "its story reached the point that opens this": the fact is what the app tests, and no save breaks it (data/prereqs_review.json).

| step | requires | condition | saves under way the fact covers | violations |
|---|---|---|---|---|
| mq3036rosaromance | q304dandelion | q304_rosa_visited | 7 | 0 |
| q302debt | q302mafia | q302_freed_rico | 13 | 0 |
| q302war | q302mafia | q302_whoreson | 218 | 0 |
| sq306maverick | q301dreamer | q301_burn_doppler | 11 | 0 |
| sq312vincentves | q302mafia | q302_whoreson_found | 7 | 0 |

## Every derived claim

| kind | claim | checked in | violations |
|---|---|---|---|
| reviewed_cutoff | reviewed cutoff brothers_in_arms: Finish Brothers in Arms before The Isle of Mists | 2 | 0 |
| app_dump | the built app reports what the data files say | 424 | 0 |
| route_coverage | every route step has derived evidence, and every evidence row has a step | 412 | 0 |
| settlement | every settled decision is in the route, and no route lock is refuted | 9 | 0 |
| reader | the save reader attaches statuses to the right entries | 24189 | 0 |

## Parser coverage

- *.w2phase: 522 files, {'UnsupportedVersion': 2}
- *.w2scene: 3036 files, {'Truncated': 1, 'UnsupportedVersion': 1}
- *.journal: 442 files, {'UnsupportedVersion': 20}

This is a consistency check, not a proof: the saves can refute a claim, and they can show no contradiction, but they cannot demonstrate that a quest stopped being possible. Where a claim rests on the files, the files are named in data/cutoffs.json.
