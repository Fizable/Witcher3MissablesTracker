# Finish the Witcher 3 Missables Tracker — mission prompt

**Status:** durable prompt, 2026-10-28. This is the finish contract for the desktop tracker, not a
new milestone plan. It is written to be pasted into a fresh agent session from
`C:\Steam\steamapps\common\The Witcher 3\w3tracker`.

`docs/` is where this project already keeps its handoffs, plans and release contracts; that is why
this file lives here rather than at the repository root.

## Decisions this prompt was built from

These are the user's answers from the planning session. They are decisions, not open questions. If
the user changes one, revise this file before starting; do not silently substitute a different
outcome.

1. **Surface:** desktop tracker first. Finish the Windows app and its packaged executable. Do not
   build an in-game WitcherScript mod in this mission.
2. **What "100%" means:** one save/run with chosen outcomes, aiming at the maximum obtainable set of
   quests and cards for that run. Every exclusion is named and proven. This is not a claim that
   every mutually exclusive branch fits in one save.
3. **Chosen outcomes:** Ciri lives / witcher ending, Baron's wife is cured, Olgierd is saved in
   Hearts of Stone, and both Blood and Wine sisters live.
4. **Card evidence:** game files first. Where the files cannot prove a card-level missable window, a
   community-reviewed window is allowed only when it is visibly labelled as community evidence and
   carries a source and review date. It is never presented as gamefile truth.
5. **Done bar:** automated gates plus adversarial re-review. A green test run is the start of the
   re-review, not the finish. No "honest incomplete" handoff.
6. **Authoritative data:** the current game install at `C:\Steam\steamapps\common\The Witcher 3` and
   the current REDkit data at `F:\SteamLibrary\steamapps\common\The Witcher 3 REDkit\r4data`. Verify
   both paths exist before regenerating. If one is missing, ask for the exact replacement path.

## How to use this file

Paste everything from **Mission prompt** to the end of this file into a fresh agent session with the
project open. The preamble above is for the user and for judging the prompt; the mission prompt below
is self-contained and does not depend on the chat that produced it.

---

# Mission prompt

You are finishing the Witcher 3 Missables Tracker at
`C:\Steam\steamapps\common\The Witcher 3\w3tracker`.

Read first, in this order:

- `README.md`
- `docs/TARGET-SCHEMA.md`
- `docs/RELEASE-1.0.0.md`
- `docs/BACKEND_CONTRACT.md`
- `tools/README.md`

The three milestone files that used to be listed above (HANDOFF-1.1, PLAN-1.2-card-deadlines and
PLAN-1.0-completion) were retired on 2026-10-30, after their milestones shipped. This file is kept
as the record of the finish decisions the mission was built from, not as a live reading list; what
those milestones actually produced is recorded in `docs/RELEASE-1.0.0.md` through
`docs/RELEASE-1.2.2.md`.

Then verify every count in those documents against the current tree. The documents are evidence, not
authority. Several counts are stale, and `data/coverage.json` already disagrees with the prose about
DLC phase and scene coverage. Measure first. Do not build UI or write a plan on top of an unverified
count.

## 1. The user outcome — the only definition of done

Deliver the desktop tracker as a packaged Windows executable. Do not build an in-game WitcherScript
mod in this mission. The tracker must guide one save/run to completion for this fixed target set:

- Ciri lives / witcher ending (`ciri_witcher`)
- Baron's wife is cured (`baron_wife_cured`)
- Olgierd is saved, Hearts of Stone (`olgierd_saved`)
- Both Blood and Wine sisters live (`bw_both_sisters`)

"100%" means: for this chosen run, every one of the 414 route nodes (403 quests + 11 manual) is
classified as done, obtainable, at risk, lost, excluded or unknown with evidence; every one of the
224 Gwent cards (202 main + 22 leaders at baseline) is accounted for with ownership and, where
applicable, a missable window; and every warning appears while the window is still open. If the
loaded save is already past a window, the app must say `LOST IN THIS SAVE` only when the journal or
ownership proves it, and `unknown` otherwise; it must not pretend it warned in time. This does not
mean every mutually exclusive branch in one save, and it is never a single unqualified percentage.

The mission is complete only when all of the following are true:

1. The four targets are guided, not placeholders, with facts and guidance that resolve to game
   files. `baron_wife_cured` must no longer be `not_guided_yet`.
