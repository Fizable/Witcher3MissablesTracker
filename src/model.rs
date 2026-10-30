//! Route model + engine. Port of route.py: needs (hard), PREFS (recommended order), EVENTS (cutoffs), DO NEXT / HOLD OFF / safety check.

use serde::Deserialize;
use serde_json::{json, Map, Value};
use std::collections::{HashMap, HashSet};

#[derive(Deserialize, Clone)]
pub struct Node {
    pub section: String,
    pub id: String,
    pub title: String,
    pub lv: String,
    pub files: Vec<String>,
    pub hard: Vec<String>,
    /// Some `hard` prerequisites are not "the other quest is finished" but "its story has reached
    /// the point that opens this step", and the game states that with a fact of its own. Keyed by
    /// prerequisite id: a prerequisite is satisfied when it reads done or one of its facts is set.
    /// Settled and re-checked by tools/prereqs.py (data/prereqs_review.json).
    #[serde(default)]
    pub hard_facts: HashMap<String, Vec<String>>,
    pub by: Vec<String>,
    pub note: String,
    pub kind: String,
    pub opt: bool,
    #[serde(default)]
    pub when: Vec<String>,
    /// `CJournalQuest.order`: a stable sort key, not a story sequence (see routegen).
    #[serde(default)]
    pub order: i64,
    /// The lowest-order phase description, first sentence, clipped. Same for every player.
    #[serde(default)]
    pub desc: String,
    /// A scene section of this quest sets a fact when the choice is taken: an outcome branch. A
    /// one-shot dialogue row is `dialogue_choice` and is never a branch. The choice text is never
    /// shown. Read from the scene's own fact-setting blocks by tools/questindex.py.
    #[serde(default)]
    pub branch: bool,
    /// A one-shot (`singleUseChoice`) dialogue row exists. Dialogue, not an outcome branch.
    #[serde(default)]
    pub dialogue_choice: bool,
    /// A reviewed ending target (data/endings.json) names a fact this quest's branch sets. Never
    /// inferred from a scene; false until a target is reviewed.
    #[serde(default)]
    pub ending_relevant: bool,
    /// The game files name a block that adds this quest's journal entry. False means the start is
    /// unknown, not unavailable.
    #[serde(default)]
    pub start_known: bool,
    /// `game_file` for a step read from a CJournalQuest, `manual_reviewed` for one of the 9 kept
    /// bookkeeping steps, `save_only` for a journal the route does not know. Only the first two can
    /// be in the audited matrix; a save-only row is shown separately and never counted as 100%.
    #[serde(default)]
    pub provenance: String,
    /// Why a manual step cannot be derived. Empty for game-file steps.
    #[serde(default)]
    pub review_reason: String,
    /// The reviewed document that kept this manual step.
    #[serde(default)]
    pub review_source: String,
    /// The review date, `YYYY-MM-DD`.
    #[serde(default)]
    pub reviewed: String,
}

#[derive(Deserialize, Clone)]
pub struct FlagDef {
    pub id: String,
    pub label: String,
    #[serde(default)]
    pub note: String,
}

#[derive(Deserialize, Clone)]
pub struct EventDef {
    pub name: String,
    pub fires: Vec<(String, Vec<String>)>,
    #[serde(default)]
    pub soft: bool,
}

#[derive(Deserialize, Clone)]
pub struct Pref {
    pub step: String,
    pub needs: Vec<String>,
    pub why: String,
}

#[derive(Clone)]
pub struct RouteData {
    pub sections: Vec<String>,
    pub nodes: Vec<Node>,
    pub events: Vec<(String, EventDef)>,
    pub prefs: Vec<Pref>,
    pub conditional: HashSet<String>,
    pub flags: Vec<FlagDef>,
    /// The reviewed 11-step audit: baseline 11, 9 kept and 2 replaced by file-derived journals.
    pub manual_audit: Value,
}

pub fn load_route(v: &Value) -> Result<RouteData, String> {
    let sections: Vec<String> = serde_json::from_value(v["sections"].clone()).map_err(|e| e.to_string())?;
    let nodes: Vec<Node> = serde_json::from_value(v["nodes"].clone()).map_err(|e| e.to_string())?;
    let prefs: Vec<Pref> = serde_json::from_value(v["prefs"].clone()).map_err(|e| e.to_string())?;
    let cond: Vec<String> = serde_json::from_value(v["conditional"].clone()).map_err(|e| e.to_string())?;
    let flags: Vec<FlagDef> = serde_json::from_value(v["flags"].clone()).unwrap_or_default();
    let manual_audit = v.get("manual_audit").cloned().unwrap_or(Value::Null);
    let mut events = Vec::new();
    let m: &Map<String, Value> = v["events"].as_object().ok_or("events missing")?;
    for (k, val) in m {
        events.push((k.clone(), serde_json::from_value::<EventDef>(val.clone()).map_err(|e| e.to_string())?));
    }
    Ok(RouteData { sections, nodes, events, prefs, conditional: cond.into_iter().collect(), flags, manual_audit })
}

pub struct Held {
    pub why: String,
    pub blockers: Vec<usize>,
}

pub struct Step {
    pub n: Node,
    pub status: String,
    /// The journal's own status with the user's ticks taken out. A tick that contradicts it is
    /// bookkeeping, not evidence: the card keeps the journal state and says the two disagree.
    pub journal: String,
    pub manual: bool,
    pub locked: Vec<usize>,
    pub held: Option<Held>,
    pub lost: bool,
    pub evs: Vec<usize>, // indices into Eval.events
    pub cond_unknown: bool,
    pub tick_disagrees: bool,
    pub frontier: &'static str,
}

/// The six-state vocabulary the matrix must use. `at_risk` is not a softer `lost`: a passed
/// cutoff whose journal has not failed the quest is a check, and an unproven save state is
/// `unknown`, never a guessed loss.
pub struct Classification {
    pub state: &'static str,
    pub reason: String,
    pub source: &'static str,
}

/// Read one matrix state from the journal/save evidence already on the step and its live warning.
///
/// Rules that matter to section 4.3:
/// - a manual tick is `done`, but its source stays `manual_reviewed`, never Tier A;
/// - a tick on a file-derived step never overrules the journal: an open journal is at risk, and a
///   missing completed entry is unknown, not done;
/// - `Failed` and a live missed/lost gate are lost; a passed cutoff with an open journal is at risk;
/// - an unresolved world-state condition is unknown, and a contradicted one is excluded with the
///   condition named.
/// - no activation block is still obtainable; `start_known` is not a gate.
pub fn classify(s: &Step, watch: &[Value], ticked: bool) -> Classification {
    let c = |state, reason: String, source| Classification { state, reason, source };
    if s.status == "N/A" {
        let conds: Vec<String> = s.n.when.iter().map(|x| x.to_string()).collect();
        let why = if conds.is_empty() {
            "the route marks this step as not applicable in this playthrough".to_string()
        } else {
            format!("the world state contradicts {}", conds.join(", "))
        };
        return c("excluded", format!("Excluded: {why}."), "world_state");
    }
    if s.status == "Failed" {
        return c("lost", "The save's own journal marks this quest Failed.".into(), "journal");
    }
    if matches!(s.status.as_str(), "Done" | "Assumed") {
        if s.manual {
            return c(
                "done",
                if ticked { "Manual step: you marked it done. This is a reviewed checklist row, not a gamefile claim.".into() }
                else { "Manual step: assumed from later progress in the save. This is a reviewed checklist row, not a gamefile claim.".into() },
                "manual_reviewed",
            );
        }
        if s.status == "Assumed" {
            return c("done", "Assumed from later progress in the save; the journal did not flip itself.".into(), "save");
        }
        return c("done", "The save's own journal marks this quest Done.".into(), "journal");
    }
    // A live warning is the only place a cutoff can prove more than the journal status does.
    for wanted in ["lost", "missed"] {
        if let Some(w) = watch.iter().find(|w| w.get("live").and_then(|x| x.as_str()) == Some(wanted)) {
            let line = w.get("headline").or_else(|| w.get("why")).and_then(|x| x.as_str()).unwrap_or("The save proves this step is lost.");
            let mech = w.get("mechanism").and_then(|x| x.as_str()).unwrap_or("journal");
            return c("lost", format!("{line} ({mech})"), "cutoff");
        }
    }
    for wanted in ["inside", "check", "passed", "open", "ahead"] {
        if let Some(w) = watch.iter().find(|w| w.get("live").and_then(|x| x.as_str()) == Some(wanted)) {
            let line = w.get("headline").or_else(|| w.get("why")).and_then(|x| x.as_str()).unwrap_or("A reviewed cutoff is still open.");
            let mech = w.get("mechanism").and_then(|x| x.as_str()).unwrap_or("cutoff");
            return c("at_risk", format!("{line} ({mech})"), "cutoff");
        }
    }
    if s.cond_unknown {
        let conds: Vec<String> = s.n.when.iter().map(|x| x.to_string()).collect();
        return c(
            "unknown",
            format!("The save does not answer {}; the step is shown as unknown, not guessed.", conds.join(", ")),
            "world_state",
        );
    }
    // A fired reviewed loss edge on a Not started quest is the old `lost` flag: the journal has not
    // proved a failure, so it is a check (the contract's `CUTOFF PASSED` is not lost).
    if s.lost {
        return c(
            "at_risk",
            "A reviewed cutoff has passed and the journal is still open; it is not proved lost.".into(),
            "cutoff",
        );
    }
    if s.manual {
        return c(
            "obtainable",
            "Kept manual step: the save cannot show it, so it stays obtainable until you tick it.".into(),
            "manual_reviewed",
        );
    }
    c(
        "obtainable",
        if s.n.start_known {
            "No reviewed cutoff is open, and the game files name a start block.".into()
        } else {
            "No activation block was found; treated as obtainable, not unavailable.".into()
        },
        "route",
    )
}

pub struct Ev {
    pub id: String,
    pub def: EventDef,
    pub fired: bool,
    pub open: Vec<usize>,
}

pub struct Eval {
    pub steps: Vec<Step>,
    pub byid: HashMap<String, usize>,
    pub events: Vec<Ev>,
    pub todo: Vec<usize>,
}

pub fn short(t: &str) -> &str {
    t.split(" (").next().unwrap_or(t)
}

