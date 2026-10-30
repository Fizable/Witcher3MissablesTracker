# Next Phase Plan — Witcher 3 Missables Tracker

Status: complete; 1.3.1 built and verified 2026-10-30.
Owner: the next coding agent.
Workspace: `C:\Steam\steamapps\common\The Witcher 3\w3tracker` (Rust + Tauri 2, version in `Cargo.toml`).
Scope: the `w3tracker/` project only. The game install and the saves are read-only. This plan is the source of truth; the mission prompt in chat is the entry point.

---

## 1. Mission

Execute Phases 0 through 5 end to end. Do not stop for check-ins. Do not ask the user questions. Test your own work. Finish with a release if the acceptance checks are green.

The user will be unavailable for a while. Make decisions from the locked decisions and defaults in this file; when a new ambiguity appears, choose the smallest reversible option consistent with payload-first, journal-truth, and completionist-first, and record it in the Decision Log. A phase is complete only when its acceptance checks pass and the evidence is recorded. If a check fails, fix the cause; never skip, weaken, or suppress it.

Only a hard blocker stops a step: missing game/REDkit files, unavailable saves, a missing build toolchain, or release credentials that cannot be obtained. Document the blocker with the exact command and continue with every other phase. Do not stop the whole mission for one blocked step.

---

## 2. Read first

Read these before changing anything:

- `../AGENTS.md` — workspace rules; the game install is not version-controlled; no game launch; no save writes.
- `README.md` — the product, the data pipeline, the build path.
- `docs/DESIGN.md` — the specification being audited.
- `docs/BACKEND_CONTRACT.md` — payload field definitions.
- `docs/CARD-WINDOWS.md` — the 15 reviewed card windows and the current card model.
- `docs/TARGET-SCHEMA.md` — targets, setup, guidance.
- `tools/README.md` — `questindex.py`, `questgraph.py`, `routegen.py`.
- `package.ps1` — the release/package path, before Phase 5.
- `NEXT-PHASE-PLAN.md` — this file.

The project conventions are plain prose, no emoji, no marketing language. The app must stay read-only against saves, offline (no HTTP client), and free of CD PROJEKT RED affiliation claims. Do not add network calls or save writes.

---

## 3. Hard constraints