2. The run planner produces a route-ordered plan for those targets, detects conflicts, and never
   silently drops a target.
3. Every quest and card in the chosen run has a status and an evidence trail; no silent omissions.
4. Every missable quest and every obtainable card has a warning with a proven closing mechanism, or
   a visibly labelled community-reviewed window where game files cannot prove one.
5. The 11 baseline manual route steps are audited: each is replaced by a file-derived step or
   labelled `manual_reviewed`, and none is presented as gamefile-proven.
6. The packaged exe, run from its own `data/` folder, passes the same checks on real saves.
7. All gates in section 6 pass and two consecutive adversarial review passes find no new P0/P1
   defect.
8. The final report contains measured numbers, not promises.

Milestones 1.1 and 1.2 in the existing docs are internal slices. This mission is the whole product.
Do not hand back after the outcome matrix, after the planner, after the card candidate report, or
after any one workstream. There is no handoff milestone. A progress note is not a handoff; keep
working. The existing handoff prompts allow an "honest incomplete" report. This mission does not.
Incomplete is a status you keep working from, not a finish line. The finish line is the packaged app
with the full chosen-run guidance and card warnings.

## 2. Non-negotiable evidence rules

- **Tier A — gamefile-proven:** REDkit/journal/phase/scene/string database or the save itself. This
  is the only tier that may be called "gamefile-proven" or "100% correct".
- **Tier B — community-reviewed:** a named source (with URL where available), a review date, and a
  visible label in the UI. Allowed only to fill a gap the files cannot prove. Never mix it into
  Tier A, never hide the label, and never use it for a hard "lost" claim unless a save or file
  corroborates it.
- **Tier C — unknown:** shown as unknown, never guessed. A card with no source is "unknown source",
  not owned or not owned by inference.
- The old `../w3check/user_guide.md` route is Tier B/C and explicitly unverified. Fact-check every
  line; never treat it as authority.
- The frozen wiki-era JSON (`data/audit_*.json`, `data/guide_*.json`) must not be loaded; Tier B
  rows need their own reviewed source, not those files. No hard-coded save name, save path or card
  ownership; install paths are configuration. Generated files are regenerated, never hand-edited;
  reviewed decisions live in reviewed input files with sources, following the existing
  `data/endings.json`, `data/route_overrides.json`, `data/quest_sections.json`,
  `data/prereqs_review.json` and `data/cutoffs.json` convention.
- Preserve: read-only saves and game folder, journal-over-tick, the spoiler gate, no choice text in
  the default payload, and the existing `DO THIS NOW` / `MISSABLE` / `CUTOFF PASSED - CHECK NOW` /
  `LOST IN THIS SAVE` vocabulary.
- Do not print a single misleading completion percentage. Report done/obtainable/at-risk/lost/
  excluded/unknown counts, and name every exclusion. `max achievable` is not "100% of every branch".
- Do not skip, weaken, delete or xfail a check to make a gate pass. Do not update `goldens.json`,
  expected counts, checker thresholds or baselines merely to match an unverified output. Any such
  change needs a reviewed reason and must be reported.
- Do not remove a quest, card or warning from a matrix to make a count pass. Every removal needs
  file evidence and a named replacement or exclusion.
- Do not commit, push or publish unless the user asks. Leave changes in the working tree for review.

## 3. Baseline to verify before editing

- Version 1.0.0; 414 route nodes (403 quests + 11 manual); 2,286 branch rows on 141 quests; 224
  cards, 0 with a missable window; 2 ending targets, only `bw_both_sisters` guided; 0 exclusivity
  edges; no `data/outcomes.json`, no `src/outcomes.rs`, no `src/plan.rs`.
- `tools/fact_index.json` has 15,949 rows and 0 DLC sources, because `factgates.py` scans only the
  base quest root. Extend it to `ep1` and `bob`.
- `data/coverage.json` currently reports 18 Hearts of Stone phases/18 scenes and 53 Blood and Wine
  phases/31 scenes, while `PLAN-1.2` says 0/0. Re-measure and reconcile; do not trust either the
  prose or a stale generated file.
- The working tree is far ahead of the last commit. Do not reset, discard or overwrite existing
  work; record the baseline and build on it.
- Verify the `C:` game folder and `F:` REDkit path exist. If one is unavailable, ask for the exact
  path; do not silently fall back to stale data.