fn node_status(n: &Node, state: &HashMap<String, String>, ticks: &HashSet<String>) -> String {
    if n.files.is_empty() {
        return if ticks.contains(&n.id) { "Done".into() } else { "Not started".into() };
    }
    let mut sts: Vec<String> = Vec::new();
    for f in &n.files {
        let alts: Vec<String> = f
            .split('|')
            .map(|x| {
                // A route file may name one journal objective (`quest#objective`). When the save has
                // no entry for that objective but the quest itself is finished, the quest status is
                // the truth: the objective can no longer be done and a completed quest cannot be
                // advertised as available. A failed objective still wins over a completed quest.
                let exact = state.get(x).cloned();
                let stem = x.split('#').next().and_then(|q| state.get(q)).cloned();
                match (exact, stem) {
                    (Some(e), _) if e == "Failed" => e,
                    (_, Some(s)) if s == "Done" => s,
                    (Some(e), _) => e,
                    (None, Some(s)) => s,
                    (None, None) => "Not started".into(),
                }
            })
            .collect();
        if alts.iter().any(|a| a == "Done") {
            sts.push("Done".into());
        } else {
            sts.push(alts[0].clone());
        }
    }
    let st = if sts.iter().any(|s| s == "Failed") {
        "Failed"
    } else if sts.iter().all(|s| s == "Done") {
        "Done"
    } else if sts.iter().all(|s| s == "Not started") {
        "Not started"
    } else {
        "Active"
    };
    // A tick is a note, never a status: the journal decides the card, the matrix and the warning.
    // Only a manual step (no journal file at all) is finished by its tick, in the branch above.
    let _ = ticks;
    st.into()
}

fn is_ok(s: &str) -> bool {
    s == "Done" || s == "Assumed" || s == "N/A"
}

/// a node does not exist in your game when one of its conditions contradicts a tag you set (unknown tags never exclude)
fn is_na(n: &Node, flags: &HashMap<String, String>) -> bool {
    n.when.iter().any(|c| match c.split_once('=') {
        Some((k, val)) => flags.get(k).map(|f| !f.is_empty() && f != val).unwrap_or(false),
        None => false,
    })
}

fn cond_unknown(n: &Node, flags: &HashMap<String, String>) -> bool {
    n.when.iter().any(|c| c.split_once('=').map(|(k, _)| flags.get(k).map(|f| f.is_empty()).unwrap_or(true)).unwrap_or(false))
}

/// Is a hard prerequisite satisfied?
///
/// The prerequisite's own journal status is the usual answer. Where the files showed the real rule is
/// "the prerequisite's story got as far as X" - and no save ever has this step under way without that
/// fact - the game's own fact answers instead, which is what the saves were objecting to: they hold
/// several of these steps under way while the prerequisite reads unfinished.
fn prereq_ok(n: &Node, h: &str, byid: &HashMap<String, usize>, steps: &[Step], facts: &HashSet<String>) -> bool {
    if let Some(&j) = byid.get(h) {
        if is_ok(&steps[j].status) {
            return true;
        }
    }
    n.hard_facts.get(h).map(|fs| fs.iter().any(|f| facts.contains(f))).unwrap_or(false)
}

pub fn evaluate(rd: &RouteData, state: &HashMap<String, String>, ticks: &HashSet<String>, flags: &HashMap<String, String>, facts: &HashSet<String>) -> Eval {
    let secrank: HashMap<&str, usize> = rd.sections.iter().enumerate().map(|(i, s)| (s.as_str(), i)).collect();
    let mut steps: Vec<Step> = rd
        .nodes
        .iter()
        .map(|n| {
            let journal = if n.files.is_empty() { "Not started".to_string() } else { node_status(n, state, &HashSet::new()) };
            // a `when` flag may exclude a quest the save has not reached; it may never overrule a
            // journal that proves the quest exists in this playthrough
            let status = if journal == "Not started" && is_na(n, flags) { "N/A".into() } else { node_status(n, state, ticks) };
            // Ticking a file-derived step records a note. The card, the matrix and the warning keep
            // the journal's answer; the disagreement is stated instead of being resolved either way.
            let tick_disagrees = !n.files.is_empty()
                && ticks.contains(&n.id)
                && !matches!(journal.as_str(), "Done" | "Failed");
            let cond_unknown = journal == "Not started" && cond_unknown(n, flags);
            Step { n: n.clone(), status, journal, manual: n.files.is_empty(), locked: vec![], held: None,
                   lost: false, evs: vec![], cond_unknown, tick_disagrees,
                   frontier: "available" }
        })
        .collect();
    let byid: HashMap<String, usize> = steps.iter().enumerate().map(|(i, s)| (s.n.id.clone(), i)).collect();

    // manual steps you have clearly moved past (a later step in a later region is Done)
    for i in 0..steps.len() {
        if steps[i].manual && steps[i].status == "Not started" && !steps[i].n.opt {
            let r = secrank[steps[i].n.section.as_str()];
            let moved = steps[i + 1..].iter().any(|l| {
                l.status == "Done" && secrank[l.n.section.as_str()] > r && !l.manual && l.n.kind != "gwent" && l.n.kind != "treasure"
            });
            if moved {
                steps[i].status = "Assumed".into();
            }
        }
    }
    // a hard requirement is clearly done when something it gates has engaged (the game would not have allowed
    // that otherwise) - catches journal entries that never flip to Done even once the quest is over, by letting
    // real progress on what comes after it prove it happened. Runs to a fixpoint for multi-step chains.
    loop {
        let mut to_assume: Vec<usize> = Vec::new();
        for i in 0..steps.len() {
            if is_ok(&steps[i].status) || steps[i].status == "Failed" || steps[i].status == "N/A" {
                continue;
            }
            // gwent/treasure dependents are excluded: their own "Active" is often just as unreliable a journal
            // placeholder as the thing we are trying to prove here, not real evidence of story progress
            // a fact-gated dependent does not prove this step happened: its story can reach that
            // point with this step still unfinished, which is exactly what the saves show
            let dependent_engaged = steps
                .iter()
                .any(|s| s.n.hard.iter().any(|h| h == &steps[i].n.id && !s.n.hard_facts.contains_key(h)) && matches!(s.status.as_str(), "Active" | "Done" | "Assumed") && s.n.kind != "gwent" && s.n.kind != "treasure");
            if dependent_engaged {
                to_assume.push(i);
            }
        }
        if to_assume.is_empty() {
            break;
        }
        for i in to_assume {
            steps[i].status = "Assumed".into();
        }
    }
    // hard needs (game rules)
    for i in 0..steps.len() {
        let engaged = matches!(steps[i].status.as_str(), "Active" | "Done" | "Assumed");
        let unlocked = steps[i].n.hard.iter().all(|h| prereq_ok(&steps[i].n, h, &byid, &steps, facts));
        let locked: Vec<usize> = if engaged || unlocked {
            vec![]
        } else {
            steps[i]
                .n
                .hard
                .iter()
                .filter(|h| !prereq_ok(&steps[i].n, h, &byid, &steps, facts))
                .filter_map(|h| byid.get(h).copied())
                .collect()
        };
        steps[i].locked = locked;
    }
    // recommended order
    for p in &rd.prefs {
        if let Some(&i) = byid.get(&p.step) {
            let blockers: Vec<usize> = p.needs.iter().filter_map(|h| byid.get(h).copied()).filter(|&j| !is_ok(&steps[j].status)).collect();
            if matches!(steps[i].status.as_str(), "Active" | "Not started") && !blockers.is_empty() && steps[i].locked.is_empty() {
                steps[i].held = Some(Held { why: p.why.clone(), blockers });
            }
        }
    }
    // frontier: what the save says about this step, and what the files positively name about its gate
    for s in steps.iter_mut() {
        s.frontier = if is_ok(&s.status) {
            "done"
        } else if matches!(s.journal.as_str(), "Active" | "Failed") || matches!(s.status.as_str(), "Active" | "Failed") {
            "in_log"
        } else if !s.locked.is_empty() {
            "gated"
        } else if s.manual || s.n.start_known {
            "available"
        } else {
            "unknown"
        };
    }
    // events: one per reviewed loss edge. The top section reads them against this save.
    let mut events: Vec<Ev> = Vec::new();
    for (eid, def) in &rd.events {
        let fired = def.fires.iter().any(|(r, sts)| state.get(r).map(|s| sts.contains(s)).unwrap_or(false));
        let open: Vec<usize> = (0..steps.len()).filter(|&i| steps[i].n.by.contains(eid) && matches!(steps[i].status.as_str(), "Active" | "Not started")).collect();
        events.push(Ev { id: eid.clone(), def: def.clone(), fired, open });
    }
    let eidx: HashMap<&str, usize> = events.iter().enumerate().map(|(i, e)| (e.id.as_str(), i)).collect();
    for s in steps.iter_mut() {
        s.evs = s.n.by.iter().filter_map(|b| eidx.get(b.as_str()).copied()).collect();
        s.lost = s.status == "Not started" && s.evs.iter().any(|&k| events[k].fired && !events[k].def.soft);
    }
    let todo: Vec<usize> = (0..steps.len())
        .filter(|&i| {
            let s = &steps[i];
            !s.n.opt && matches!(s.status.as_str(), "Active" | "Not started") && !s.lost && s.locked.is_empty() && s.held.is_none()
        })
        .collect();
    Eval { steps, byid, events, todo }
}

pub struct Verdict {
    pub verdict: &'static str,
    pub headline: String,
    pub details: Vec<String>,
}