- Work only inside `w3tracker/` for code and data. Do not modify `bin/`, `content/`, or `mods/`.
- Never launch the game. Never write to `Documents\The Witcher 3\` or the real `%APPDATA%\Witcher3MissablesTracker`.
- Use a temporary `APPDATA` profile and copied saves for every test. The real saves are read-only.
- `dsound.dll`, `dxgi.dll`, `dinput8.dll` and `xinput*` are single-slot loader hooks; do not replace one with another. Not relevant to this mission unless a game-file change is requested, which it is not.
- Never touch `content/content0/cookedfinal.redscripts`; script conflicts are resolved with Script Merger.
- Do not delete `_DLSS5_Backup/`, `*.original`, or `*.old` files.
- Do not add a runtime dependency without checking that the project already uses it. The UI is plain HTML/CSS/JS with no bundler and no `package.json` at that level.
- Do not add a network client to the app. Source links open a browser only when clicked.
- Do not add a feature whose only job is to display data the band already trusts. §7 of `DESIGN.md` is binding.
- Use `package.ps1` for packaging; do not invent a new release path.
- Keep the tree clean per phase; commit locally. Do not push to a remote or upload to a store unless the repo has a configured, authorized release command and credentials.

---

## 4. Locked decisions

These are decisions the user already made. Do not re-litigate them.

| Area | Decision |
|---|---|
| Invariant layer | Payload first. `get_view` must not emit violating data; the UI may simplify but must never be what makes an invariant true. |
| `UP NEXT` scope | `view.todo` = tracked quest + in-log quests + the **next** unblocked plan step. Available quests live in `MORE > PROGRESS`. |
| Tick semantics | A tick is a note. The journal wins: card, matrix and warning stay journal-true; show `tick disagrees`. Do not silently reinterpret existing ticks as done; preserve them as notes and show what the save says. |
| Guidance off | The plan survives; only exact `instructions` are gated. PLAN AHEAD, step titles and goal chips remain. |
| Card band rule | Only a card the player can act on now belongs in `top`; a window whose closing quest has not started is ledger-only. Never-missable cards never warn. |
| Order warning | Only when finishing A actually fails B. A soft recommended order is not a warning. |
| Design doc | Add the acceptance table and the state model. |
| Audience priority | Completionist first. Do not simplify away state; accept density in the ledger. The play surface must still answer what is at risk and what is next. Functional dead ends (tick, recovery, guidance-off plan, search contradiction) are still bugs. |
| Choice warning | Make it a `NOW` item. The band must warn that a choice matters to the endings in play, without printing the choice text or the recommended option. |
| Opens gate | Use a detailed source model: `requires`, `closes`, `fallback`, evidence. A row without an `opens` is ledger-only. There is no player-position signal; literal "I am at the Baron" is out of scope. |
| Baron card | The Baron gives **Sigismund Dijkstra** (`gwint_card_dijkstra`) through `cg100_no_mans_land.w2phase`. The current `none` classification is unsafe because it treats a deck definition as a collection grant. |
| Plan step | "Plan step" in `view.todo` means the next unblocked ahead step only, not all ahead steps. |
| Release | Automatic local build and commit when all acceptance checks are green; no remote push or store upload unless the repo has an explicit, authorized command and credentials. |
| User availability | The user will not answer. Do not ask. Decide from this file and record new decisions. |

---

## 5. Pre-fix audit summary

This section records the audit that started the phase, before Phases 1–5 changed the payload. The
"Partly", "Broken" and "Contradiction" verdicts below are the findings that drove those phases; the
final state is the progress log in section 11 and the acceptance record in `DESIGN.md` 10.2. They are
kept here as the reproduction trail, not as open work.

### 5.1 What was run

- `cargo test --locked`: 47 passed, 0 failed, 0 ignored.
- Headless runs on three real saves: newest `AutoSave_10d9e0_7ea4f000_581b307.sav`; earliest `ManualSave_53db8_7e221800_4f13d1b.sav`; median `ManualSave_5258a_7e224000_39e1473.sav`. The last two were copied to an isolated profile; the originals stayed read-only.
- `--view`, `--dump`, `--cards`, `--targets`, `--outcomes`, `--plan`, `--detail`, and a clean-profile run.
- Logs: `w3loadfix.log` healthy (0 verified mismatches), `ReShade.log` clean, `RenoDX-DLSS5-crash.log` normal detach, `WitcherNativeBridge.log` registrations OK. No tracker log exists.
- The working tree already had `ui/api.js`, `ui/app.js`, `ui/index.html`, `ui/style.css` modified before the audit; the audit reflects the working tree. No edits were made by the auditor.

### 5.2 Four method answers

1. **What a professional would do.** Build a requirement traceability matrix before reading code: row, payload field, DOM node, positive test, negative test. Reproduce on the real corpus and the real 480×820 pinned window. Separate spec defects from implementation defects. Test the warning adversarially (mid-quest, post-cutoff, ticked, no save, missing folder, goal on/off, guidance off). Measure first-run learnability as a task test, not an opinion. Protect the band.
2. **Rawest material.** The 518 real saves and the three sampled above; the game files behind `route.json`, `derived.json`, `branches.json`, `cutoffs.json`; the actual `--view`/`--dump` JSON; the actual DOM at 480×820; a clean profile and the four-goal profile; the logs. Not the README, not `ui/mock`, not the fixtures.
3. **Methods.** Traceability; differential headless runs (clean vs selected, view vs dump, detail vs search, explicit plan ids); JSON invariant checks; `cargo test`; the Python data checkers; DOM inspection; dependency and binary scan for the offline claim; log reading. The missing step is a mutation check: break each guarantee deliberately and confirm a named test fails.
4. **Proof.** Every §5 row has a green command/element/test triple and a test that fails when the guarantee is removed. The clean payload is spoiler-free. `top` contains only the four warning classes; ahead card windows are a count, never an item; an empty band is correct silence. `todo` matches its definition. The tick truth table passes for every journal state. A first-time player answers the six §9 questions unaided at 480×820. The document records the save, date, commands and results.

### 5.3 Surface traceability (§5)

| Surface | Command | UI element | Test behind it | Verdict |
|---|---|---|---|---|
| `NOW` band | `get_view.top` | `#topSec` (`ui/index.html:52-59`), `renderTop` (`ui/app.js:727`) | `top_tests` (6), `cards::card_top_items...` | **Partly.** Loss, cutoff, order and active card windows work. The fourth warning, a consequential choice, has no band path and no data: `ending_relevant` is 0 on every step. Ahead card windows also sit in `top`. |
| `UP NEXT` | `view.todo`, `view.tracked` | `#todoSec` (`index.html:61-72`), `renderTodo` (`app.js:906`) | `model::do_next...`, `frontier_states...` | **On screen yes; payload no.** 198 ids on the newest save (55 in the log), 302 on the earliest (2 in the log); all five plan-ahead steps are included. The UI filters at `app.js:919-921`; no test covers the filter. |
| `PLAN AHEAD` | `view.target`, `get_plan` | `#planAhead`, `renderPlanAhead` (`app.js:878`) | `plan::the_plan_orders_by_level...` | **Broken with guidance off.** `planMatchesView`/`loadPlan` require `guidance === 'on'` (`app.js:339-341`, `355-361`); the plan and goal chips disappear while `--plan` returns 7 steps. |
| quest detail | `get_detail` | `#detailPane` | no direct test | **Delivered, test gap.** Default `guidance: null`; the exact line is gated. |
| `can I do this now?` | `search`, `check_quest` | `#q`, `#hits`, `#verdict` | **nothing does** | **Contradiction.** The search path and the detail pane disagree about `mq3012noblestatuette`. |
| `MORE > STATUS` | `view.completion` | `#statusSec`, `#runSec` | `matrixcheck.py`, parts of `model` | **Delivered.** Six states named, no single percentage. No cargo test for `completion()`. |
| `MORE > CARDS` | `get_cards`, `set_card` | `#cardsSec` | 5 `cards` tests | **Delivered.** 224 cards: 129 owned, 94 not owned, 1 unknown; 15 Tier B windows. The source model is too coarse. |
| `MORE > COVERAGE` | `view.coverage` | `#coverageSec` | none | **Delivered, soft fail.** Gwent is six zeroes printed as `0`, with no "not modelled" marker. |
| `MORE > PROGRESS` | `view.completion.matrix` | `#progSec` | `the_generated_route_is_the_whole_game`, `matrixcheck.py` | **Delivered.** Section counts sum to 412. A latent sixth "Tracked" section exists. |
| goal picker | `get_targets`, `set_target` | `#targetPicker`, `#goalRow` | 5 `targets` tests | **Delivered but buried.** After the first-run card, the only entry is `⚙ my game`. |
| outcome matrix / tradeoffs | `get_outcomes`, `view.tradeoffs` | `#outcomeMatrix`, `#tradeoffsSec` | 7 `outcomes` tests | **Delivered.** 11 outcomes, 4 groups, 7 tradeoff edges. Conflicts are unreachable with the shipped targets. |
| guidance toggle | `set_guidance` | `#goalRow` button | gating tests only | **Delivered, but it deletes the plan.** |
| `my game` | `set_flag`, `set_level`, `set_folder`, `pick_folder` | `#flagsPanel` | exclusion test only; no command tests | **Delivered.** A flag can still override an active journal by construction. |
| header | `view.save` | `#saveName`, `#saveAge`, `#saveError` | none | **Delivered.** Name, age, read error shown. |
| first-run setup | `view.setup` | `#setupCard` | none; behavior documented in `TARGET-SCHEMA.md:57` | **Delivered**, but it sits above the warning. |
| pin | `set_pin` | `#pin` | none | **Delivered by inspection.** |

### 5.4 Invariants (§6)

| # | Invariant | Holds? | Evidence |
|---|---|---|---|
| 1 | Read-only, offline | **Yes, by inspection** | No HTTP client in the Windows dependency graph (`cargo tree -i reqwest`: nothing; `reqwest`/`hyper`/`ureq` strings in the exe: 0). Writes only `%APPDATA%\Witcher3MissablesTracker`; `open_url` is click-only. **No test enforces it.** |
| 2 | Journal outranks a tick | **Broken for "Not started"** | `model.rs:177` turns a tick on a non-manual step with `journal != "Done"` into `unknown`; `model.rs:304` makes the card `Done`; `main.rs:724` clears the watch because `tick_only` requires `journal == "Active"`. Tests cover only the `Active` case. |
| 3 | No spoilers by default | **Yes, functionally** | Clean profile: `target: null`, 0 goal steps, 0 tradeoffs, detail `guidance: null`. The cited proof `top_tests::only_the_journal_can_declare_a_loss` proves loss semantics, not spoilers; no payload-level test exists. |
| 4 | One denominator | **Yes** | 412 = 403 + 9; Gwent 11; sections 96+183+35+87+11 = 412; `model::tests::the_generated_route_is_the_whole_game` passes. |
| 5 | Ahead card window is a count, not a warning | **Broken in the payload** | Clean `--view`: two `MISSABLE CARD` items. Earliest save: only eight `MISSABLE CARD` items; the band is hidden and the promised count is cleared. The UI strips the pair at `app.js:731-732`. |
| 6 | Conflicts are stated, not resolved | **Engine yes; product unreachable** | `plan::tests::two_outcomes_in_one_group_are_a_conflict` passes. The four shipped targets are one per group, so no selectable pair can conflict. |
| 7 | Exact lines only on the step the player is on | **Yes** | `--plan`: 7 steps, 5 ahead, instructions only on 4 ahead steps; `q502avallach` is a confirmation step with no line. Test passes. |
| 8 | No affiliation claim | **Yes** | README and `NOTICE.txt` state it. No test. |