- Check the last commit and current branch before any consequential Git operation, but do not commit
  unless asked.

## 4. Work required

These are workstreams, not milestones. Do not stop after any one of them.

### 4.1 Baseline reconciliation and provenance audit

Before changing behaviour, produce a measured baseline table in the working notes:

- route node count and section counts;
- quest, phase, scene, branch and cutoff coverage per pack;
- card count, main/leader split, source coverage, missable count;
- target count, guided count, `not_guided_yet` count;
- exclusivity edge count;
- every `fact_index` source family, including the DLC zero;
- the 11 manual steps and the reviewed cutoffs, with their provenance.

Reconcile the stale prose in `PLAN-1.2` and `HANDOFF-1.1` with the generated files. State which
number is authoritative and why. This table is the baseline for every later gate.

### 4.2 Outcome model and run planner

- Extend the fact index to DLC phase files without overwriting base rows.
- Build `data/outcomes.json`: reviewed terminal outcomes for main-story Ciri, Baron family, Hearts
  of Stone Olgierd, and Blood and Wine sisters/duchy. Every outcome needs file evidence; phase-set
  outcomes use an exact journal objective or an explicit "no dialogue line" mechanism, never
  invented dialogue.
- Make `ciri_witcher`, `baron_wife_cured`, `olgierd_saved` and `bw_both_sisters` guided. A chosen
  target left `not_guided_yet` is a failure, not a finish.
- Guide `baron_wife_cured` from the `q105` phase facts. If there is no player-facing line, show the
  exact journal objective and say that no dialogue line is involved. Do not guess a line and do not
  leave the target unguided.
- Extend `endings.json` and its checker; keep the spoiler gate. Review exclusivity and ship only
  proven edges.
- Audit exclusivity candidates from failure blocks, reviewed cutoffs, `CDeactivateSpawnset`, and
  facts one phase sets while another tests. Record accepted edges and rejected candidates with
  evidence. **Do not leave `data/exclusive.json` empty by default.** An empty file is valid only
  with a candidate-audit report explaining why every candidate was rejected; even then, "all
  quests" is unproven/unknown, not 100%.
- Implement the one-run planner: route-ordered steps, ahead/settled/unreachable/blocked, conflict
  detection, coverage counts. Add `src/outcomes.rs` and `src/plan.rs` (or an equivalent module
  split) and the `get_outcomes`, `get_plan` and, if the run-set view is implemented, `get_runset`
  commands. Update `docs/BACKEND_CONTRACT.md` for the new payloads and the spoiler gate.
- If the files prove the four chosen targets cannot coexist in one save, do not silently switch to a
  run set. Stop and present the proven conflict and the minimum run set as a decision for the user.
  That is the only allowed substitution, and it needs evidence.

### 4.3 Quest completeness and the 11 manual steps

- Produce a quest matrix for the chosen run. Start from 414 route nodes; if the audit removes or
  adds a step, update the count in every gate, payload and report. A quest not in the matrix is a
  defect.
- Classify every node as done, obtainable, at risk, lost, excluded or unknown; every excluded quest
  names the mechanism.
- Audit all 11 manual steps in `data/route_overrides.json`. Each must be either:
  - replaced by a file-derived step, or
  - kept and labelled `provenance: manual_reviewed`, with the exact reason it cannot be derived, the
    source of the review, and a visible label in the matrix and UI.
  Do not count manual steps as Tier A. If a manual step is redundant, remove it and update the
  denominator; if it is kept, say why.
- Prove the four chosen outcomes can coexist in one save, or report the exact conflict with evidence.
- Keep warnings save-driven: `LOST` only when the journal/ownership proves it; `CUTOFF PASSED` is
  not lost; a tick never overrules the journal. Test both sides of each outcome and the known
  cutoffs.

### 4.4 Gwent cards — the central missing feature

- Produce a 224-row card matrix at baseline. If the measured count differs, reconcile it and update
  every gate and report before using a new denominator. Ownership from `SBCollectionCard` /
  `SBLeaderCollectionCard`, unknown when the save cannot show it; manual ticks only fill gaps.
- Build a card-window candidate report with gamefile evidence first: phase grant, journal failure,
  one-time source. Only a reviewed row with a step, a mechanism and an evidence tier may become
  `missable`.