pub fn check_quest(rd: &RouteData, ev: &Eval, short_name: &str, state: &HashMap<String, String>) -> Verdict {
    let v = |verdict, headline: &str, details: Vec<String>| Verdict { verdict, headline: headline.to_string(), details };
    let nodes: Vec<usize> = (0..ev.steps.len())
        .filter(|&i| ev.steps[i].n.files.iter().any(|f| f.split('#').next() == Some(short_name) || f.split('|').any(|x| x == short_name)))
        .collect();
    if state.get(short_name).map(|s| s == "Done").unwrap_or(false) {
        return v("info", "Already done", vec![]);
    }
    if let Some(&i) = nodes.first() {
        if ev.steps[i].status == "N/A" {
            return v("info", "Does not apply to your game", vec![format!("It only exists when: {} (from your My game settings).", ev.steps[i].n.when.join(", "))]);
        }
    }
    for e in &ev.events {
        if e.def.fires.iter().any(|(r, _)| r.split('#').next() == Some(short_name)) && !e.fired && !e.open.is_empty() {
            let names: Vec<&str> = e.open.iter().take(8).map(|&d| short(&ev.steps[d].n.title)).collect();
            return v("stop", &format!("Not yet: this triggers \"{}\"", e.def.name), vec![format!("It would fail or lock: {}", names.join("; ")), "Finish those first.".into()]);
        }
    }
    if let Some(&i) = nodes.first() {
        let d = &ev.steps[i];
        if d.status == "N/A" {
            return v("info", "Does not apply to your game", vec![format!("It only exists when: {} (from your My game settings).", d.n.when.join(", "))]);
        }
        if d.lost {
            let fired: Vec<&str> = d.evs.iter().filter(|&&k| ev.events[k].fired).map(|&k| ev.events[k].def.name.as_str()).collect();
            return v("info", "Probably lost already", vec![format!("Cutoff that has happened: {}", fired.join("; "))]);
        }
        if d.status == "Failed" {
            return v("info", "Failed in your quest log", vec![]);
        }
        if !d.locked.is_empty() {
            let names: Vec<&str> = d.locked.iter().take(4).map(|&x| short(&ev.steps[x].n.title)).collect();
            return v("info", "Not available yet", vec![format!("The game does not offer it until: {}", names.join("; "))]);
        }
        if let Some(h) = &d.held {
            let names: Vec<&str> = h.blockers.iter().take(3).map(|&x| short(&ev.steps[x].n.title)).collect();
            return v("warn", "Recommended to wait", vec![h.why.clone(), format!("Do first: {}", names.join("; "))]);
        }
        let cut: Vec<&str> = d.evs.iter().filter(|&&k| !ev.events[k].fired).map(|&k| ev.events[k].def.name.as_str()).collect();
        let det: Vec<String> = if d.n.note.is_empty() { vec![] } else { vec![d.n.note.clone()] };
        if !cut.is_empty() {
            let c: Vec<&str> = cut.into_iter().take(3).collect();
            return v("warn", &format!("Safe to do now. It is lost at: {}", c.join("; ")), det);
        }
        return v("safe", "Safe: no cutoff is known for it", det);
    }
    let _ = rd;
    let b = short_name.as_bytes();
    if b.len() >= 4 && b[0] == b'q' && b[1..4].iter().all(|c| c.is_ascii_digit()) {
        return v("warn", "Main story quest: I have no data on what it closes", vec!["Finish your DO NEXT items first if you are unsure.".into()]);
    }
    v("safe", "Safe: not tied to any story cutoff I know of", vec!["Only cutoffs in the route data are checked.".into()])
}

// ------------------------------------------------------------------ JSON views for the UI

/// DO NEXT order. The route order is not story order; this is the only place that decides what to
/// look at first.
///
/// 1. the quest tracked in the game, 2. quests already in the log, 3. available quests, 4. available
/// quests that carry a live cutoff (the caution chip). Gated, done, lost and unsafe steps never
/// appear. Inside a group: nearest deadline (a live cutoff), then lowest suggested level, then the
/// journal's own `order` as a tie-break. Gwent and treasure steps are section-only unless they are
/// tracked or carry a cutoff.
pub fn todo_order(ev: &Eval, tracked: Option<&str>, unsafe_ids: &HashSet<usize>, caution: &HashSet<usize>, next_plan: Option<&str>) -> Vec<usize> {
    let mut out: Vec<usize> = ev
        .todo
        .iter()
        .copied()
        .filter(|&i| !unsafe_ids.contains(&i))
        .filter(|&i| {
            let s = &ev.steps[i];
            let is_tracked = tracked.map(|t| tracks(&s.n, t)).unwrap_or(false);
            // UP NEXT is the play queue: what the save says is live, plus the one plan step that
            // is next. A merely unlocked quest lives in MORE > PROGRESS.
            is_tracked || s.frontier == "in_log" || next_plan == Some(s.n.id.as_str())
        })
        .collect();
    out.sort_by_key(|&i| {
        let s = &ev.steps[i];
        let is_tracked = tracked.map(|t| tracks(&s.n, t)).unwrap_or(false);
        let group = if is_tracked {
            0
        } else if s.frontier == "in_log" {
            1
        } else {
            2
        };
        let deadline = if caution.contains(&i) { 0 } else { 1 };
        let level = s.n.lv.trim().parse::<i64>().ok();
        (group, deadline, level.is_none(), level.unwrap_or(0), s.n.order, i)
    });
    out
}

fn r(ev: &Eval, i: usize) -> Value {
    json!({"id": ev.steps[i].n.id, "title": short(&ev.steps[i].n.title), "manual": ev.steps[i].manual})
}

/// The spoiler-free chips on a mission card. Each one names the file fact behind it; none of them
/// contains a choice's text or a recommended option.
fn tags_of(s: &Step, _goal: bool) -> Vec<Value> {
    let mut out = Vec::new();
    if s.n.ending_relevant {
        out.push(json!({"id": "ending_choice", "label": "ENDING CHOICE"}));
    } else if s.n.branch {
        out.push(json!({"id": "branch", "label": "CHOICE"}));
    }
    if s.n.kind == "gwent" || s.n.section == "Gwent" {
        out.push(json!({"id": "gwent", "label": "Gwent"}));
    }
    if !s.n.by.is_empty() {
        out.push(json!({"id": "missable", "label": "missable"}));
    }
    if s.tick_disagrees {
        out.push(json!({"id": "tick", "label": "tick disagrees"}));
    }
    out
}

pub fn step_json(rd: &RouteData, ev: &Eval, i: usize) -> Value {
    step_json_goal(rd, ev, i, false)
}

/// The same step, with the `GOAL` state attached. `goal` is not a tag: the card renders it in
/// preference to `ENDING CHOICE` or `CHOICE`, and the backend keeps the three concepts separate.
pub fn step_json_goal(_rd: &RouteData, ev: &Eval, i: usize, goal: bool) -> Value {
    let s = &ev.steps[i];
    json!({
        "id": s.n.id, "title": s.n.title, "section": s.n.section, "lv": s.n.lv, "status": s.status,
        "journal": s.journal, "frontier": s.frontier, "manual": s.manual, "opt": s.n.opt,
        "kind": s.n.kind, "desc": s.n.desc, "branch": s.n.branch,
        "dialogue_choice": s.n.dialogue_choice, "ending_relevant": s.n.ending_relevant,
        "provenance": s.n.provenance, "review_reason": s.n.review_reason,
        "review_source": s.n.review_source, "reviewed": s.n.reviewed,
        "goal": goal, "order": s.n.order,
        "start_known": s.n.start_known, "tick_disagrees": s.tick_disagrees,
        "conditional": s.cond_unknown || _rd.conditional.contains(&s.n.id),
        "locked": s.locked.iter().map(|&x| r(ev, x)).collect::<Vec<_>>(),
        "held": s.held.as_ref().map(|h| json!({"why": h.why, "blockers": h.blockers.iter().map(|&x| r(ev, x)).collect::<Vec<_>>()})),
        "lost": s.lost,
        "tags": tags_of(s, goal),
    })
}

// ------------------------------------------------------------------ a warning read against the loaded save

/// Journal status of a quest stem: its own entry when the save carries one, else folded from its objectives.
pub fn quest_status(state: &HashMap<String, String>, q: &str) -> Option<String> {
    let q = q.to_ascii_lowercase();
    if let Some(s) = state.get(&q) {
        return Some(s.clone());
    }
    let pre = format!("{q}#");
    let (mut any, mut done, mut failed, mut active) = (false, false, false, false);
    for (k, v) in state {
        if !k.starts_with(&pre) {
            continue;
        }
        any = true;
        match v.as_str() {
            "Done" => done = true,
            "Failed" => failed = true,
            "Inactive" | "Not started" => {}
            _ => active = true,
        }
    }
    if !any {
        return None;
    }
    Some(if done { "Done" } else if failed { "Failed" } else if active { "Active" } else { "Not started" }.to_string())
}

/// a list of quest stems under `key`, whether the data wrote it as a list or as the single stem it usually is
fn qlist(v: &Value, key: &str) -> Vec<String> {
    match v.get(key) {
        Some(Value::String(s)) => vec![s.to_ascii_lowercase()],
        Some(Value::Array(a)) => a.iter().filter_map(|x| x.as_str()).map(|s| s.to_ascii_lowercase()).collect(),
        _ => Vec::new(),
    }
}

/// the titles that go with a list of quest stems, in the same order (the stem itself when a title is missing)
fn titles_of(v: &Value, key: &str, ids: &[String]) -> Vec<String> {
    let t: Vec<String> = v.get(key).and_then(|x| x.as_array()).into_iter().flatten().filter_map(|x| x.as_str().map(String::from)).collect();
    ids.iter().enumerate().map(|(i, q)| t.get(i).cloned().unwrap_or_else(|| q.clone())).collect()
}

/// "done: Pyres of Novigrad; in your log: Now or Never" - what the save says about these quests right now
fn status_phrase(state: &HashMap<String, String>, done_q: &HashSet<String>, ticked_q: &HashSet<String>, ids: &[String], names: &[String]) -> String {
    let mut order: Vec<&str> = Vec::new();
    let mut groups: HashMap<&str, Vec<String>> = HashMap::new();
    for (i, q) in ids.iter().enumerate() {
        let s = match live_status(state, done_q, ticked_q, q).as_deref() {
            Some("Done") => "done",
            Some("Failed") => "failed",
            Some("Active") => "in your log",
            Some(_) => "not started",
            None => "not in your log",
        };
        if !groups.contains_key(s) {
            order.push(s);
        }
        groups.entry(s).or_default().push(names.get(i).cloned().unwrap_or_else(|| q.clone()));
    }
    order.iter().map(|s| format!("{s}: {}", groups[s].join(", "))).collect::<Vec<_>>().join("; ")
}

/// A steps's journal-only status: what the save says, with your own ticks taken out of it.
pub fn journal_status(n: &Node, state: &HashMap<String, String>) -> String {
    node_status(n, state, &HashSet::new())
}

/// as `quest_status`, but a step the route already counts as finished answers for the quests it tracks.
///
/// A tick never outranks the journal. Ticking a step records what the save cannot show - a visit, a tutorial -
/// so it fills a gap, but when the journal still carries the quest as under way the tick is not evidence that it
/// is done, and the cutoff behind it still stands. 0.1.8 let a tick on the statuettes hide the fact that Triss
/// had already left, which is the one thing the warning existed to say.
fn live_status(state: &HashMap<String, String>, done_q: &HashSet<String>, ticked_q: &HashSet<String>, q: &str) -> Option<String> {
    let key = q.to_ascii_lowercase();
    let journal = quest_status(state, &key);
    if ticked_q.contains(&key) && journal.as_deref() == Some("Active") {
        return journal;
    }
    if done_q.contains(&key) {
        return Some("Done".into());
    }
    journal
}

/// "You ticked X done, but the journal still has it open - the journal wins here."
///
/// Shown beside a warning whose quests are both ticked and still open, so the disagreement is stated instead of
/// being silently resolved either way.
fn tick_note(state: &HashMap<String, String>, ticked_q: &HashSet<String>, ids: &[String], names: &[String]) -> Option<String> {
    let mut hit: Vec<&str> = Vec::new();
    for (i, q) in ids.iter().enumerate() {
        let key = q.to_ascii_lowercase();
        if ticked_q.contains(&key) && quest_status(state, &key).as_deref() == Some("Active") {
            hit.push(names.get(i).map(String::as_str).unwrap_or(q));
        }
    }
    if hit.is_empty() {
        return None;
    }
    let them = if hit.len() == 1 { "it" } else { "them" };
    Some(format!("You ticked {} done, but the journal still has {them} open - the journal wins here.", hit.join(", ")))
}