### 5.5 Bugs

**1. The fourth warning is not delivered anywhere (§2 item 4, NOW).** `top_items` (`main.rs:938`, `cards.rs:298`) produces only loss-edge, failed-quest and card entries. `tags_of` (`model.rs:580`) would emit `ENDING CHOICE` if `ending_relevant` were true, but `data/route.json` has **0** steps with `ending_relevant: true` on all three saves. The band never says "this quest contains a choice that matters to the endings in play"; at best the card says the generic `CHOICE`. *Repro:* `--view`, count `steps[*].ending_relevant` (0), inspect `top[*].tag` (no choice tag). *Decision:* make it a NOW item; needs a data review and a top item with no choice text.

**2. `view.top` pads the band with card windows that are still ahead (§5 NOW, §6.5).** `cards::top_items` emits `kind: "card"`, `tag: "MISSABLE CARD"` for `ahead` (`cards.rs:298`, `371`); `view()` extends `top` with it (`main.rs:938-940`). The contract's `TopItem.kind` is only `lost|failed|risk|missable`, so this is also contract drift. *Repro:* clean `--view` top = statuettes + Iorveth `CARD WINDOW OPEN` + Gaunter/King Bran `MISSABLE CARD`; earliest save top = eight `MISSABLE CARD` and nothing else. *Fix:* drop `ahead` from `top`; `open` (actionable) only; Phase 2 adds the source model.

**3. `view.todo` is the route, not the play queue (§5 UP NEXT).** `model::evaluate` puts every unlocked, non-optional `Not started` step into `todo` (`model.rs:449-457`); `view()` exports it (`main.rs:1002`). Latest: 198 ids, 55 in the log, 133 available; earliest: 302 ids, 2 in the log. All five plan-ahead steps are included. *Repro:* `--view`, `q502avallach in todo` is true while its `frontier` is `available`. *Decision:* tracked + in-log + **next** plan step only; available quests live in PROGRESS.

**4. Turning guidance off deletes the plan (§3, §5 PLAN AHEAD).** `planMatchesView` returns false unless `target.guidance === 'on'` (`app.js:339-341`); `loadPlan` returns early otherwise (`app.js:355-361`). The plan is a "what is still coming" surface; only `instructions` are guidance. *Repro:* select a goal, open **my game**, click `Guidance: off`; the plan disappears. `--plan` still returns 7 steps. *Decision:* plan survives; exact lines gated.

**5. A tick on a journal "Not started" step splits the card and the matrix, and clears its watch (§6.2).** `node_status` makes a ticked non-manual step `Done` (`model.rs:304`); `classify` returns `unknown` because the journal has no completed entry (`model.rs:177`); `attach_derived` clears `watch` because `tick_only` requires `journal == "Active"` (`main.rs:724`). *Repro:* open `q402velenallies` → `Mark this done anyway`; PROGRESS shows a green check, STATUS counts `unknown`, and the watch is gone. *Decision:* a tick is a note; card, matrix and warning stay journal-true; `tick disagrees` is shown.

**6. The search answer and the detail answer disagree about the same quest (§5 search, §2 last sentence).** `detail_json` uses `model::check_quest` alone (`main.rs:1128-1132`), which knows only `ev.events`. The `check_quest` command overwrites that verdict with the first reviewed watch for the quest file (`main.rs:1275-1289`), and `derived_watch_for` (`main.rs:735`) never calls `live_cutoff`, so it is save-blind. *Repro:* `--detail mq3012noblestatuette` says `"Safe: no cutoff is known for it"`, while the same step's card carries `"Hand both statuettes to Triss before Final Preparations ends"`. The search box would return the warning instead of "safe". No test covers `check_quest`. *Decision:* one save-aware verdict path.

**7. When ahead card windows are the only thing at stake, the promised count disappears (README NOW, §2).** `renderTop` only adds the `+N later card warnings` link when `items.length && later.length`, then clears it when `!items.length` (`app.js:733-742`). The earliest save has exactly this state: `top` is eight `MISSABLE CARD` entries, so the band is hidden (correct per invariant 5) and the count is hidden too (not correct per README). *Decision:* the later count belongs in `MORE > CARDS > LATER`, not the band; README changes.

**8. `--dump` cannot see the card part of the NOW band (§9, README audit).** The dump builds `top` from `top_items` only (`main.rs:1500`), while the window gets `top_items` plus `cards::top_items` (`main.rs:938`). Latest: dump top 1, view top 4. *Repro:* run both on the same save. *Fix:* dump must use the same top builder.

**9. The conflict path cannot be reached with the shipped targets (§5 outcome matrix, §6.6).** `--targets` returns four ids, one per group: `baron_wife_cured`, `ciri_witcher`, `olgierd_saved`, `bw_both_sisters`. `ciri_empress` is an outcome, not a target. `--plan ciri_witcher,ciri_empress` reports `ciri_empress` invalid and builds a ready plan for the valid half. The unit test proves the engine, not the product.

**10. PROGRESS can gain a sixth "Tracked" section (§5 PROGRESS).** `effective_route` inserts `Tracked` for a journal the route does not know (`main.rs:552`), but `matrix.sections` has no counts for it. `renderProgress` renders `v.sections` and shows `—`/a zero bar (`app.js:986-1000`). Latent: the newest tracked quest is in the route.

**11. A `my game` flag can overrule an active journal (§5 `my game`).** `is_na` runs before status (`model.rs:315-330`); a contradicted flag sets the step `N/A`, and `classify` returns `excluded`. Current flags (`letho=no`, `keira_sent=yes`, `triss_romance=no`, `yen_romance=yes`) only touch `Not started` journals, so nothing is overruled in this save. The code path is unconditional; no test covers a flag against `Active`. Latent.

**12. Gwent's COVERAGE row is a bare all-zero row (§5 COVERAGE, soft).** `View.coverage.packs.gwent` is all zeros; `renderCoverage` prints each zero (`app.js:441-470`). The legend says a zero is not a clean bill, but the row has no "not modelled" marker. It should say HoS has no Gwent pack, not six zeroes.

### 5.6 What is solid