- Zero `missable` rows today is a finding, not completion. If gamefile evidence yields zero card
  windows, build the reviewed community layer, label it, and continue until every obtainable card
  has a reviewed window or a proven reason none exists. A zero is acceptable only if the candidate
  report shows, for every card, why no deadline exists; a zero caused by missing evidence is a
  failure, not a completion.
- Tier B card rows require a named source (with URL where available), review date, a
  `tier: community` field, and a visible label in the UI. They must never be counted as Tier A or
  used for a hard `lost` claim without save/file corroboration.
- Surface windows in the card row and in `AT RISK NOW`; be silent once owned or passed; say lost
  only when proven. Keep the ledger separate from ownership.
- Coverage must reconcile: 196 base cards, 28 Blood and Wine, 0 Hearts of Stone (expected), 22
  leaders. If the measured counts differ, report the discrepancy and fix the data or the prose.
- Every card has a name and a source or an explicit `unknown source`. A card not in the matrix is a
  defect.

### 4.5 UI, warnings and package

- The default screen stays spoiler-free; labels and lines only after opt-in.
- `RUN`, `AT RISK NOW`, `DO NEXT`, `PROGRESS`, `GWENT CARDS`, `COVERAGE`, the goal picker, the
  outcome matrix and the run plan all work together.
- A quest or card warning must name the closing step and mechanism in the collapsed Technical
  details, not only in the headline.
- Package with `package.ps1` and verify the exe from `dist/` with its own `data/`: `--view`,
  `--detail`, `--cards`, `--targets`, and the new plan/outcome commands.

## 5. Route hypotheses to verify, not trust

`../w3check` is the older prototype, not the shipping app. Its `user_guide.md` is the user's pasted
route and is explicitly unverified. Treat it as a Tier B checklist of things to fact-check, not as
data:

- Ciri: snowball fight, Velen rather than Emhyr, Lodge alone, Avallac'h's lab, Skjall's grave.
- Baron: the Whispering Hillock outcome that cures his wife.
- Hearts of Stone: help Olgierd, solve the riddle, do not take the other finale path.
- Blood and Wine: buy the ribbon, exhaust Syanna's dialogue, read the playroom journal, choose
  mercy at the ceremony.

Every one of these needs a Tier A fact, exact journal objective, or explicit mechanism before it
ships. If a line cannot be extracted, do not invent it; use the exact objective and label the
mechanism.

## 6. Proof gates

Run and record the actual output. A gate is not passed because it is plausible; it is passed when the
command exits successfully and its counts are recorded.

```text
py tools/regen.py --check
py tools/contradictions.py
py tools/endings.py check --release
py tools/test_endings.py
py tools/outcomecheck.py            # new or equivalent
py tools/cardwindows.py check       # new or equivalent
cargo test
package.ps1 ...
```

Also verify, from the packaged exe and its own `data/`:

- early, mid and epilogue saves;
- both sides of each of the four targets;
- a save with a failed quest;
- a save with a missing card collection block;
- a corrupted save;
- a missed card and a passed card window;
- the default payload contains no target label, choice text or instruction;
- the guided payload contains only the selected target's exact line;
- a conflict is shown as a conflict, not silently resolved;
- no console errors and no horizontal overflow in the tested viewport;
- every Tier B row is visibly labelled and has a resolvable source and date;
- every Tier A row resolves to a file, locid or save;
- no generated file was hand-edited;
- no 100% completion percentage is printed in the app or final report; counts and named
  exclusions are the only completion statement;
- every card has a window classification: Tier A, Tier B, or a documented no-window reason; a zero
  `missable` count is accepted only when that report covers all 224 cards.

The gate must include a **provenance reconciliation**:

- every shipped outcome, quest warning and card window has a tier;
- every Tier B row has a source and review date;
- every manual step is labelled;
- every `unknown` is counted, not hidden;
- every exclusion names its mechanism.

## 7. Adversarial re-review loop (blocking)

When you believe you are done, switch roles. You are now a hostile reviewer trying to prove the
tracker wrong. This is a required part of the mission, not a nice-to-have.

- Re-derive 20 random quest claims and 20 random card claims from the files. Do not use the app's
  own data as evidence for itself.
- Try to find a save where a warning is shown after the loss, missing before the loss, or claims
  lost without proof.
