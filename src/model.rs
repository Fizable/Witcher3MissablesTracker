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
    pub conf: String,
    pub hard: Vec<String>,
    pub by: Vec<String>,
    pub note: String,
    pub kind: String,
    pub opt: bool,
    #[serde(default)]
    pub when: Vec<String>,
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
    pub near: Vec<String>,
    #[serde(default)]
    pub soft: bool,
    /// extra context shown in the hold-off warning, e.g. a verified detail about the exact trigger
    #[serde(default)]
    pub note: String,
    /// true only once this event's fires/near/soft mapping has been checked against real evidence (a save-file
    /// diff, or a structural bundle-resource scan) rather than taken as-is from a wiki page
    #[serde(default)]
    pub verified: bool,
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
}

pub fn load_route(v: &Value) -> Result<RouteData, String> {
    let sections: Vec<String> = serde_json::from_value(v["sections"].clone()).map_err(|e| e.to_string())?;
    let nodes: Vec<Node> = serde_json::from_value(v["nodes"].clone()).map_err(|e| e.to_string())?;
    let prefs: Vec<Pref> = serde_json::from_value(v["prefs"].clone()).map_err(|e| e.to_string())?;
    let cond: Vec<String> = serde_json::from_value(v["conditional"].clone()).map_err(|e| e.to_string())?;
    let flags: Vec<FlagDef> = serde_json::from_value(v["flags"].clone()).unwrap_or_default();
    let mut events = Vec::new();
    let m: &Map<String, Value> = v["events"].as_object().ok_or("events missing")?;
    for (k, val) in m {
        events.push((k.clone(), serde_json::from_value::<EventDef>(val.clone()).map_err(|e| e.to_string())?));
    }
    Ok(RouteData { sections, nodes, events, prefs, conditional: cond.into_iter().collect(), flags })
}

pub struct Held {
    pub why: String,
    pub blockers: Vec<usize>,
}

pub struct Step {
    pub n: Node,
    pub status: String,
    pub manual: bool,
    pub locked: Vec<usize>,
    pub held: Option<Held>,
    pub lost: bool,
    pub evs: Vec<usize>, // indices into Eval.events
    pub cond_unknown: bool,
}

pub struct Ev {
    pub id: String,
    pub def: EventDef,
    pub fired: bool,
    pub open: Vec<usize>,
    pub near: bool,
    pub near_active: Vec<usize>, // which of def.near are already Active/Done (why `near` is true)
}

pub struct Alert {
    pub level: &'static str,
    pub msg: String,
    pub missing: Vec<usize>,
}