fn put(v: &mut Value, key: &str, val: Value) {
    if let Value::Object(m) = v {
        m.insert(key.to_string(), val);
    }
}

/// A short, readable list for a sentence: "A", "A and B", "A, B and 2 more".
fn join_titles(items: &[String]) -> String {
    match items {
        [] => String::new(),
        [one] => one.clone(),
        [one, two] => format!("{one} and {two}"),
        [one, two, ..] => format!("{one}, {two} and {} more", items.len() - 2),
    }
}

/// Read one cutoff warning against the loaded save.
///
/// The shipped warning was written once, when the files were read, and names the earliest quest on the
/// route that switches the resource off. Only the save knows whether that is still ahead of you, already
/// behind you, or the quest you are inside right now, so the sentence is rebuilt here rather than shown
/// as advice that may be years out of date. Returns false when there is nothing left to warn about.
/// Test-only entry point: a cutoff read without the save's facts.
#[cfg(test)]
pub fn live_cutoff(item: &mut Value, state: &HashMap<String, String>, done_q: &HashSet<String>, ticked_q: &HashSet<String>) -> bool {
    live_cutoff_facts(item, state, done_q, ticked_q, &HashSet::new())
}

/// A window can open later than its journal phase: the turn-in dialogue is the game's own graph,
/// and Triss tests `q310_philippa_rescued` before she will discuss the statuettes, however long
/// Final Preparations has been running. An unmet opening gate is a note, never a "do this now".
fn window_not_yet(item: &mut Value, facts: &HashSet<String>, saved: &str) -> bool {
    let Some(list) = item.get("opens_at").and_then(|x| x.as_array()).filter(|a| !a.is_empty()) else {
        return false;
    };
    if list.iter().filter_map(|x| x.as_str()).all(|f| facts.contains(f)) {
        return false;
    }
    put(item, "live", json!("not_yet"));
    put(item, "level", json!("info"));
    put(item, "tag", json!("WINDOW NOT OPEN YET"));
    if let Some(h) = item.get("not_yet_headline").and_then(|x| x.as_str()) {
        put(item, "headline", json!(h));
    }
    if let Some(a) = item.get("not_yet_action").and_then(|x| x.as_str()) {
        put(item, "action", json!(a));
    }
    put(item, "live_note", json!(saved));
    true
}

pub fn live_cutoff_facts(item: &mut Value, state: &HashMap<String, String>, done_q: &HashSet<String>, ticked_q: &HashSet<String>, facts: &HashSet<String>) -> bool {
    let affected = qlist(item, "affected");
    let closed = qlist(item, "closed_by");
    if affected.is_empty() || closed.is_empty() {
        return true;
    }
    // A window names the exact journal phase that ends the quest; a community cutoff names the quests
    // that switch the actor off. The save records both, so read the precise one when it is present.
    let at = item.get("closes_at").and_then(|x| x.as_str()).filter(|s| !s.is_empty()).map(String::from);
    let prot = titles_of(item, "affected_titles", &affected);
    let mut close = titles_of(item, "closed_by_titles", &closed);
    if at.is_some() {
        if let Some(t) = item.get("closes_at_title").and_then(|x| x.as_str()).filter(|s| !s.is_empty()) {
            close = vec![t.to_string()];
        }
    }
    let mut open: Vec<String> = Vec::new();
    let mut lost: Vec<String> = Vec::new();
    for (i, a) in affected.iter().enumerate() {
        match live_status(state, done_q, ticked_q, a).as_deref() {
            Some("Done") => {}
            Some("Failed") => lost.push(prot[i].clone()),
            _ => open.push(prot[i].clone()),
        }
    }
    if open.is_empty() && lost.is_empty() {
        return false; // you finished what it protects: there is nothing to warn about any more
    }
    let mut done: Vec<usize> = Vec::new();
    let mut running: Vec<usize> = Vec::new();
    if let Some(at) = &at {
        match live_status(state, done_q, ticked_q, at).as_deref() {
            Some("Done") | Some("Failed") => done.push(0),
            Some("Active") => running.push(0),
            // an older save may not carry the phase entry yet; fall back to the quest's own status
            _ => match live_status(state, done_q, ticked_q, &closed[0]).as_deref() {
                Some("Done") | Some("Failed") => done.push(0),
                Some("Active") => running.push(0),
                _ => {}
            },
        }
    } else {
        for (i, c) in closed.iter().enumerate() {
            match live_status(state, done_q, ticked_q, c).as_deref() {
                Some("Done") | Some("Failed") => done.push(i),
                Some("Active") => running.push(i),
                _ => {}
            }
        }
    }
    let mut saved = if let Some(at) = &at {
        format!("In this save: {}.", status_phrase(state, done_q, ticked_q, &[at.clone()], &close))
    } else {
        format!("In this save: {}.", status_phrase(state, done_q, ticked_q, &closed, &close))
    };
    // a tick that contradicts the journal is named rather than obeyed: the warning stands, and the card says why
    let mut named = affected.clone();
    named.extend(closed.iter().cloned());
    if let Some(at) = &at {
        named.push(at.clone());
    }
    let mut name_list = prot.clone();
    name_list.extend(close.iter().cloned());
    if let Some(n) = tick_note(state, ticked_q, &named, &name_list) {
        saved.push(' ');
        saved.push_str(&n);
    }
    // An availability window is not a journal failure: when it closes the chance to act is gone
    // until the next window, and the quest stays Active. Triss leaving Novigrad is that shape.
    if item.get("mechanism").and_then(|x| x.as_str()) == Some("availability") {
        if !lost.is_empty() {
            return false;
        }
        if done.iter().chain(running.iter()).next().is_some() {
            let gap = item
                .get("gap_headline")
                .and_then(|x| x.as_str())
                .unwrap_or("The next chance to hand them in comes later in the story.")
                .to_string();
            let gap_action = item
                .get("gap_action")
                .and_then(|x| x.as_str())
                .map(String::from);
            put(item, "live", json!("later"));
            put(item, "level", json!("info"));
            put(item, "tag", json!("WINDOW CLOSED - NEXT CHANCE LATER"));
            put(item, "headline", json!(gap));
            if let Some(a) = gap_action {
                put(item, "action", json!(a));
            }
            put(item, "live_note", json!(saved));
            return true;
        }
        if window_not_yet(item, facts, &saved) {
            return true;
        }
        put(item, "live", json!("open"));
        put(item, "level", json!("stop"));
        put(item, "tag", json!("DO THIS NOW"));
        put(item, "live_note", json!(saved));
        return true;
    }
    if !lost.is_empty() {
        put(item, "live", json!("lost"));
        put(item, "level", json!("lost"));
        put(item, "tag", json!("LOST IN THIS SAVE"));
        let them = if lost.len() == 1 { "it" } else { "them" };
        put(item, "headline", json!(format!(
            "{} can no longer be completed: the journal marks {them} failed.",
            join_titles(&lost)
        )));
        put(item, "live_note", json!(saved));
        return true;
    }
    if !done.is_empty() {
        // The cutoff has fired, but the journal has not failed the quest. That is a disagreement,
        // not a licence to tell the player it is gone: only the journal may say "failed".
        put(item, "live", json!("check"));
        put(item, "level", json!("stop"));
        put(item, "tag", json!("CUTOFF PASSED - CHECK NOW"));
        let what = join_titles(&open);
        let them = if open.len() == 1 { "it" } else { "them" };
        let closer = close.first().cloned().unwrap_or_default();
        put(item, "headline", json!(format!(
            "{what}: the cutoff has passed - {closer} is done, and your journal still has {them} open. Finish now if the game still allows it."
        )));
        put(item, "live_note", json!(saved));
        return true;
    }
    if !running.is_empty() {
        if window_not_yet(item, facts, &saved) {
            return true;
        }
        put(item, "live", json!("inside"));
        put(item, "level", json!("stop"));
        put(item, "tag", json!("DO THIS NOW"));
        let them = if open.len() == 1 { "it" } else { "them" };
        if at.is_some() {
            let inside = item.get("closed_by_titles").and_then(|x| x.as_array())
                .and_then(|a| a.first()).and_then(|x| x.as_str()).unwrap_or("this quest");
            // A window is already open here: naming the point that will end it again would read as
            // "you are inside it, finish before it starts". Say what is true - act now, if the
            // game still allows it - and let the journal decide whether it is already lost.
            put(item, "headline", json!(format!(
                "You are inside {inside}. Finish {them} now if the game still allows it."
            )));
        } else {
            let running_titles: Vec<String> = running.iter().map(|&i| close[i].clone()).collect();
            put(item, "headline", json!(format!(
                "You are inside {}. Finishing it closes {} partway through, so finish {them} first.",
                join_titles(&running_titles),
                join_titles(&open)
            )));
        }
        put(item, "live_note", json!(saved));
        return true;
    }
    put(item, "live", json!("ahead"));
    put(item, "tag", json!("CUTOFF AHEAD - GAME FILES + YOUR SAVES"));
    if at.is_some() {
        put(item, "headline", json!(format!(
            "Finish {} before {}.",
            join_titles(&open),
            close.first().cloned().unwrap_or_default()
        )));
    }
    put(item, "live_note", json!(saved));
    true
}