The engine is not the problem. 412 = 403 + 9 holds; section totals sum exactly; the six-state matrix sums on all three saves; the plan orders by level then route and strips instructions from settled steps; 15 Tier B card windows carry source and review date; an unreadable collection block yields `unknown`, never `not owned`; the default payload is spoiler-free; the Windows binary has no HTTP client; the 47 tests are meaningful. The failures cluster at the seam between payload and UI, not in the route model.

### 5.7 Test gaps

No tests for `search`/`check_quest`, `detail_json`, `completion()` math, coverage, header, setup, pin, folder/flag commands, or any JS. The Python data checkers cover the data shape, not the rendered surface. No mutation test proves that removing an invariant breaks a test. The cited §6.3 test does not prove the spoiler claim.

### 5.8 UX/learnability sweep

Scenario: 480×820, pinned, one save, no goal.

| Question from §9 | Answer | Evidence | Smallest change |
|---|---|---|---|
| Can a first-time player tell what is at risk now? | **Yes for quests; no for card deadlines on a fresh save** | Newest: two items with headline and action. Earliest: band invisible, eight ahead card windows, no count. | Keep the band hidden; put the later count in CARDS; with the decision, the fresh band is correctly empty. |
| Can they tell what to do next? | **Yes** | `UP NEXT` puts the tracked quest first, then in-log quests; the first card carries `CURRENT OBJECTIVE` (`app.js:840-860`). | One clause in the legend explaining the order; no new control. |
| Can they find how to tick a step? | **No** | Only manual cards carry `mark done` (`app.js:857`). PROGRESS icons are disabled unless `manual` or `Assumed` (`app.js:957-963`). The only path is the detail page's collapsed `<details>` labelled `Mark this done anyway` (`app.js:1279`), which reads as an override, not a tick. | Surface that existing control as a plain button and label the disclosure "Something wrong with this reading?" The backend rule already exists. |
| Can they find the goal picker? | **No after the first run** | The first-run card is a one-time invitation. After Skip (or Cancel, which also writes `setup_v1`), the only entry is `⚙ my game` (`index.html:14`), whose tooltip says "Letho, Keira, romances"; the goal row is inside (`index.html:40-44`, `app.js:283-300`). | Move the existing `Ending goal: none [Choose]` row to the header, or rename the gear to `my game · goals`. Under completionist-first this is an accepted tradeoff, not a blocker. |
| Do they know what `MORE` holds? | **Weak yes** | The button is `⋯ more`; contents are only in the hover title (`index.html:15`). One click opens a labelled tab bar. | Put the tab names in the button's visible/aria label. Copy only. |
| Can they recover from a missing save or unfound folder? | **Yes, with two gaps** | `save.error` is a red alert (`index.html:24`, `app.js:135-142`); the panel auto-opens once when either folder is not OK (`app.js:200-205`) and shows path, ✔/⚠, Browse, Use and a manual path. Gaps: `panelAutoOpened` never resets, so a later missing save does not reopen it; a corrupt save says `reading save... (...)` indefinitely (`main.rs:468`) with no next step; a failed Browse is silent. | Reset the auto-open when `save.error` becomes non-empty; name the file and the action in the corrupt message; report a failed Browse. |

Additional first-run findings: the optional goal card sits above NOW in document order (`index.html:43-59`); the pitch precedes the product. With no save, UP NEXT says `Nothing queued right now` (`index.html:72`, `app.js:932`) because no step is in the log; change it to `Load a save to see what's next` when `save.error` is set. The band uses five tag strings and a colour code; the headline and action carry the meaning, but the first read is heavy. The band's `max-height: 52vh` (`style.css:308-309`) can hold roughly three cards; more becomes an inner scroll with no "more" cue.

Under completionist-first: the goal picker, the `MORE` label and the setup card's position are accepted tradeoffs; a completionist will open those surfaces. The tick control is not a density tradeoff — with note-only semantics it must visibly say "noted; the save still says Not started". Missing-save and missing-folder recovery also remains a functional dead end. The band and UP NEXT must still answer "what is at risk" and "what next" without opening MORE; the six-question test stands, with a completionist threshold for the optional surfaces. Do not strip the plan or the ledger to calm the play surface.

### 5.9 Design document critique

`DESIGN.md` is a strong charter and a weak specification. The gaps:

1. The "backend" column names a field, not a layer. Two failures (ahead cards in `top`, 133 not-in-log ids in `todo`) are payload violations the UI silently repairs.
2. The invariants do not name their enforcement. §6.3 cites a test that proves loss semantics, not spoilers. §6.1 and §6.8 have no test.
3. There is no state model. "Actionable", "settled", "at risk", "ahead" and "a gap the save cannot see" are used as if defined. The tick truth table is the clearest casualty.
4. §2 says "exactly these four" but the product has five tags and a card kind. "Order" has no top item type. "Consequential choice" has no top item at all.
5. §5 and §9 have no acceptance scenarios. Six learnability questions are a good start, but there is no starting state, expected visible text, viewport, or pass threshold.
6. §4's "no single completion percentage" needs a ruling on the PROGRESS bar.
7. There is no verification record. The README claims 500+ saves; the audit runs three. Record save name/hash, date, commands and results per row.
8. The refusals are good but under-specified. "No feature whose only job is to display data the band already trusts" needs worked examples.

The minimal upgrade is a row-contract table (row, question, payload, DOM selector, positive test, negative test, last verified), a state-model section (six matrix states, tick truth table, card-window lifecycle, warning lifecycle, search/detail), six scripted first-run scenarios, and a layer column on the invariants.

### 5.10 Card and statuette availability finding

The card and turn-in examples are the concrete case for the source model.

**Baron / Dijkstra.** `cg100_no_mans_land.w2phase` block 551 is a `CQuestScriptBlock` with comment `gwint_card_dijkstra`, function `AddItemQuestExt`, followed by `CQuestRewardBlock` `cg_baron`; the same graph contains `CGwintMinigame` with deck `Baron`, the `cg100_02_baron.w2scene` dialogue, and a `CQuestContextDialogBlock` to `baron_default.w2scene`. Conditions include `cg_baron_discovered >= 1`, `q107_baron_hanged >= 1`, `Player has cg100_barons_notes`, and the phase tests `q107_failed`, `q107_complete`, `q105_will_help_children`, `q402_escort_completed`. The quest objectives include both "Win a unique card from the baron" and "Look for a unique card and information about other players in the baron's office." The direct opportunity is playing the Baron before the Baron line ends; the office is the fallback.

The current `gwent_cards.json` classifies Dijkstra as `kind: "none"` because `cardwindows.py` treats the `starter_deck` row from the `north` deck definition as a persistent source. A deck list is evidence that a card can appear in a deck, not that the player owns it. The row has no `native_script` / `OnGwintSetupNewgame` collection-grant source. The `none` is unsafe. The same false-persistent-source risk applies to any card whose only "persistent" evidence is a deck definition or an opponent deck.