pub struct Eval {
    pub steps: Vec<Step>,
    pub byid: HashMap<String, usize>,
    pub events: Vec<Ev>,
    pub alerts: Vec<Alert>,
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
        let alts: Vec<String> = f.split('|').map(|x| state.get(x).cloned().unwrap_or_else(|| "Not started".into())).collect();
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
    if ticks.contains(&n.id) && st != "Failed" {
        "Done".into()
    } else {
        st.into()
    }
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

pub fn evaluate(rd: &RouteData, state: &HashMap<String, String>, ticks: &HashSet<String>, flags: &HashMap<String, String>) -> Eval {
    let secrank: HashMap<&str, usize> = rd.sections.iter().enumerate().map(|(i, s)| (s.as_str(), i)).collect();
    let mut steps: Vec<Step> = rd
        .nodes
        .iter()
        .map(|n| Step { n: n.clone(), status: if is_na(n, flags) { "N/A".into() } else { node_status(n, state, ticks) }, manual: n.files.is_empty(), locked: vec![], held: None, lost: false, evs: vec![], cond_unknown: cond_unknown(n, flags) })
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
            let dependent_engaged = steps
                .iter()
                .any(|s| s.n.hard.iter().any(|h| h == &steps[i].n.id) && matches!(s.status.as_str(), "Active" | "Done" | "Assumed") && s.n.kind != "gwent" && s.n.kind != "treasure");
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
        let locked: Vec<usize> = if engaged {
            vec![]
        } else {
            steps[i].n.hard.iter().filter_map(|h| byid.get(h).copied()).filter(|&j| !is_ok(&steps[j].status)).collect()
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
    // events
    let mut events: Vec<Ev> = Vec::new();
    for (eid, def) in &rd.events {
        let fired = def.fires.iter().any(|(r, sts)| state.get(r).map(|s| sts.contains(s)).unwrap_or(false));
        let open: Vec<usize> = (0..steps.len()).filter(|&i| steps[i].n.by.contains(eid) && matches!(steps[i].status.as_str(), "Active" | "Not started")).collect();
        let near_active: Vec<usize> = def.near.iter().filter_map(|x| byid.get(x)).filter(|&&i| matches!(steps[i].status.as_str(), "Active" | "Done")).copied().collect();
        let near = !near_active.is_empty();
        events.push(Ev { id: eid.clone(), def: def.clone(), fired, open, near, near_active });
    }
    let mut alerts: Vec<Alert> = Vec::new();
    for e in &events {
        if e.fired && !e.open.is_empty() {
            alerts.push(Alert {
                level: if e.def.soft { "warn" } else { "stop" },
                msg: format!("{} has happened. Still open and probably lost:", e.def.name),
                missing: e.open.clone(),
            });
        }
    }
    let eidx: HashMap<&str, usize> = events.iter().enumerate().map(|(i, e)| (e.id.as_str(), i)).collect();
    for s in steps.iter_mut() {
        s.evs = s.n.by.iter().filter_map(|b| eidx.get(b.as_str()).copied()).collect();
        s.lost = s.status == "Not started" && s.evs.iter().any(|&k| events[k].fired && !events[k].def.soft);
    }
    let failed: Vec<usize> = (0..steps.len()).filter(|&i| steps[i].status == "Failed" && !steps[i].n.opt).collect();
    if !failed.is_empty() {
        alerts.push(Alert { level: "stop", msg: "Failed in your quest log:".into(), missing: failed });
    }
    let todo: Vec<usize> = (0..steps.len())
        .filter(|&i| {
            let s = &steps[i];
            !s.n.opt && matches!(s.status.as_str(), "Active" | "Not started") && !s.lost && s.locked.is_empty() && s.held.is_none()
        })
        .collect();
    Eval { steps, byid, events, alerts, todo }
}

pub struct HoldOff {
    pub kind: &'static str,
    pub name: String,
    pub status: String,
    pub why: String,
    pub missing: Vec<usize>,
}

fn doable(ev: &Eval, i: usize, seen: &mut Vec<usize>, out: &mut Vec<usize>) {
    let s = &ev.steps[i];
    if is_ok(&s.status) || seen.contains(&i) {
        return;
    }
    if s.locked.is_empty() {
        if !out.contains(&i) {
            out.push(i);
        }
        return;
    }
    seen.push(i);
    for &l in &s.locked {
        doable(ev, l, seen, out);
    }
    seen.pop();
}

pub fn dont_start(ev: &Eval) -> Vec<HoldOff> {
    let mut holds: Vec<HoldOff> = Vec::new();
    for s in &ev.steps {
        if let Some(h) = &s.held {
            let mut miss = Vec::new();
            for &b in &h.blockers {
                doable(ev, b, &mut Vec::new(), &mut miss);
            }
            holds.push(HoldOff { kind: "hold", name: short(&s.n.title).to_string(), status: s.status.clone(), why: h.why.clone(), missing: miss });
        }
    }
    let mut events: Vec<HoldOff> = Vec::new();
    for e in &ev.events {
        if e.fired || !e.near || e.open.is_empty() {
            continue;
        }
        let mut now = Vec::new();
        for &d in &e.open {
            doable(ev, d, &mut Vec::new(), &mut now);
        }
        let names: Vec<&str> = e.open.iter().take(6).map(|&d| short(&ev.steps[d].n.title)).collect();
        // name what's already under way, so the warning has a concrete action attached instead of just the event's
        // name. `near` is only a proximity signal (this cutoff is getting close), not necessarily the trigger itself -
        // only `def.note` (filled in once an event's exact trigger has been verified, e.g. E_KG) may claim causation.
        let near_names: Vec<&str> = e.near_active.iter().map(|&d| short(&ev.steps[d].n.title)).collect();
        let mut why = format!("Already under way: {}.", near_names.join(", "));
        if !e.def.note.is_empty() {
            why.push(' ');
            why.push_str(&e.def.note);
        }
        why.push_str(&format!(" This would fail or lock: {}{}.", names.join("; "), if e.open.len() > 6 { "..." } else { "" }));
        if e.open.iter().all(|&d| !ev.steps[d].locked.is_empty()) {
            why.push_str(" You cannot do them yet, so stay away from this for now.");
        }
        events.push(HoldOff { kind: "event", name: e.def.name.clone(), status: String::new(), why, missing: now });
    }
    events.extend(holds); // events first, like the Python version
    events
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

fn r(ev: &Eval, i: usize) -> Value {
    json!({"id": ev.steps[i].n.id, "title": short(&ev.steps[i].n.title), "manual": ev.steps[i].manual})
}

pub fn step_json(rd: &RouteData, ev: &Eval, i: usize, start: &str) -> Value {
    let s = &ev.steps[i];
    json!({
        "id": s.n.id, "title": s.n.title, "section": s.n.section, "lv": s.n.lv, "status": s.status,
        "manual": s.manual, "opt": s.n.opt, "conf": s.n.conf, "note": s.n.note, "start": start, "kind": s.n.kind,
        "conditional": s.cond_unknown || rd.conditional.contains(&s.n.id),
        "locked": s.locked.iter().map(|&x| r(ev, x)).collect::<Vec<_>>(),
        "held": s.held.as_ref().map(|h| json!({"why": h.why, "blockers": h.blockers.iter().map(|&x| r(ev, x)).collect::<Vec<_>>()})),
        "lost": s.lost,
    })
}

pub fn holdoff_json(ev: &Eval) -> Value {
    Value::Array(
        dont_start(ev)
            .iter()
            .map(|h| json!({"kind": h.kind, "name": h.name, "status": h.status, "why": h.why, "missing": h.missing.iter().map(|&x| r(ev, x)).collect::<Vec<_>>()}))
            .collect(),
    )
}

pub fn alerts_json(ev: &Eval) -> Value {
    Value::Array(ev.alerts.iter().map(|a| json!({"level": a.level, "msg": a.msg, "missing": a.missing.iter().map(|&x| r(ev, x)).collect::<Vec<_>>()})).collect())
}

pub fn verdict_json(v: &Verdict, display: &str) -> Value {
    json!({"verdict": v.verdict, "headline": v.headline, "details": v.details, "display": display})
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

    fn route() -> RouteData {
        let p = concat!(env!("CARGO_MANIFEST_DIR"), "/data/route.json");
        let v: Value = serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap();
        load_route(&v).unwrap()
    }

    fn state(pairs: &[(&str, &str)]) -> HashMap<String, String> {
        pairs.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect()
    }

    /// steps no journal entry shows (a tutorial, Gwent matches, a visit): the user ticks them, so they may gate a hold-off
    const INHERENTLY_MANUAL: [&str; 3] = ["wo_prologue", "no_vegelbud", "hos_shakes"];
    /// cutoffs that happen where the save records nothing (leaving a place)
    const UNDETECTABLE_EVENTS: [&str; 1] = ["E_LAMP"];

    /// the save has to be able to tell when a step that gates a hold-off is done, or the hold-off can never clear on its own
    #[test]
    fn steps_that_gate_a_hold_off_can_be_read_from_the_save() {
        let rd = route();
        let mut gating: Vec<&str> = rd.nodes.iter().filter(|n| !n.by.is_empty()).map(|n| n.id.as_str()).collect();
        gating.extend(rd.prefs.iter().flat_map(|p| p.needs.iter().map(|s| s.as_str())));
        for id in gating {
            let n = rd.nodes.iter().find(|n| n.id == id).unwrap_or_else(|| panic!("unknown step {id}"));
            assert!(
                !n.files.is_empty() || INHERENTLY_MANUAL.contains(&id),
                "'{}' ({id}) gates a hold-off but reads no journal file: link it to its journal entry, or list it in INHERENTLY_MANUAL",
                n.title
            );
        }
    }

    /// an event that can never fire never lets the tracker say it has happened
    #[test]
    fn every_cutoff_can_be_detected() {
        for (id, e) in route().events {
            assert!(!e.fires.is_empty() || UNDETECTABLE_EVENTS.contains(&id.as_str()), "{id} ({}) has no journal trigger", e.name);
        }
    }

    /// whatever way a step is marked done (its journal quest, or your tick), it never stays in DO NEXT or as something to do first
    #[test]
    fn a_finished_step_never_stays_open() {
        let rd = route();
        let flags = HashMap::new();
        for n in &rd.nodes {
            let (st, ticks) = if n.files.is_empty() {
                (HashMap::new(), HashSet::from([n.id.clone()]))
            } else {
                (n.files.iter().map(|f| (f.split('|').next().unwrap().to_string(), "Done".to_string())).collect(), HashSet::new())
            };
            let ev = evaluate(&rd, &st, &ticks, &flags);
            let i = ev.byid[&n.id];
            assert_eq!(ev.steps[i].status, "Done", "{} is not Done once its quest is", n.id);
            assert!(!ev.todo.contains(&i), "{} is Done but still in DO NEXT", n.id);
            for h in dont_start(&ev) {
                assert!(!h.missing.contains(&i), "{} is Done but '{}' still says to do it first", n.id, h.name);
            }
        }
    }

    /// A Walk on the Waterfront shows up in the journal as 'Shady Deal'; once that is done the outpost hold-off must go
    #[test]
    fn finishing_the_waterfront_quest_clears_the_outpost_hold_off() {
        let rd = route();
        let held = |st: HashMap<String, String>| {
            let ev = evaluate(&rd, &st, &HashSet::new(), &HashMap::new());
            dont_start(&ev).iter().any(|h| h.name.contains("witch-hunter outpost"))
        };
        assert!(held(state(&[("q303treasure", "Active")])));
        assert!(!held(state(&[("q303treasure", "Active"), ("mq3005badalley", "Done")])));
        // once the outpost section has started or the quest is over, the cutoff has happened and holding off is moot
        assert!(!held(state(&[("q303treasure", "Active"), ("q303treasure#Follow Witch Hunter Leader", "Active")])));
        assert!(!held(state(&[("q303treasure", "Done")])));
    }

    /// Destination: Skellige's journal entry is a phase placeholder that stays "Active" forever, even long after the
    /// player has sailed on: the only proof it finished is that The King is Dead (which hard-requires it) is itself
    /// under way. Same for a longer chain: Echoes of the Past hard-requires The King is Dead.
    #[test]
    fn a_hard_prereq_is_assumed_done_once_what_it_gates_has_engaged() {
        let rd = route();
        let ev = evaluate(&rd, &state(&[("q201traveltoskellige", "Active"), ("pirate", "Active")]), &HashSet::new(), &HashMap::new());
        let dest = ev.byid["sk_dest"];
        assert_eq!(ev.steps[dest].status, "Assumed", "sk_dest should be inferred done once sk_king (which hard-requires it) has engaged");
        assert!(!ev.todo.contains(&dest));

        // sk_king's own journal file is itself stuck on a non-representative first entry; only the next quest down
        // the chain (Echoes of the Past) shows real progress, two hops away from Destination: Skellige
        let chain = evaluate(&rd, &state(&[("q201traveltoskellige", "Active"), ("pirate", "Not started"), ("q203cataclysm", "Active")]), &HashSet::new(), &HashMap::new());
        let king = chain.byid["sk_king"];
        let dest2 = chain.byid["sk_dest"];
        assert_eq!(chain.steps[king].status, "Assumed", "sk_king should be inferred done once sk_echoes (which hard-requires it) has engaged");
        assert_eq!(chain.steps[dest2].status, "Assumed", "sk_dest should be inferred done transitively through sk_king");
    }

    /// Gwent: Skellige Style hard-requires Echoes of the Past, but its own "Active" status comes from a single
    /// card-win objective that is just as often a stuck placeholder (caught against a real save: Mousesack's entry
    /// reads Active with no card actually won yet). A gwent/treasure step engaging must never "prove" a main quest
    /// done, or a quest the player is genuinely mid-way through (and that should still show up in DO NEXT) vanishes.
    #[test]
    fn a_gwent_step_engaging_does_not_assume_the_main_quest_it_needs_is_done() {
        let rd = route();
        let ev = evaluate(&rd, &state(&[("q203cataclysm", "Not started"), ("cgskellige#Win unique card from Mousesack", "Active")]), &HashSet::new(), &HashMap::new());
        let echoes = ev.byid["sk_echoes"];
        assert_eq!(ev.steps[echoes].status, "Not started", "a gwent card win must not assume Echoes of the Past is done");
    }

    /// King's Gambit starts automatically off Possession and Lord of Undvik with no in-game prompt - the hold-off
    /// must say that plainly (which quest is already under way, and that finishing it is the trigger), not just
    /// name the event, or a player has no way to know finishing a conversation is the dangerous action.
    #[test]
    fn starting_kings_gambit_names_what_is_already_under_way() {
        let rd = route();
        let ev = evaluate(&rd, &state(&[("q203him", "Active")]), &HashSet::new(), &HashMap::new());
        let hold = dont_start(&ev).into_iter().find(|h| h.name == "Starting King's Gambit").expect("Possession in progress should hold off King's Gambit");
        assert!(hold.why.contains("Possession"), "why should name Possession as already under way: {}", hold.why);
        assert!(hold.why.contains("no choice or prompt to decline"), "why should warn there is no in-game prompt, from the verified note: {}", hold.why);
        assert!(hold.why.contains("Needs both Possession and Lord of Undvik"), "why should carry the verified trigger note: {}", hold.why);
    }

    /// `near` is only a proximity signal (this cutoff may be getting close) - for events with no verified `note`
    /// explaining the actual trigger, the hold-off must not claim the active step is what triggers the event, or
    /// it overclaims causation the way it did for King's Gambit's neighbors (Isle of Mists, Ugly Baby) before
    /// their own triggers were ever checked.
    #[test]
    fn an_unverified_event_near_an_active_step_does_not_claim_it_triggers_it() {
        let rd = route();
        let ev = evaluate(&rd, &state(&[("q206berserkers", "Active")]), &HashSet::new(), &HashMap::new());
        let hold = dont_start(&ev).into_iter().find(|h| h.name.contains("Ugly Baby")).expect("King's Gambit under way should flag the nearby Ugly Baby cutoff");
        assert!(hold.why.contains("King's Gambit"), "why should name King's Gambit as already under way: {}", hold.why);
        assert!(!hold.why.contains("triggers this"), "near is a proximity signal, not a confirmed trigger, without a verified note: {}", hold.why);
    }
}