/// Read a start gate ("do X before Y ends, or Z is never offered") against the save.
pub fn live_gate(item: &mut Value, state: &HashMap<String, String>, titles: &HashMap<String, String>, done_q: &HashSet<String>, ticked_q: &HashSet<String>) -> bool {
    let check = item
        .get("checks")
        .and_then(|v| v.as_array())
        .and_then(|a| a.iter().find(|c| c.get("kind").and_then(|k| k.as_str()) == Some("implies_done")))
        .cloned();
    let Some(check) = check else { return true };
    let gated = qlist(&check, "if_present");
    let needs = qlist(&check, "then_done");
    if gated.is_empty() || needs.is_empty() {
        return true;
    }
    let name = |q: &String| titles.get(q).cloned().unwrap_or_else(|| q.clone());
    let gnames: Vec<String> = gated.iter().map(name).collect();
    let nnames: Vec<String> = needs.iter().map(name).collect();
    let saved = format!("In this save: {}.", status_phrase(state, done_q, ticked_q, &gated, &gnames));
    // "in the log" is Active, Done or Failed: a quest the save only carries as not started has not
    // been offered yet, and the gate is still ahead of you
    if gated.iter().any(|q| matches!(live_status(state, done_q, ticked_q, q).as_deref(), Some("Active") | Some("Done") | Some("Failed"))) {
        put(item, "live", json!("settled"));
        put(item, "level", json!("info"));
        put(item, "tag", json!("ALREADY SETTLED IN THIS SAVE"));
        put(item, "headline", json!("Settled: the gate this note warns about has already been passed in your game."));
        put(item, "live_note", json!(saved));
        return true;
    }
    let mut finished: Vec<String> = Vec::new();
    let mut remaining: Vec<String> = Vec::new();
    for (i, q) in needs.iter().enumerate() {
        match live_status(state, done_q, ticked_q, q).as_deref() {
            Some("Done") | Some("Failed") => finished.push(nnames[i].clone()),
            _ => remaining.push(nnames[i].clone()),
        }
    }
    if remaining.is_empty() {
        put(item, "live", json!("missed"));
        put(item, "level", json!("lost"));
        put(item, "tag", json!("MISSED IN THIS SAVE"));
        put(item, "headline", json!(format!("Missed: {} {} done and {} never entered your log, so that branch was not taken.", finished.join(", "), if finished.len() == 1 { "is" } else { "are" }, gnames.join(", "))));
        put(item, "live_note", json!(format!("In this save: {}.", status_phrase(state, done_q, ticked_q, &needs, &nnames))));
        return true;
    }
    put(item, "live", json!("ahead"));
    put(item, "tag", json!("GATE AHEAD - GAME FILES + YOUR SAVES"));
    put(item, "live_note", json!(format!("In this save: {}.", status_phrase(state, done_q, ticked_q, &needs, &nnames))));
    true
}

/// A note that refutes a guide claim is answered by the save once the quest it is about is over: the
/// journal either failed the other quests or it did not, which is the whole question.
pub fn live_refutation(item: &mut Value, state: &HashMap<String, String>, titles: &HashMap<String, String>, done_q: &HashSet<String>, ticked_q: &HashSet<String>) -> bool {
    let checks: Vec<Value> = item.get("checks").and_then(|v| v.as_array()).cloned().unwrap_or_default();
    let name = |q: &String| titles.get(q).cloned().unwrap_or_else(|| q.clone());
    for c in checks.iter().filter(|c| c.get("kind").and_then(|k| k.as_str()) == Some("not_failed")) {
        let when = qlist(c, "when");
        let quests = qlist(c, "quests");
        if quests.is_empty() || !when.iter().any(|q| matches!(live_status(state, done_q, ticked_q, q).as_deref(), Some("Done") | Some("Failed"))) {
            continue;
        }
        let over = when.iter().map(name).collect::<Vec<_>>().join(", ");
        let failed: Vec<String> = quests.iter().filter(|q| live_status(state, done_q, ticked_q, q).as_deref() == Some("Failed")).map(name).collect();
        put(item, "live", json!("settled"));
        if failed.is_empty() {
            put(item, "level", json!("info"));
            put(item, "tag", json!("SETTLED BY YOUR SAVE"));
            put(item, "live_note", json!(format!("Your save answers this: {over} is over and none of those quests failed in it, so the claim holds for your game.")));
        } else {
            put(item, "level", json!("lost"));
            put(item, "tag", json!("FAILED IN YOUR SAVE"));
            put(item, "live_note", json!(format!("Your save answers this: {over} is over and {} failed, so that is what happened in this playthrough.", failed.join(", "))));
        }
        return true;
    }
    // the save has not reached this question yet, which is worth saying instead of implying it is settled
    let refutes = checks.iter().any(|c| c.get("kind").and_then(|k| k.as_str()) == Some("not_failed"));
    if refutes && item.get("live").is_none() {
        put(item, "live", json!("unknown"));
        put(item, "tag", json!("NOT ANSWERED BY THIS SAVE YET"));
        put(
            item,
            "live_note",
            json!("Your save has not reached the quest this is about, so the note stands as written - the game files are the source, not your progress."),
        );
    }
    true
}

/// Annotate any warning the data can be re-read against the save. Returns false when it no longer applies.
/// `done_q` is every quest the route counts as finished; `ticked_q` is the ones you ticked yourself while the
/// journal still has them open, which are held back from `done_q` so they cannot silence a warning.
pub fn live_warning_facts(item: &mut Value, state: &HashMap<String, String>, titles: &HashMap<String, String>, done_q: &HashSet<String>, ticked_q: &HashSet<String>, facts: &HashSet<String>) -> bool {
    if !qlist(item, "affected").is_empty() && !qlist(item, "closed_by").is_empty() {
        return live_cutoff_facts(item, state, done_q, ticked_q, facts);
    }
    // a refuted claim is answered by the journal, not by a gate: the question is whether the quests it
    // names failed, and only the save knows that
    if item.get("evidence").and_then(|v| v.as_str()) == Some("refuted") {
        return live_refutation(item, state, titles, done_q, ticked_q);
    }
    let gate = item
        .get("checks")
        .and_then(|v| v.as_array())
        .map(|a| a.iter().any(|c| c.get("kind").and_then(|k| k.as_str()) == Some("implies_done")))
        .unwrap_or(false);
    if gate {
        return live_gate(item, state, titles, done_q, ticked_q);
    }
    live_refutation(item, state, titles, done_q, ticked_q);
    true
}

pub fn verdict_json(v: &Verdict, display: &str) -> Value {
    json!({"verdict": v.verdict, "headline": v.headline, "details": v.details, "display": display})
}

/// A reviewed turn-in whose wording depends on the save's facts. It never changes whether the
/// window is live; it only names what is still missing, or that both items are in hand.
pub fn turn_in_text(item: &mut Value, facts: &HashSet<String>) -> bool {
    let Some(turn) = item.get("turn_in").cloned() else { return false };
    let live = item.get("live").and_then(|x| x.as_str()).unwrap_or("");
    if !matches!(live, "ahead" | "inside" | "check" | "open") {
        return false;
    }
    let requires: Vec<String> = turn
        .get("requires")
        .and_then(|x| x.as_array())
        .map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect())
        .unwrap_or_default();
    if requires.is_empty() {
        return false;
    }
    let missing: Vec<&String> = requires.iter().filter(|f| !facts.contains(*f)).collect();
    let row = if missing.is_empty() {
        turn.get("both")
    } else if missing.len() == requires.len() {
        turn.get("neither")
    } else {
        turn.get("missing").and_then(|m| m.get(missing[0].as_str()))
    };
    let Some(row) = row else { return false };
    if let Some(h) = row.get("headline").and_then(|x| x.as_str()) {
        item["headline"] = json!(h);
    }
    if let Some(a) = row.get("action").and_then(|x| x.as_str()) {
        item["action"] = json!(a);
    }
    let note = if missing.is_empty() {
        "Both items are in the save's facts."
    } else if missing.len() == requires.len() {
        "The save has neither item."
    } else {
        "One of the two items is still missing."
    };
    item["live_note"] = json!(note);
    true
}

/// true when the route step reads this journal quest file (or one of its objectives / alternatives)
pub fn tracks(n: &Node, short_name: &str) -> bool {
    n.files.iter().any(|f| f.split('#').next() == Some(short_name) || f.split('|').any(|x| x == short_name))
}

/// the route step that tracks this journal quest file, if any
pub fn step_for_short(ev: &Eval, short_name: &str) -> Option<usize> {
    (0..ev.steps.len()).find(|&i| tracks(&ev.steps[i].n, short_name))
}