**Statuettes.** `mq3012_jade_statuettes.w2phase` sets/tests `mq3012_noble_statuette`, `mq3012_soldier_statuette`, `mq3012_both_statues`, `mq3012_endgame`, `mq3012_noble_done`, `mq3012_soldier_done`, and tests `q310_philippa_rescued`, `q310_keira_done`, `q309_completed`, `q301_met_kob`. The Triss turn-in scenes `mq3012_04_triss_remove_curse.w2scene` and `mq3012_05_lifting_curse.w2scene` have choices whose `section_facts` are exactly both statuette facts. `branches.json` already records:

```
tests: ["mq3012_noble_statuette", "mq3012_soldier_statuette"]
sets:  ["mq3012_spell_cast", "mq3012_statuette_placed"]
```

The save exposes facts (`main.rs:62`, `save.rs:223`), so the runtime can evaluate them. The current watch only says "before Final Preparations ends" (`q210preparations`); it never says "both statuettes in hand — talk to Triss now" or "you still need the soldier statuette". The linkage is missing, not the signal.

**The general model.** Separate **source**, **availability** and **missability**:

- Source: vendor, opponent, dialogue, quest reward, phase grant, loot.
- Availability: `requires` (facts, items, quest phases, dialogue choices), `closes` (event/phase/failure), `fallback`.
- Missability: true only if every source can close; a real persistent source makes it false.
- Runtime states: `not_yet` (no source's requires met; ledger only), `open` (a source is usable now; the only card state in the band), `check`/`lost` (closed; post-cutoff warnings), `owned`/`unknown`/`none` (no warning).
- Layers: raw (everything the scripts say), reviewed (what the app may claim, with source/date), runtime (what the save evaluates).
- Evidence ranking: collection grant > phase grant > reward > loot > vendor (only while the vendor exists) > deck definition (not ownership) > opponent deck (not a reward).

---

## 6. Phases

### Phase 0 — Freeze the definitions (docs only)

Update `docs/DESIGN.md`, `README.md`, `docs/BACKEND_CONTRACT.md`, `docs/CARD-WINDOWS.md`, and `docs/TARGET-SCHEMA.md` with:

- §2.3 card wording: "a card window you can act on now, or one that has closed"; §2.4 choice warning as a NOW item; "Order" only when finishing A actually fails B.
- §5 `UP NEXT` payload = tracked + in-log + next plan step; available quests in PROGRESS.
- §5 `NOW` must never show a card before the player can act on it, or pad the band.
- §6.2 tick truth table; §6.5 card state model (`not_yet/open/check/lost/owned/unknown/none`); §6.3 payload spoiler test; §6 layer/test/last-verified columns.
- §4 ruling on the PROGRESS bar; §9 six scripted first-run scenarios at 480×820.
- §7 refusal for literal player location; the save has no position signal.
- `BACKEND_CONTRACT`: `todo` definition; `TopItem.kind` includes `card`; `window_live` states and per-source `requires`/`closes`/`fallback`.
- `README`: ticks are notes; the later count is in CARDS, not the band.

Acceptance: every §5 row has a payload/DOM/test/last-verified entry; no code behavior changes. This phase is first because bugs 2, 3, 5 and 7 are ambiguous without the definitions.

### Phase 1 — Make the payload true (backend + minimal UI)

1. **`view.todo`**: tracked + in-log + the next unblocked plan step. Files: `src/model.rs` todo/evaluate, `src/main.rs` view. Tests for exact membership on the three saves; remove the UI filter at `ui/app.js:919-921`.
2. **Card top**: `cards::top_items` excludes `ahead`; only `open`/`check`/`lost`; add `kind: "card"` to the contract; remove the UI strip at `ui/app.js:731-732`; move the later count to CARDS.
3. **Tick note-only**: `node_status`/`classify`/`attach_derived`; keep the journal state, matrix state and watch; show `tick disagrees`; tests for `Not started`/`Active`/`Done`/`Failed`/`Assumed`; update README. Handle existing tick data as notes.
4. **Guidance off**: plan survives; `target.guidance` gates `instructions` only; update `loadPlan`/`planMatchesView`; tests.
5. **Search/detail**: one save-aware verdict; `check_quest` uses `live_cutoff`; `detail_json` uses the same path; test `mq3012noblestatuette` (safe vs watch) and a Done/Failed case.
6. **`--dump` parity**: use the same top builder; test dump top = view top.

Acceptance: clean top has no ahead cards; earliest top is empty (correct silence); newest top keeps the active Iorveth only; `todo` is tracked + in-log + next; tick truth table passes; guidance off yields 7 plan steps and 0 instructions; detail/search agree; dump=view; 47+ tests pass; no new HTTP or save writes.

### Phase 2 — Source availability (the data expansion)

**2A. Evidence model.** Split `starter_deck` into `deck_definition` (not ownership) and `collection_grant` (native `OnGwintSetupNewgame`). Reclassify cards whose only "persistent" source is a deck list or opponent deck. Dijkstra is the first case.

**2B. Extractor.** From each `CQuestScriptBlock` item grant (`AddItemQuestExt`/`AddItem`), walk the graph backwards through `CQuestGraphSocket`/`CGraphConnection` to `CQuestPauseConditionBlock`, `CQuestFactsDBCondition`, `W3QuestCond_*`, and the scene/dialogue block. `tools/questgraph.py` already has `incoming_blocks`, `_connections`, `props` and `label`; extend the walk to emit `requires`, `closes`, `fallback`, evidence. Attach the grant to the card id via the `gwint_card_*` comment.

**2C. Dijkstra proof.** Direct Baron source + office fallback; test on a save before the Baron line and one after it; `open` only when the Baron is available; `check`/fallback when he is gone; `owned` when the card is owned. Do not call it `none` until the native collection grant is checked.

**2D. Statuette proof.** A dialogue source with `requires` both statuette facts and `closes` q210preparations; test both/one/neither; say "talk to Triss now" only with both, "you still need the soldier statuette" with one, "before Final Preparations" as the outer deadline.

**2E. The 15 reviewed windows.** Add `opens`/active gates; six groups use the closing quest active; Thaler/Lambert need an earlier step/fact; never-missable cards are filtered out of the band. A row without `opens` is ledger-only.

**2F. The 224-card audit.** Every card gets its sources, conditions and fallbacks; the reviewed layer decides what the app may claim; the checker rejects a `none` that rests only on a deck definition, a `missable` without a source/closing condition, or a condition that is not a real fact/item/phase. Mutation tests for the checker.

Acceptance: Dijkstra source truth table; statuette dialogue truth table; no `not_yet` card in `top`; CARDS shows the exact reason; every card has evidence; checker mutation tests. This is the largest phase; do not start it before Phase 1's `ahead` filter, and do not ship unreviewed conditions.

### Phase 3 — Remaining completeness and latent bugs

- **Choice warning:** add the `ending_relevant` data review and a NOW item that names the choice without text; test a reviewed branch; keep the default payload spoiler-free.
- **Conflicts:** add a second target per group (data) or document the conflict as unreachable; test the product path, not just the engine.
- **Sixth Tracked section:** guard `effective_route` or add matrix counts; test.
- **Flag vs Active journal:** guard against N/A when the journal is Active; test.
- **Gwent coverage:** label the pack "not modelled"; test.
- **Test gaps:** `search`/`check_quest`, `detail_json`, `completion()`, coverage, setup/pin/folders/flags, JS; mutation tests for invariants 1, 3, 4, 5, 6, 7.

Acceptance: every §5 row has a positive and negative test; every invariant has a failing test when removed; no latent section or flag overrule.

### Phase 4 — UX

- **Tick:** surface the existing control as a plain button on the detail page; label the disclosure "Something wrong with this reading?"; show note semantics.
- **Recovery:** reset the auto-open when `save.error` becomes non-empty; name the corrupt file and the action; report a failed Browse; change the no-save empty text.
- **Setup card:** move below NOW or collapse to one line. Under completionist-first this is lower priority, but §1 still says the warning is the product.
- **Goal picker / MORE:** optional under completionist-first; if done, move the goal row to the header or rename the gear, and put the tab names in the MORE label.
- **Band:** a scroll cue at 52vh; copy for the five tags.
- **First-run test:** six scenarios at 480×820, with a completionist threshold for optional surfaces.

Acceptance: no dead ends; tick control discoverable; recovery works twice; the band and UP NEXT answer their questions without opening MORE; DOM evidence, not screenshots unless requested.

### Phase 5 — Verification and release

Run `cargo test --locked`; headless `--view`/`--dump`/`--cards`/`--targets`/`--outcomes`/`--plan`/`--detail` on the three saves plus the clean profile; check 412, section sums, top/todo membership, tick truth table, search/detail parity, dump parity, and the card/statuette truth tables; scan the payload for spoilers and the binary for HTTP; read the logs; record the save names, dates, commands and results in `DESIGN.md`. If shipping, bump `Cargo.toml`, `tauri.conf.json` and the README together, add a release note under `docs/RELEASE-x.y.z.md`, run `package.ps1`, verify the artifact, and commit locally.

Acceptance: every row has a green triple or an explicit "not delivered" note; no regression; limitations reported, not hidden; release artifact verified; progress log complete.

---

## 7. Self-testing playbook

The user must not be asked to run anything, inspect a save, or look at the UI. Test everything here.

### 7.1 Build and unit tests

```
cd w3tracker
cargo test --locked
cargo build --release
```

The release binary is `target/release/witcher3-missables-tracker.exe`. If `cargo test` fails, fix the cause; do not skip tests or weaken assertions.

### 7.2 Isolated profiles and saves

Use `w3tracker/.next-phase/` for temporary data (gitignore it or remove it before the final commit). The app writes under `%APPDATA%\Witcher3MissablesTracker`, not `%APPDATA%` directly; the settings file must be at `$APPDATA/Witcher3MissablesTracker/settings.json`.

```
mkdir -p .next-phase/appdata/Witcher3MissablesTracker .next-phase/saves
cp "<real save>.sav" .next-phase/saves/
printf '{"saves_dir":"<absolute path with forward slashes>"}' \
  > .next-phase/appdata/Witcher3MissablesTracker/settings.json
APPDATA="$PWD/.next-phase/appdata" ./target/release/witcher3-missables-tracker.exe --view .next-phase/view.json
```

Use three real saves: newest, earliest, median. Copy them; never modify the originals. Use an empty temp `APPDATA` with no settings for the clean/default payload. Run the same commands with the four-goal profile copied from a temp settings file, not the real one.

### 7.3 JSON invariants

Check at least:

- 412 = 403 + 9; Gwent 11; sections 96+183+35+87+11 = 412.
- Matrix states sum to 412 on every save.
- `top` has no `MISSABLE CARD`; no `not_yet` card; only `open`/`check`/`lost` plus the three quest warning classes.
- `todo` is exactly tracked + in-log + the next plan step; no available ids, no all-five plan-ahead ids.
- Clean payload: `target: null`, 0 goal steps, 0 tradeoffs, detail `guidance: null`.
- Detail/search agree on `mq3012noblestatuette` and on a Done/Failed case.
- `--dump` top equals `--view` top.
- Card counts: 224 total, 129/94/1 owned/not/unknown on the newest save; 15 Tier B; no `not_yet` in `top`.

### 7.4 Tick truth table

For a non-manual step with a live watch (the newest save has `q402velenallies` as `Not started`), test every journal state:

| Journal | Tick | Card | Matrix | Watch |
|---|---|---|---|---|
| Not started | off | Not started | obtainable | present |
| Not started | on | Not started + note | obtainable | present |
| Active | off | Active | at risk/obtainable | present |
| Active | on | Active + note | unchanged | present |
| Done | off | Done | done | cleared |
| Done | on | Done | done | cleared |
| Failed | off | Failed | lost | cleared |
| Failed | on | Failed | lost | cleared |
| Assumed | on | Assumed | excluded/unknown | per flags |

Use real saves where possible; use Rust fixtures for states the corpus lacks. The UI must not show a green "done" check for a note-only tick.

### 7.5 Card and statuette truth tables

- **Dijkstra / Baron:** before the Baron line, `open` when the Baron is available; after the line, the office fallback (if reachable) or a check/lost state; owned when the save owns it. Test the source conditions, not just the card count.
- **Statuettes:** both facts → "talk to Triss now"; one fact → "you still need the other statuette"; neither → "find both"; the q210preparations deadline remains the outer `check`/`lost` window. Test the dialogue gate separately from the cutoff.
- If no real save has a state, add a Rust fixture for the model and mark the UI check as fixture-based. Do not invent a save or write one.

### 7.6 UI testing

The app is Tauri; native WebView automation is not available per `AGENTS.md`. Test the real `ui/` DOM by serving it locally and stubbing the Tauri bridge:

- Prefer the available browser/preview tools. Serve `ui/` on loopback, inject a mock `window.__TAURI__` (or the module's `invoke`) that returns the `--view` payload, and check `renderTop`, `renderTodo`, `planMatchesView`, `patchRow`, the tick control, the setup card and the error states.
- If a browser is not available, build a small dev-only DOM harness (Node + a DOM shim or `jsdom` if already available) that loads the real `app.js` and `index.html`. Do not add a runtime dependency to the app; keep the harness outside the shipped UI.
- If neither is possible, test the pure render logic with a minimal DOM shim and record the limitation in the progress log. Do not ask the user to look at the screen.
- The viewport is 480×820. Check the band at 52vh, the setup card position, the no-save empty text, the corrupt-save message, and the missing-folder panel.

### 7.7 Mutation tests

For at least invariants 1, 3, 4, 5, 6 and 7, temporarily break the guarantee and confirm the named test fails, then restore the exact file. Examples: add an ahead card to `top`; make a tick set `Done`; hide the plan when guidance is off; drop the spoiler filter; remove the conflict test; put an instruction on a settled step. Keep a copy of the file in `.next-phase/` before the mutation; restore it; verify `git diff` is back to the intended change. Do not leave a mutation behind.

### 7.8 Logs

Read `w3loadfix.log`, `ReShade.log`, `RenoDX-DLSS5-crash.log`, `WitcherNativeBridge.log`, `OptiScaler.log` if present. There is no tracker log; do not add one just for the audit. If a test writes a log, keep it in `.next-phase/` and summarize it.

### 7.9 No user testing

Never write "please test", "check the UI", "run this and tell me", or "does this look right?" in the final message. The mission is not complete until the self-tests pass or a hard blocker is documented.

---

## 8. Autonomy protocol

- **Do not stop for check-ins.** Do not end with a plan, a question, or "next I will". End only when the Definition of Done is met or a hard blocker is documented.
- **Do not stop after a phase.** Proceed to the next phase; the progress log is the resume point if the turn is interrupted.
- **No user questions.** The user is unavailable. Use the locked decisions; for a new ambiguity, choose the smallest reversible option consistent with payload-first, journal-truth, and completionist-first, and record it in the Decision Log.
- **Phase gates.** A phase is complete only when its acceptance checks pass and the evidence is recorded. If a check fails, fix the cause; never skip, weaken, or suppress.
- **Hard blockers.** Missing game/REDkit files, unavailable saves, missing toolchain, or release credentials. Document the exact command and continue with every other phase. Do not stop the whole mission.
- **Scope discipline.** No unrelated refactors, no new features beyond the plan, no network client, no save writes.
- **Progress updates.** A brief update per phase is fine, but it must be followed by more work in the same turn. Do not ask for permission.
- **Commit per phase.** Follow the repo's commit style. Keep generated artifacts out of the commit.
- **Resume.** Read the progress log first. If a phase is marked complete with evidence, skip it. Never redo completed work.

---

## 9. Release protocol

The user asked for automatic releases when it fits. Read `package.ps1` before starting Phase 5.

1. Bump the version in `Cargo.toml`, `tauri.conf.json` and `README.md` together. Use the repo's existing version scheme; do not guess a major jump.
2. Add `docs/RELEASE-x.y.z.md` following the existing release-note style. State the user-visible changes and the verification commands.
3. Run the release build through `package.ps1` (PowerShell). Verify the installer/artifact in `dist/`; do not hand-roll a different packaging command.
4. Run the Phase 5 verification against the built artifact, not only the debug binary.
5. Commit locally with a clear message covering the release. Do not push to a remote, tag remotely, or upload to a store unless the repo has an explicit, authorized release command and credentials.
6. If signing/store credentials are missing, produce the unsigned local build, document the exact remaining step, and do not block the rest of the mission.
7. If the release path is unsafe or would modify the game install, stop that step and document it; keep the code and tests.

A release is not a substitute for the acceptance checks. If any phase is incomplete or a check is red, do not bump the version; leave a green build and a progress note instead.

---

## 10. Definition of Done

- Phases 0-5 complete, or a hard blocker documented with the exact command and the rest complete.
- Every §5 surface has a command/UI/test/last-verified entry.
- Every §6 invariant has a positive and negative test; the mutation checks pass.
- Clean payload is spoiler-free; `top` has only actionable warnings; `todo` is exact; the tick truth table passes; guidance off keeps the plan; search/detail agree; dump equals view.
- Cards: source model, evidence ranking, Dijkstra/statuette truth tables, 224-card audit, checker and mutation tests; no `not_yet` in `top`.
- UX: six questions pass at 480×820 with the completionist threshold; no dead ends for tick or recovery.
- `cargo test --locked` green; three saves and the clean profile green; no game/save writes; app offline.
- Release: version/changelog/package artifact verified and committed locally, or a documented credential blocker.
- Progress log complete; no unanswered questions; no user testing requested.
- The tree is clean except for the intended release artifacts; no temp `.next-phase/` left behind.

---

## 11. Progress log

Update this table after each phase. Include the command, the key counts, and the commit.

| Phase | Status | Evidence | Commit |
|---|---|---|---|
| 0 — Definitions | Complete | `DESIGN.md` sections 9-10 (state model, acceptance table, six scenarios); `BACKEND_CONTRACT.md` todo/TopItem/card states; `README.md` tick and card wording; `CARD-WINDOWS.md` source model. Docs only, no code behaviour change. | b6ad822 |
| 1 — Payload truth | Complete | `cargo test --locked`: 53 passed. Four isolated profiles: clean `top=[]`, `todo=0`; earliest `top=[]`, `todo=2`; median `todo=52`; newest `todo=65`, cards 129/94/1. `--dump` top equals `--view` top on all four. Tick table run on real saves: Not started + note stays Not started; Active + note stays Active; Done and Failed keep their state and clear the watch. Detail/search share `verdict_for`. | b6ad822 |
| 2 — Availability | Complete | 224 cards = 15 missable (15 Tier B) + 17 one-time + 192 no-window; 200 sourced / 24 explicit unknown. `starter_deck` split into `deck_definition` (weak) and `collection_grant`; Dijkstra reclassified from `none` to one-time at `cgnomansland`, opened by `cg_baron_discovered`, with the Baron's office fallback. All 15 reviewed windows carry `opens`; 17 one-time rows carry an open gate. `cardwindows.py check` green; `test_cardwindows.py` 13/13; `cards.py check` green; 56 Rust tests. | 8c83a24 |
| 3 — Remaining completeness | Complete (product conflict documented) | Choice warning is a NOW item from runtime ending branches, live only on an Active quest. Sixth `Tracked` section is gone: the matrix owns the section list and `effective_route` no longer inserts a section. Flag vs Active is guarded and tested. Gwent/HoS coverage reads `not modelled`. Tests added for the default payload, the tick table, flags, choice items, offline/read-only. Mutation checks 1,3,4,5,6,7 pass. Conflicts: engine test passes; the four shipped targets are one per outcome group, so a selectable conflict is impossible in 1.3 and is recorded as such rather than given fake targets. | b6ad822 |
| 4 — UX | Complete | Tick is a plain NOTE button on the detail page, disclosure renamed "Something wrong with this reading?"; PROGRESS shows a pencil note, never a green check, for a note-only tick. Auto-open resets on a new read error; a corrupt save names the file and the retry; a failed Browse reports in the folder panel. Setup card moved below NOW; gear renamed `my game · goals`; MORE carries an aria label. Six first-run scenarios at 480x820 recorded in `DESIGN.md` 10.1; DOM checks run against the real `ui/` with a stubbed bridge. | b6ad822 |
| 5 — Verification and release | Complete | `cargo test --locked` 57/57; `py tools/cardwindows.py check`; `py tools/test_cardwindows.py` 13/13; `py tools/cards.py check`; three copied saves + clean; statuette turn-in both (newest) / soldier missing (median) / neither (earliest); Dijkstra owned (newest, median) and not_yet (earliest), active/check/fallback in Rust fixtures; `--dump` top equals `--view` top on all; `package.ps1 -Bump minor` built 1.3.0; packaged exe verified; artifact hashes in `docs/RELEASE-1.3.0.md`. Post-release audit found the no-save verdict/detail leak; 1.3.1 adds `save_is_ready` and clears `derived.watch` without a save, 57 tests, clean and three saves re-run, hashes in `docs/RELEASE-1.3.1.md`. | 8c83a24 (1.3.0); 8c84616 (1.3.1) |
| — | Follow-up | Post-release cleanup: the statuette `turn_in` source (`data/cutoff_windows.json` and `tools/review_cutoffs.py`) is committed with the ledger it produces; `regen.py` hashes LF-normalized bytes and `goldens.json` records the eleven regenerated outputs; the temporary 14 MB `.next-phase-report/` evidence folder is gone; the README points at `docs/RELEASE-1.3.1.md`. The full chain was re-run and reproduced every shipped `data/*.json` byte for byte; `py tools/regen.py --check` reports all eleven outputs matching. | d8d3d92 |

---

## 12. Decision log

Record new decisions here. Do not silently change a locked decision.

| Date | Decision | Why |
|---|---|---|
| 2026-10-30 | Payload first; journal truth; completionist-first; next plan step only; card source model; Dijkstra is the Baron card; deck definition is not ownership. | The user's answers and the scripts. |
| 2026-10-30 | `view.todo` is computed in the backend as tracked + in-log + the first ahead, unlocked plan step; the UI no longer re-filters it. | Two filters were disagreeing; the payload must be the one definition. |
| 2026-10-30 | A tick on a file-derived step is a note for every journal state, including Not started; only manual rows use a tick as status. | The old code turned a Not started tick into the card Done while the matrix said unknown and the watch vanished. |
| 2026-10-30 | The NOW band carries no later-card count. Ahead windows live only in MORE > CARDS > LATER. | The band is the product; a count of things you cannot act on padded it. |
| 2026-10-30 | `goal_steps` has no guidance switch; only `instructions` are gated. | Turning guidance off deleted the plan, which is a reference surface, not a line. |
| 2026-10-30 | The fourth warning is built at runtime from `branches.json` facts named by reviewed targets, not by hand-editing generated `route.json`. | Payload-first and regenerable; the band names the quest and never the choice. |
| 2026-10-30 | The choice warning only fires on an `Active` quest. | A future choice is ledger data, not a decision the player can make now. |
| 2026-10-30 | Coverage marks any pack with `with_cards == 0` as `not modelled` with a reason. | A measured zero and an unmodelled pack are not the same claim. |
| 2026-10-30 | Release 1.3.0 after Phase 2 completed. | All phases green; 56 Rust tests, 13 checker mutation tests, three real saves, clean profile, packaged artifact. |
| 2026-10-30 | A deck definition is not ownership; 16 starter-deck basics are explicit unknown-source rows. | The `north` deck list is not a collection grant; the save's collection still decides owned. |
| 2026-10-30 | Dijkstra is one-time, not missable. | The office is a fallback, so a closed step cannot be called lost; one-time rows stay out of NOW. |
| 2026-10-30 | Turn-in wording is data-driven from `cutoffs.json` facts. | The watch names both/one/neither statuettes without hardcoding a step id in Rust. |
| 2026-10-30 | A missing or unreadable save returns `info` and no detail watch, never a live warning or a `safe` verdict. | An empty journal is not "every quest Not started"; the detail and search panes must not invent state. |

---

## 13. Mission prompt

The copy-paste version is in the chat. It is reproduced here for the record:

> You are the coding agent for the Witcher 3 Missables Tracker at `C:\Steam\steamapps\common\The Witcher 3\w3tracker`. Read `AGENTS.md`, `README.md`, `docs/DESIGN.md`, `docs/BACKEND_CONTRACT.md`, `docs/CARD-WINDOWS.md`, `docs/TARGET-SCHEMA.md`, `tools/README.md`, and `NEXT-PHASE-PLAN.md` completely before touching anything.
>
> Mission: execute `NEXT-PHASE-PLAN.md` end to end, Phases 0 through 5. Do not stop for check-ins, do not ask the user questions, and do not hand back a plan. Work until the Definition of Done is met or a hard blocker is documented.
>
> The user is unavailable. Make decisions from the locked decisions and defaults in the plan; record new decisions in the Decision Log. Do not ask the user to test, run commands, inspect saves, or verify the UI. Test everything yourself with `cargo test --locked`, the headless CLI on copied saves and a temporary `APPDATA`, JSON invariant checks, tick and card/statuette truth tables, DOM/UI checks, mutation tests, and the logs. If a native WebView cannot be automated, build a DOM harness or use the available browser/preview tools; record the limitation rather than offloading verification.
>
> A phase is complete only when its acceptance checks pass and the evidence is recorded. If a check fails, fix the cause; never skip, weaken, or suppress it. Do not stop after a phase; proceed to the next. If the turn is interrupted, read the progress log and resume; do not redo completed phases.
>
> Constraints: work only in `w3tracker/`; never launch the game; never write to the real saves or `%APPDATA%`; use copied saves and a temp profile; keep the app read-only and offline; do not touch `bin/`, `content/`, `mods/`, `cookedfinal.redscripts`, `_DLSS5_Backup/`, or the loader-hook names; do not add a network client; use `package.ps1` for packaging.
>
> Release: when all acceptance checks are green, bump `Cargo.toml`, `tauri.conf.json` and the README together, add `docs/RELEASE-x.y.z.md`, run `package.ps1`, verify the artifact, and commit locally. Do not push to a remote or upload to a store unless the repo has an explicit, authorized command and credentials. If signing/store credentials are missing, produce the unsigned build, document the exact remaining step, and continue.
>
> Hard blockers: missing game/REDkit files, unavailable saves, a missing toolchain, or release credentials. Document the exact command and complete every other phase. Do not stop the whole mission for one blocked step.
>
> Start now. Update the progress log as you go.
