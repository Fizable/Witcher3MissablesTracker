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
}

#[derive(Deserialize, Clone)]
pub struct Pref {
    pub step: String,
    pub needs: Vec<String>,
    pub why: String,
}

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
        let near = def.near.iter().filter_map(|x| byid.get(x)).any(|&i| matches!(steps[i].status.as_str(), "Active" | "Done"));
        events.push(Ev { id: eid.clone(), def: def.clone(), fired, open, near });
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
        let mut why = format!("This would fail or lock: {}{}.", names.join("; "), if e.open.len() > 6 { "..." } else { "" });
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
    json!({"id": ev.steps[i].n.id, "title": short(&ev.steps[i].n.title)})
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

/// the route step that tracks this journal quest file, if any
pub fn step_for_short(ev: &Eval, short_name: &str) -> Option<usize> {
    (0..ev.steps.len()).find(|&i| ev.steps[i].n.files.iter().any(|f| f.split('#').next() == Some(short_name) || f.split('|').any(|x| x == short_name)))
}