/// warning for the quest you are tracking: "stop" when finishing it closes open quests, "warn" when the route says to wait
pub fn tracked_warning(ev: &Eval, short_name: &str) -> Option<(&'static str, String, Vec<String>)> {
    for e in &ev.events {
        if e.fired {
            continue;
        }
        let Some((r, sts)) = e.def.fires.iter().find(|(r, _)| r.split('#').next() == Some(short_name)) else { continue };
        // open steps of the same quest do not count: finishing it does not fail it
        let others: Vec<usize> = e.open.iter().copied().filter(|&d| !tracks(&ev.steps[d].n, short_name)).collect();
        if others.is_empty() {
            continue;
        }
        let names: Vec<&str> = others.iter().take(8).map(|&d| short(&ev.steps[d].n.title)).collect();
        // say what the event waits for: an objective of this quest, its end, or (rarely) its start
        let headline = if r.contains('#') {
            format!("Its next step triggers \"{}\"", e.def.name)
        } else if sts.iter().all(|s| s == "Done") {
            format!("Finishing this triggers \"{}\"", e.def.name)
        } else {
            format!("This triggers \"{}\"", e.def.name)
        };
        // soft events are the same amber "warn" the alerts use
        let level = if e.def.soft { "warn" } else { "stop" };
        return Some((level, headline, vec![format!("It would fail or lock: {}", names.join("; ")), "Finish those first.".into()]));
    }
    for s in &ev.steps {
        if let (true, Some(h)) = (tracks(&s.n, short_name), &s.held) {
            let names: Vec<&str> = h.blockers.iter().take(3).map(|&x| short(&ev.steps[x].n.title)).collect();
            return Some(("warn", "Recommended to wait".into(), vec![h.why.clone(), format!("Do first: {}", names.join("; "))]));
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    fn route_file() -> RouteData {
        let p = concat!(env!("CARGO_MANIFEST_DIR"), "/data/route.json");
        let v: Value = serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap();
        load_route(&v).unwrap()
    }

    #[test]
    fn the_default_step_payload_carries_no_instruction_or_ending_label() {
        let rd = route_file();
        let ev = evaluate(&rd, &HashMap::new(), &HashSet::new(), &HashMap::new(), &HashSet::new());
        let endings: Value = serde_json::from_str(
            &std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/data/endings.json")).unwrap(),
        ).unwrap();
        let labels: Vec<String> = endings
            .get("targets")
            .and_then(|x| x.as_object())
            .into_iter()
            .flatten()
            .filter_map(|(_, t)| t.get("label").and_then(|x| x.as_str()).map(String::from))
            .collect();
        assert!(!labels.is_empty(), "the shipped labels are what the scan must catch");
        for i in 0..ev.steps.len() {
            let body = step_json(&rd, &ev, i).to_string();
            assert!(!body.contains("\"instruction\""), "{} carries an instruction", ev.steps[i].n.id);
            for l in &labels {
                assert!(!body.contains(l.as_str()), "{} carries the ending label {l}", ev.steps[i].n.id);
            }
        }
    }

    #[test]
    fn a_flag_never_overrules_a_live_journal() {
        let mut n = node("flagged", "10", &["flagged"], "side", 0, true);
        n.when = vec!["keira_sent=yes".into()];
        let rd = route(vec![n]);
        let flags = HashMap::from([("keira_sent".to_string(), "no".to_string())]);
        // the save proves the quest exists: the flag cannot mark it N/A or unknown
        let ev = evaluate(&rd, &state(&[("flagged", "Active")]), &HashSet::new(), &flags, &HashSet::new());
        assert_eq!(ev.steps[0].status, "Active");
        assert!(!ev.steps[0].cond_unknown);
        // on a quest the save has not reached, the flag still excludes it
        let ev = evaluate(&rd, &HashMap::new(), &HashSet::new(), &flags, &HashSet::new());
        assert_eq!(ev.steps[0].status, "N/A");
    }

    #[test]
    fn the_tick_truth_table_holds_for_every_journal_state() {
        for (status, ticked, want, note) in [
            ("Not started", false, "Not started", false),
            ("Not started", true, "Not started", true),
            ("Active", false, "Active", false),
            ("Active", true, "Active", true),
            ("Done", false, "Done", false),
            ("Done", true, "Done", false),
            ("Failed", false, "Failed", false),
            ("Failed", true, "Failed", false),
        ] {
            let n = node("t", "10", &["t"], "side", 0, true);
            let rd = route(vec![n]);
            let st = state(&[("t", status)]);
            let ticks = if ticked { HashSet::from(["t".to_string()]) } else { HashSet::new() };
            let ev = evaluate(&rd, &st, &ticks, &HashMap::new(), &HashSet::new());
            assert_eq!(ev.steps[0].status, want, "{status} ticked={ticked}");
            assert_eq!(ev.steps[0].tick_disagrees, note, "{status} ticked={ticked}");
        }
    }

    fn state(pairs: &[(&str, &str)]) -> HashMap<String, String> {
        pairs.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect()
    }

    fn node(id: &str, lv: &str, files: &[&str], kind: &str, order: i64, start_known: bool) -> Node {
        Node {
            section: "Main".into(), id: id.into(), title: id.into(), lv: lv.into(),
            files: files.iter().map(|f| f.to_string()).collect(), hard: vec![],
            hard_facts: HashMap::new(), by: vec![], note: String::new(), kind: kind.into(),
            opt: false, when: vec![], order, desc: "A line about the quest.".into(),
            branch: false, dialogue_choice: false, ending_relevant: false, start_known,
            provenance: if files.is_empty() { "manual_reviewed".into() } else { "game_file".into() },
            review_reason: String::new(), review_source: String::new(), reviewed: String::new(),
        }
    }

    fn route(nodes: Vec<Node>) -> RouteData {
        RouteData { sections: vec!["Main".into()], nodes, events: vec![], prefs: vec![],
                     conditional: HashSet::new(), flags: vec![], manual_audit: Value::Null }
    }

    fn at(ev: &Eval, id: &str) -> usize {
        *ev.byid.get(id).unwrap_or_else(|| panic!("{id} in the route"))
    }

    fn classified(status: &str, journal: &str, manual: bool, ticked: bool, tick_disagrees: bool,
                  cond_unknown: bool, lost: bool, when: &[&str], watch: Value) -> Classification {
        let files: &[&str] = if manual { &[] } else { &["x"] };
        let mut n = node("x", "10", files, if manual { "manual" } else { "main" }, 0, !manual);
        n.when = when.iter().map(|s| s.to_string()).collect();
        if manual {
            n.provenance = "manual_reviewed".into();
            n.review_reason = "fixture".into();
        }
        let s = Step {
            n, status: status.into(), journal: journal.into(), manual, locked: vec![], held: None,
            lost, evs: vec![], cond_unknown, tick_disagrees, frontier: "available",
        };
        let watch = watch.as_array().cloned().unwrap_or_default();
        classify(&s, &watch, ticked)
    }

    #[test]
    fn the_matrix_never_turns_a_passed_cutoff_or_a_tick_into_a_proved_loss() {
        // The journal has not failed it: a fired cutoff is a check, not LOST.
        let passed = classified("Not started", "Not started", false, false, false, false, true,
                                &[], json!([{"live": "passed", "headline": "check now", "mechanism": "journal_failure"}]));
        assert_eq!(passed.state, "at_risk");
        let fired_no_watch = classified("Not started", "Not started", false, false, false, false, true, &[], json!([]));
        assert_eq!(fired_no_watch.state, "at_risk");
        let failed = classified("Failed", "Failed", false, false, false, false, false, &[], json!([]));
        assert_eq!(failed.state, "lost");
        assert_eq!(failed.source, "journal");
        let missed = classified("Not started", "Not started", false, false, false, false, false, &[],
                                json!([{"live": "missed", "headline": "missed", "mechanism": "journal_gate"}]));
        assert_eq!(missed.state, "lost");
        let lost = classified("Active", "Active", false, false, false, false, false, &[],
                              json!([{"live": "lost", "headline": "failed", "mechanism": "journal_failure"}]));
        assert_eq!(lost.state, "lost");
    }

    #[test]
    fn a_tick_never_overrules_the_journal_in_the_matrix() {
        // Active + tick: the matrix is unchanged by the note; the card still says Active.
        let open = classified("Active", "Active", false, true, true, false, false, &[], json!([]));
        assert_eq!(open.state, "obtainable");
        // Not started + tick: the journal has no completed entry, so the step stays obtainable -
        // not unknown, never done. The note is reported beside the card, not as a status.
        let absent = classified("Not started", "Not started", false, true, true, false, false, &[], json!([]));
        assert_eq!(absent.state, "obtainable");
        // A live warning still outranks the note.
        let warned = classified("Not started", "Not started", false, true, true, false, false, &[],
                                json!([{"live": "check", "headline": "cutoff passed", "mechanism": "journal_failure"}]));
        assert_eq!(warned.state, "at_risk");
        let manual = classified("Done", "Not started", true, true, false, false, false, &[], json!([]));
        assert_eq!(manual.state, "done");
        assert_eq!(manual.source, "manual_reviewed");
        assert!(!manual.reason.contains("gamefile claim") || manual.reason.contains("not a gamefile"));
    }

    #[test]
    fn a_reviewed_turn_in_names_what_is_still_missing() {
        let turn = json!({
            "requires": ["noble", "soldier"],
            "both": {"headline": "Both in hand - talk now", "action": "Talk to Triss"},
            "neither": {"headline": "Find both", "action": "Find both statuettes"},
            "missing": {
                "noble": {"headline": "Need the noble statuette", "action": "Find the noble statuette"},
                "soldier": {"headline": "Need the soldier statuette", "action": "Find the soldier statuette"}
            }
        });
        let both = HashSet::from(["noble".to_string(), "soldier".to_string()]);
        let mut item = json!({"live": "inside", "turn_in": turn.clone()});
        assert!(turn_in_text(&mut item, &both));
        assert_eq!(item["headline"], "Both in hand - talk now");
        assert_eq!(item["action"], "Talk to Triss");
        assert!(item["live_note"].as_str().unwrap().contains("Both items"));

        let noble = HashSet::from(["noble".to_string()]);
        let mut item = json!({"live": "inside", "turn_in": turn.clone()});
        assert!(turn_in_text(&mut item, &noble));
        assert_eq!(item["headline"], "Need the soldier statuette");
        assert!(item["live_note"].as_str().unwrap().contains("still missing"));

        let none = HashSet::new();
        let mut item = json!({"live": "ahead", "turn_in": turn.clone()});
        assert!(turn_in_text(&mut item, &none));
        assert_eq!(item["headline"], "Find both");

        let mut lost = json!({"live": "lost", "turn_in": turn});
        assert!(!turn_in_text(&mut lost, &both), "a lost window keeps its journal verdict");
    }

    #[test]
    fn the_matrix_names_an_exclusion_and_does_not_guess_an_unanswered_flag() {
        let excluded = classified("N/A", "Not started", false, false, false, false, false, &["keira_sent=yes"], json!([]));
        assert_eq!(excluded.state, "excluded");
        assert!(excluded.reason.contains("keira_sent=yes"));
        let unknown = classified("Not started", "Not started", false, false, false, true, false, &["keira_sent=yes"], json!([]));
        assert_eq!(unknown.state, "unknown");
        let no_start = classified("Not started", "Not started", false, false, false, false, false, &[], json!([]));
        assert_eq!(no_start.state, "obtainable", "an unknown start is available, not unavailable");
    }

    #[test]
    fn a_finished_quest_answers_for_an_objective_the_save_does_not_carry() {
        // A route file can narrow a quest to one journal objective. The save may carry the quest's
        // own entry and not that objective; the finished quest must still read Done, or a passed
        // card window stays OPEN LATER forever.
        let n = node("q", "10", &["q#Win the card"], "gwent", 0, true);
        let rd = route(vec![n]);
        let ev = evaluate(&rd, &state(&[("q", "Done")]), &HashSet::new(), &HashMap::new(), &HashSet::new());
        assert_eq!(ev.steps[0].status, "Done");
        assert_eq!(ev.steps[0].journal, "Done");
        let stale = evaluate(&rd, &state(&[("q", "Done"), ("q#Win the card", "Not started")]),
                             &HashSet::new(), &HashMap::new(), &HashSet::new());
        assert_eq!(stale.steps[0].status, "Done");
        let active = evaluate(&rd, &state(&[("q", "Active")]), &HashSet::new(), &HashMap::new(), &HashSet::new());
        assert_eq!(active.steps[0].status, "Active");
    }

    #[test]
    fn frontier_states_follow_the_save_and_never_hide_an_unknown_start() {
        let done = node("done", "", &["done"], "side", 0, true);
        let active = node("active", "", &["active"], "side", 0, true);
        let available = node("available", "", &["available"], "side", 0, true);
        let unknown = node("unknown", "", &["unknown"], "side", 0, false);
        let dep = node("dep", "", &["dep"], "side", 0, true);
        let mut gated = node("gated", "", &["gated"], "side", 0, true);
        gated.hard = vec!["dep".into()];
        let rd = route(vec![done, active, available, unknown, dep, gated]);
        let st = state(&[("done", "Done"), ("active", "Active")]);
        let ev = evaluate(&rd, &st, &HashSet::new(), &HashMap::new(), &HashSet::new());
        assert_eq!(ev.steps[at(&ev, "done")].frontier, "done");
        assert_eq!(ev.steps[at(&ev, "active")].frontier, "in_log");
        assert_eq!(ev.steps[at(&ev, "available")].frontier, "available");
        assert_eq!(ev.steps[at(&ev, "unknown")].frontier, "unknown");
        assert_eq!(ev.steps[at(&ev, "gated")].frontier, "gated");
        assert!(!ev.todo.contains(&at(&ev, "done")));
        assert!(!ev.todo.contains(&at(&ev, "gated")));
        for id in ["active", "available", "unknown", "dep"] {
            assert!(ev.todo.contains(&at(&ev, id)), "{id} should stay in DO NEXT");
        }
        // the card JSON carries no wiki field; it carries the short description and the chip list
        let v = step_json(&rd, &ev, at(&ev, "unknown"));
        for bad in ["note", "start", "conf", "kb", "guide", "choices"] {
            assert!(v.get(bad).is_none(), "step JSON still has {bad}");
        }
        assert_eq!(v["desc"], "A line about the quest.");
        assert!(v["tags"].is_array());
        assert_eq!(v["frontier"], "unknown");
    }

    #[test]
    fn do_next_is_tracked_then_in_log_then_available_then_caution() {
        let tracked = node("tracked", "20", &["tracked"], "side", 9, true);
        let active_low = node("active_low", "30", &["active_low"], "side", 9, true);
        let avail_l5 = node("avail_l5", "5", &["avail_l5"], "side", 2, true);
        let avail_l3 = node("avail_l3", "3", &["avail_l3"], "side", 9, true);
        let avail_nolevel = node("avail_nolevel", "", &["avail_nolevel"], "side", 1, true);
        let caution = node("caution", "2", &["caution"], "side", 1, true);
        let gwent = node("gwent", "", &["gwent"], "gwent", 0, true);
        let treasure = node("treasure", "", &["treasure"], "treasure", 0, true);
        let dep = node("dep", "", &["dep"], "side", 0, true);
        let mut gated = node("gated", "", &["gated"], "side", 0, true);
        gated.hard = vec!["dep".into()];
        let rd = route(vec![tracked.clone(), active_low.clone(), avail_l5.clone(), avail_l3.clone(),
                            avail_nolevel.clone(), caution.clone(), gwent.clone(), treasure.clone(), dep, gated]);
        let st = state(&[("tracked", "Active"), ("active_low", "Active")]);
        let ev = evaluate(&rd, &st, &HashSet::new(), &HashMap::new(), &HashSet::new());
        let caution_ids: HashSet<usize> = HashSet::from([at(&ev, "caution")]);
        let ord = todo_order(&ev, Some("tracked"), &HashSet::new(), &caution_ids, None);
        let pos = |id: &str| ord.iter().position(|&i| ev.steps[i].n.id == id)
            .unwrap_or_else(|| panic!("{id} is not in DO NEXT: {:?}", ord.iter().map(|&i| &ev.steps[i].n.id).collect::<Vec<_>>()));
        assert_eq!(pos("tracked"), 0, "the tracked quest comes first");
        assert!(!ord.iter().any(|&i| ev.steps[i].n.id == "avail_l3"), "a merely unlocked quest is not in UP NEXT");
        assert!(!ord.iter().any(|&i| ev.steps[i].n.id == "caution"), "caution alone does not enter UP NEXT");
        assert!(!ord.iter().any(|&i| ev.steps[i].n.id == "gwent"), "an unopened Gwent quest is not in UP NEXT");
        assert!(!ord.iter().any(|&i| ev.steps[i].n.id == "treasure"), "an unopened treasure hunt is not in UP NEXT");
        assert!(!ord.iter().any(|&i| ev.steps[i].n.id == "gated"), "gated is never in DO NEXT");
        // the tracked quest enters even when its journal has not opened, and the single next plan
        // step enters by name; nothing else does
        let tracked_gwent = todo_order(&ev, Some("gwent"), &HashSet::new(), &HashSet::new(), Some("treasure"));
        assert_eq!(ev.steps[tracked_gwent[0]].n.id, "gwent");
        assert!(tracked_gwent.iter().any(|&i| ev.steps[i].n.id == "treasure"));
        assert!(!tracked_gwent.iter().any(|&i| ev.steps[i].n.id == "avail_l5"), "one plan step, not all available ones");
        // a fired cutoff takes its step out of DO NEXT; the top section names it instead
        let unsafe_ids = HashSet::from([at(&ev, "avail_l3")]);
        let without = todo_order(&ev, Some("tracked"), &unsafe_ids, &caution_ids, None);
        assert!(!without.iter().any(|&i| ev.steps[i].n.id == "avail_l3"));
    }

    #[test]
    fn a_tick_keeps_the_journal_state_and_says_so() {
        let noble = node("mq3012noblestatuette", "", &["mq3012noblestatuette"], "side", 0, true);
        let rd = route(vec![noble]);
        let st = state(&[("mq3012noblestatuette", "Active")]);
        let ticks = HashSet::from(["mq3012noblestatuette".to_string()]);
        let ev = evaluate(&rd, &st, &ticks, &HashMap::new(), &HashSet::new());
        let i = at(&ev, "mq3012noblestatuette");
        assert_eq!(ev.steps[i].status, "Active", "a tick is a note; it never becomes the status");
        assert_eq!(ev.steps[i].journal, "Active", "the journal still has it open");
        assert!(ev.steps[i].tick_disagrees);
        let tags = step_json(&rd, &ev, i)["tags"].to_string();
        assert!(tags.contains("tick disagrees"), "tags: {tags}");

        // The same note on a quest the journal has not started must not become Done either: the
        // truth table keeps the card Not started, the matrix obtainable, and the note visible.
        let untouched = state(&[("mq3012noblestatuette", "Not started")]);
        let fresh = evaluate(&rd, &untouched, &ticks, &HashMap::new(), &HashSet::new());
        let j = at(&fresh, "mq3012noblestatuette");
        assert_eq!(fresh.steps[j].status, "Not started");
        assert_eq!(fresh.steps[j].journal, "Not started");
        assert!(fresh.steps[j].tick_disagrees);
        let nc = classify(&fresh.steps[j], &[], true);
        assert_eq!(nc.state, "obtainable");

        let mut item = json!({
            "id": "triss_statuettes", "level": "stop",
            "affected": ["mq3012noblestatuette", "mq3012warriorstatuette"],
            "affected_titles": ["The Nobleman Statuette", "The Soldier Statuette"],
            "closed_by": ["sq301triss"], "closed_by_titles": ["Now or Never"],
            "headline": "Hand both statuettes to Triss before {binding}",
            "why": "triss.w2comm is switched off", "action": "Give the statuettes to Triss", "files": []
        });
        let st = state(&[("sq301triss", "Done"), ("mq3012noblestatuette", "Active"), ("mq3012warriorstatuette", "Active")]);
        assert!(live_cutoff(&mut item, &st, &HashSet::new(), &ticks));
        assert_eq!(item["live"], "check", "a tick must not turn a fired cutoff back into advice");
        assert!(item["tag"].as_str().unwrap().contains("CHECK NOW"), "tag: {}", item["tag"]);
        let headline = item["headline"].as_str().unwrap();
        assert!(headline.contains("cutoff has passed"), "headline: {headline}");
        assert!(headline.contains("journal still has"), "headline: {headline}");
        assert!(!headline.contains("can no longer be completed"), "the journal has not failed it: {headline}");
        assert!(!headline.contains("CDeactivateSpawnset"), "the card sentence must stay player-facing: {headline}");
        assert!(item["live_note"].as_str().unwrap().contains("You ticked"), "note: {}", item["live_note"]);
        // once the journal finishes what the cutoff protects, there is nothing to warn about
        let done = state(&[("sq301triss", "Done"), ("mq3012noblestatuette", "Done"), ("mq3012warriorstatuette", "Done")]);
        let mut clean = json!({"id": "t", "affected": ["mq3012noblestatuette"], "closed_by": ["sq301triss"]});
        assert!(!live_cutoff(&mut clean, &done, &HashSet::new(), &ticks));
    }

    #[test]
    fn a_reviewed_fact_gate_opens_on_the_game_fact() {
        let rd = route_file();
        let i = at(&evaluate(&rd, &HashMap::new(), &HashSet::new(), &HashMap::new(), &HashSet::new()), "mq3036rosaromance");
        let before = evaluate(&rd, &state(&[("q304dandelion", "Active")]), &HashSet::new(), &HashMap::new(), &HashSet::new());
        assert!(!before.steps[i].locked.is_empty(), "Fencing Lessons waits on Broken Flowers' fact");
        let after = evaluate(&rd, &state(&[("q304dandelion", "Active")]), &HashSet::new(), &HashMap::new(),
                             &HashSet::from(["q304_rosa_visited".to_string()]));
        assert!(after.steps[i].locked.is_empty(), "the game's own fact opens it");
        let engaged = evaluate(&rd, &state(&[("mq3036rosaromance", "Active"), ("q304dandelion", "Active")]),
                               &HashSet::new(), &HashMap::new(), &HashSet::new());
        assert!(engaged.steps[i].locked.is_empty(), "an engaged step is never locked");
        // the four edges the saves refuted are gone, not merely reworded
        for id in ["q302favourforradovid", "q303treasure", "q302rescuingdudu", "sq106killbill"] {
            let n = rd.nodes.iter().find(|n| n.id == id).unwrap_or_else(|| panic!("{id} in the route"));
            assert!(n.hard.is_empty(), "{id} still hard-requires {:?}", n.hard);
        }
    }

    #[test]
    fn the_generated_route_is_the_whole_game() {
        let rd = route_file();
        assert_eq!(rd.sections, vec!["Main", "Secondary", "Contracts", "Treasure Hunts", "Gwent"]);
        let quest = rd.nodes.iter().filter(|n| !n.files.is_empty()).count();
        let manual = rd.nodes.len() - quest;
        assert_eq!(quest, 403, "one step per CJournalQuest except the two debug containers");
        assert_eq!(manual, 9, "the kept bookkeeping steps the save cannot show");
        assert_eq!(rd.nodes.len(), 412, "403 quest + 9 reviewed manual after the audit");
        assert_eq!(rd.manual_audit["baseline"], 11);
        assert_eq!(rd.manual_audit["replaced"], 2);
        assert!(rd.nodes.iter().filter(|n| n.files.is_empty())
                .all(|n| n.provenance == "manual_reviewed" && !n.review_reason.is_empty()
                     && !n.review_source.is_empty() && n.reviewed == "2026-10-28"));
        assert!(rd.nodes.iter().filter(|n| !n.files.is_empty())
                .all(|n| n.provenance == "game_file" && n.review_reason.is_empty()));
        let gwent = rd.nodes.iter().filter(|n| n.section == "Gwent").count();
        assert_eq!(gwent, 11, "ten Gwent quests plus the Vegelbud matches");
        assert!(!rd.nodes.iter().any(|n| n.id.contains("biddebug")), "the debug containers are excluded");
        assert!(rd.nodes.iter().filter(|n| !n.files.is_empty() && !n.desc.is_empty()).count() >= 390,
                "the lowest-order description resolves for almost every quest");
        assert!(!rd.nodes.iter().any(|n| n.id == "mq7001restinpeace" && n.section == "Gwent"),
                "Rest in Peace is not a Gwent quest");
        assert_eq!(rd.events.len(), 1, "the reviewed community loss edge; journal windows live in derived.json");
        for n in &rd.nodes {
            for b in &n.by {
                assert!(rd.events.iter().any(|(id, _)| id == b), "{} names unknown loss edge {b}", n.id);
            }
        }
        for id in ["ci_c1", "ci_c2", "ci_c3"] {
            let n = rd.nodes.iter().find(|n| n.id == id).unwrap();
            let t = n.title.to_lowercase();
            assert!(t.contains("choice"), "{id} should say a choice exists: {}", n.title);
            for spoiler in ["snowball", "emperor", "velen", "lodge", "triss"] {
                assert!(!t.contains(spoiler), "{id} still contains the choice text: {}", n.title);
            }
        }
        assert!(rd.nodes.iter().filter(|n| n.section == "Contracts").all(|n| !n.branch),
                "no contract carries a branch tag");
    }

    #[test]
    fn a_one_shot_dialogue_row_is_not_an_outcome_branch() {
        let rd = route_file();
        // MQ1050's only fact-setting row is a singleUseChoice row (mq1050_scene.w2scene sets
        // mq1050_true_vision). It is dialogue, so it must not become a branch.
        let one_shot = rd.nodes.iter().find(|n| n.id == "mq1050writteninthestars")
            .expect("mq1050writteninthestars in the route");
        assert!(one_shot.dialogue_choice, "mq1050 has a one-shot dialogue row");
        assert!(!one_shot.branch, "a one-shot dialogue row must not become a branch");
        assert!(!one_shot.ending_relevant, "a dialogue row is not an ending choice");
        // The Whispering Hillock spirit choice is a fact-setting branch (sections 195/197 run the
        // q105_show_lights_cutear script), and no reviewed target names it yet.
        let spirit = rd.nodes.iter().find(|n| n.id == "q105evilspirit").expect("q105evilspirit in the route");
        assert!(spirit.branch, "the spirit choice sets a fact");
        assert!(!spirit.ending_relevant, "ending relevance comes from data/endings.json, not a scene");
    }

    #[test]
    fn only_a_fact_setting_branch_gets_a_choice_chip() {
        let mut branch = node("branch", "", &["branch"], "side", 0, true);
        branch.branch = true;
        branch.dialogue_choice = true;
        let mut dialogue = node("dialogue", "", &["dialogue"], "side", 0, true);
        dialogue.dialogue_choice = true;
        let mut ending = node("ending", "", &["ending"], "side", 0, true);
        ending.branch = true;
        ending.ending_relevant = true;
        let rd = route(vec![branch, dialogue, ending]);
        let ev = evaluate(&rd, &HashMap::new(), &HashSet::new(), &HashMap::new(), &HashSet::new());
        let tags = |id: &str| step_json(&rd, &ev, at(&ev, id))["tags"].clone();
        let has = |v: &Value, id: &str| v.as_array().unwrap().iter().any(|t| t["id"] == id);
        assert!(has(&tags("branch"), "branch"), "a fact-setting branch gets the chip");
        assert!(!has(&tags("dialogue"), "branch"),
                "a one-shot dialogue row gets no choice chip");
        assert!(has(&tags("ending"), "ending_choice"));
        assert!(!has(&tags("ending"), "branch"), "the ending chip replaces the generic one");
    }

    #[test]
    fn a_finished_step_never_stays_open() {
        let rd = route_file();
        let flags = HashMap::new();
        for n in &rd.nodes {
            let (st, ticks) = if n.files.is_empty() {
                (HashMap::new(), HashSet::from([n.id.clone()]))
            } else {
                (n.files.iter().flat_map(|f| f.split('|')).map(|f| (f.to_string(), "Done".to_string())).collect(), HashSet::new())
            };
            let ev = evaluate(&rd, &st, &ticks, &flags, &HashSet::new());
            let i = at(&ev, &n.id);
            assert_eq!(ev.steps[i].status, "Done", "{} is not Done once its quest is", n.id);
            assert_eq!(ev.steps[i].frontier, "done");
            assert!(!ev.todo.contains(&i), "{} is Done but still in DO NEXT", n.id);
        }
    }

    #[test]
    fn a_passed_cutoff_is_a_check_until_the_journal_fails_the_quest() {
        let mut item = json!({"id": "x", "affected": ["mq3012noblestatuette"],
                              "closed_by": ["sq301triss"], "closed_by_titles": ["Now or Never"]});
        let open = state(&[("sq301triss", "Done"), ("mq3012noblestatuette", "Active")]);
        assert!(live_cutoff(&mut item, &open, &HashSet::new(), &HashSet::new()));
        assert_eq!(item["live"], "check");
        assert!(item["headline"].as_str().unwrap().contains("cutoff has passed"));
        let mut failed = json!({"id": "x", "affected": ["mq3012noblestatuette"], "closed_by": ["sq301triss"]});
        let lost = state(&[("sq301triss", "Done"), ("mq3012noblestatuette", "Failed")]);
        assert!(live_cutoff(&mut failed, &lost, &HashSet::new(), &HashSet::new()));
        assert_eq!(failed["live"], "lost");
        let mut done = json!({"id": "x", "affected": ["mq3012noblestatuette"], "closed_by": ["sq301triss"]});
        let settled = state(&[("sq301triss", "Done"), ("mq3012noblestatuette", "Done")]);
        assert!(!live_cutoff(&mut done, &settled, &HashSet::new(), &HashSet::new()));
    }

    #[test]
    fn a_journal_window_reads_the_phase_not_the_whole_quest() {
        let mut item = json!({
            "id": "triss_statuettes_window", "level": "stop",
            "affected": ["mq3012noblestatuette", "mq3012warriorstatuette"],
            "affected_titles": ["The Nobleman Statuette", "The Soldier Statuette"],
            "closed_by": ["q210preparations"], "closed_by_titles": ["Battle Preparations"],
            "closes_at": "q210preparations#Novigrad",
            "closes_at_title": "the end of Final Preparations"
        });
        let ahead = state(&[("q210preparations", "Not started"),
                            ("mq3012noblestatuette", "Active"), ("mq3012warriorstatuette", "Active")]);
        assert!(live_cutoff(&mut item, &ahead, &HashSet::new(), &HashSet::new()));
        assert_eq!(item["live"], "ahead");
        assert!(item["headline"].as_str().unwrap().contains("Final Preparations"), "headline: {}", item["headline"]);

        let inside = state(&[("q210preparations#Novigrad", "Active"),
                             ("mq3012noblestatuette", "Active"), ("mq3012warriorstatuette", "Active")]);
        assert!(live_cutoff(&mut item, &inside, &HashSet::new(), &HashSet::new()));
        assert_eq!(item["live"], "inside");
        let h = item["headline"].as_str().unwrap();
        assert!(h.contains("You are inside Battle Preparations"), "headline: {h}");
        assert!(h.contains("now if the game still allows it"), "headline: {h}");

        let passed = state(&[("q210preparations#Novigrad", "Done"),
                             ("mq3012noblestatuette", "Active"), ("mq3012warriorstatuette", "Active")]);
        assert!(live_cutoff(&mut item, &passed, &HashSet::new(), &HashSet::new()));
        assert_eq!(item["live"], "check");
        assert!(!item["headline"].as_str().unwrap().contains("can no longer be completed"));
    }

    #[test]
    fn a_window_whose_dialogue_option_opens_later_says_so() {
        let make = || json!({
            "id": "triss_statuettes_window", "level": "stop", "mechanism": "journal_failure",
            "affected": ["mq3012noblestatuette"], "affected_titles": ["The Nobleman Statuette"],
            "closed_by": ["q210preparations"], "closed_by_titles": ["Battle Preparations"],
            "closes_at": "q210preparations#Novigrad", "closes_at_title": "the end of Final Preparations",
            "opens_at": ["q310_philippa_rescued"],
            "not_yet_headline": "Triss will not take the statuettes yet",
            "not_yet_action": "Rescue Philippa during Final Preparations"
        });
        let inside = state(&[("q210preparations#Novigrad", "Active"), ("mq3012noblestatuette", "Active")]);
        let none = HashSet::new();
        let mut early = make();
        assert!(live_cutoff_facts(&mut early, &inside, &none, &none, &none));
        assert_eq!(early["live"], "not_yet", "the option is not offered before Philippa is rescued");
        assert_eq!(early["level"], "info");
        assert_eq!(early["headline"], "Triss will not take the statuettes yet");
        let facts = HashSet::from(["q310_philippa_rescued".to_string()]);
        let mut ready = make();
        assert!(live_cutoff_facts(&mut ready, &inside, &none, &none, &facts));
        assert_eq!(ready["live"], "inside");
        assert_eq!(ready["tag"], "DO THIS NOW");
        let passed = state(&[("q210preparations#Novigrad", "Done"), ("mq3012noblestatuette", "Active")]);
        let mut late = make();
        assert!(live_cutoff_facts(&mut late, &passed, &none, &none, &none));
        assert_eq!(late["live"], "check", "a passed window still reads as passed, not as not-open");
    }

    #[test]
    fn cutoff_headlines_say_what_is_happening_not_which_files_do_it() {
        let mut failed = json!({"id": "x", "affected": ["mq3012noblestatuette"],
                                "affected_titles": ["The Nobleman Statuette"],
                                "closed_by": ["sq301triss"], "closed_by_titles": ["Now or Never"]});
        let st = state(&[("sq301triss", "Active"), ("mq3012noblestatuette", "Failed")]);
        assert!(live_cutoff(&mut failed, &st, &HashSet::new(), &HashSet::new()));
        let h = failed["headline"].as_str().unwrap();
        assert!(h.contains("The Nobleman Statuette"));
        assert!(h.contains("journal marks it failed"), "headline: {h}");
        assert!(!h.contains("CDeactivateSpawnset"), "headline: {h}");

        let mut inside = json!({"id": "y", "affected": ["q402velenallies"],
                                "affected_titles": ["Brothers in Arms: Velen"],
                                "closed_by": ["q402ciri"], "closed_by_titles": ["The Isle of Mists"]});
        let st = state(&[("q402ciri", "Active"), ("q402velenallies", "Active")]);
        assert!(live_cutoff(&mut inside, &st, &HashSet::new(), &HashSet::new()));
        let h = inside["headline"].as_str().unwrap();
        assert!(h.contains("You are inside The Isle of Mists"), "headline: {h}");
        assert!(h.contains("finish it first"), "headline: {h}");
        assert!(!h.contains("CDeactivateSpawnset"), "headline: {h}");
    }
}