- Inspect the packaged exe, not the checkout.
- Look for silent omissions: any quest or card not in the matrix, any 100% completion percentage,
  any count that hides unknown or excluded content, any unlabelled community claim, any manual step
  presented as gamefile truth.
- Check the stale-count problem: are the DLC coverage numbers, card counts, route counts and manual
  step count the same in the data, the checker, the payload, the README and the final report?
- Run the whole gate again. Fix every P0/P1.

Definitions for this review:

- **P0:** a false claim, data loss, crash, corrupted save, spoiler leak in the default payload, or a
  warning that is provably wrong.
- **P1:** a missing warning, a wrong status, an unlabelled Tier B row, a silent quest/card omission,
  a manual step counted as gamefile-proven, or a gate that passes without measuring.
- **P2:** presentation, wording, layout, or a non-blocking cleanup.

Repeat until two consecutive full adversarial passes produce no new P0/P1. A green test run is the
start of this loop, not the end of the work.

## 8. The only allowed stop conditions

If a gap is genuinely impossible, you may not call the mission complete. You must:

1. prove it with file/save evidence;
2. implement the most honest fallback (unknown or clearly labelled community evidence);
3. mark it in the UI;
4. list it in the final report;
5. continue all other work.

The existing docs say the planner is allowed to answer "no path with the current data". That is not
an exit here. If there is no path, prove it, implement the fallback, and continue.

Pause only for a decision that cannot be derived from the project. Ask one concrete question with
options, and stop only that workstream. A blocker question is not a completion report; state what
remains and continue after the answer. Do not stop because a slice is finished, a zero is honest, or
the remaining work is large. "Incomplete" is a status you keep working from, not a finish line.

The only two legitimate blockers are:

- a proven data impossibility: the files and saves cannot support the claim, and you have the
  evidence and the fallback implemented; or
- a user decision that changes the product, such as an incompatible target set or a missing
  authoritative data path.

Everything else is work.

## 9. Final report format

Do not replace this with a narrative. Use this shape so the result can be audited:

```text
Status: COMPLETE | BLOCKED (specific reason)
Chosen run: ciri_witcher + baron_wife_cured + olgierd_saved + bw_both_sisters
Compatibility: proven | conflict (evidence)

Quests: 414 classified (or the audited route count) - done N, obtainable N,
        at risk N, lost N, excluded N, unknown N
Cards: 224 accounted (or the audited count) - owned N, obtainable N,
       at risk N, lost N, excluded N, unknown N
Manual steps: 11 audited - replaced N, manual_reviewed N (each named; use the audited count)
Warnings: quest N, card N; Tier A N, Tier B N, Tier C N
Gates: each command + result
Packaged exe: path + payloads checked
Adversarial: passes N; open P0/P1 0
Remaining unknowns/exclusions: each with reason and evidence
Not tested: ...
```

The report must state the Tier A/Tier B/Tier C split explicitly. "100% correct" applies only to
Tier A. A reader must be able to tell whether the tracker is finished, what is still unknown, and
what evidence supports every warning without reading the source.

## 10. Final checklist

Before you claim completion, answer every line with evidence:

- [ ] All four chosen targets are guided; `baron_wife_cured` is not `not_guided_yet`.
- [ ] `data/outcomes.json` exists, validates, and covers Ciri, Baron, Olgierd and the sisters.
- [ ] The run planner produces a route-ordered plan and detects conflicts.
- [ ] `data/exclusive.json` has been audited; empty is allowed only with the rejection report.
- [ ] All 11 baseline manual steps are replaced or labelled `manual_reviewed`.
- [ ] The quest matrix covers the current route count, with every exclusion named.
- [ ] The card matrix covers the current card count (224 at baseline), with ownership and a window
      or a proven no-window reason.
- [ ] Every card has a window classification: a reviewed Tier A or Tier B window where one exists,
      or a documented no-window reason. A bare zero `missable` count is not proof.
- [ ] Every Tier B card row has a source, review date and visible community label.
- [ ] The packaged exe passes the same checks from its own `data/`.
- [ ] Two consecutive adversarial passes found no new P0/P1.
- [ ] The final report uses measured numbers and names every remaining unknown.

If any box is unchecked, the mission is not complete. If it is unchecked because of one of the two
proven blockers in section 8, report BLOCKED with the evidence; otherwise keep working.
