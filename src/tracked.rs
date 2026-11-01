//! The TRACKED payload.
//!
//! One quest, and only the reviewed facts that belong to it: its own live warnings, the quests
//! finishing it would close, its missable Gwent cards, and the one ending choice the plan still
//! has ahead. `payload` is the single entry point; every helper below is quest-scoped.

use crate::model::{self, Eval};
use serde_json::{json, Map, Value};
use std::collections::HashSet;

/// Everything the payload reads. `steps` are the same save-aware step payloads the window gets,
/// so a watch row cannot disagree with the quest page.
pub struct Input<'a> {
    pub ev: &'a Eval,
    pub short: &'a str,
    pub display: &'a str,
    pub status: &'a str,
    pub plan: Option<&'a Value>,
    pub steps: &'a [Value],
    pub card_report: &'a Value,
    pub guidance_on: bool,
}

/// The tracked quest the tracker cannot place on the route yet: name it, do not invent a step.
pub fn unknown() -> Value {
    json!({
        "short": "", "display": "a quest the tracker does not know yet", "status": "",
        "steps": [], "cutoffs": [], "watch": [], "cards": [], "choice": null
    })
}

/// The one source of truth for the TRACKED section.
pub fn payload(input: Input<'_>) -> Value {
    let step_ids: Vec<String> = open_steps(input.ev, input.short)
        .iter()
        .map(|&i| input.ev.steps[i].n.id.clone())
        .collect();
    let every_step = all_step_ids(input.ev, input.short);
    let cutoffs = cutoff_rows(input.ev, input.steps, input.short);
    let watch = watch_rows(input.steps, &every_step);
    let cards = missable_cards(input.card_report, &every_step);
    let choice = choice(input.ev, input.short, input.plan, input.guidance_on);
    json!({
        "short": input.short,
        "display": input.display,
        "status": input.status,
        "steps": step_ids,
        "cutoffs": cutoffs,
        "watch": watch,
        "cards": cards,
        "choice": choice,
    })
}

/// Route steps that belong to the tracked journal. Open steps come first, in route order. If
/// every step is finished (the save can still name a completed quest as tracked) the finished
/// steps are kept, so the TRACKED section always has the quest it says it is following.
fn open_steps(ev: &Eval, short: &str) -> Vec<usize> {
    let all: Vec<usize> = (0..ev.steps.len()).filter(|&i| model::tracks(&ev.steps[i].n, short)).collect();
    let open: Vec<usize> = all
        .iter()
        .copied()
        .filter(|&i| !matches!(ev.steps[i].status.as_str(), "Done" | "N/A"))
        .collect();
    if open.is_empty() { all } else { open }
}

/// Ids of every route step of the tracked quest, open or finished. A card or a cutoff belongs
/// to the quest even when the step that names it is already behind the player.
fn all_step_ids(ev: &Eval, short: &str) -> HashSet<String> {
    (0..ev.steps.len())
        .filter(|&i| model::tracks(&ev.steps[i].n, short))
        .map(|i| ev.steps[i].n.id.clone())
        .collect()
}

/// Live warnings *about* the tracked quest: a statuette-style window open now, a cutoff that
/// passed, a source not ready yet. The step payload is the same save-aware read the quest page
/// uses, so the tracked card cannot contradict the quest page.
fn watch_rows(steps: &[Value], ids: &HashSet<String>) -> Vec<Value> {
    let mut out: Vec<Value> = Vec::new();
    let mut seen: HashSet<String> = HashSet::new();
    for v in steps {
        let Some(id) = v.get("id").and_then(|x| x.as_str()) else { continue };
        if !ids.contains(id) {
            continue;
        }
        let Some(list) = v.get("watch").and_then(|x| x.as_array()) else { continue };
        for w in list {
            let Some(headline) = w.get("headline").and_then(|x| x.as_str()) else { continue };
            if !seen.insert(headline.to_string()) {
                continue;
            }
            let mut row = w.clone();
            row["step"] = json!(id);
            row["step_title"] = v.get("title").cloned().unwrap_or(Value::Null);
            out.push(row);
        }
    }
    out
}

/// Something the tracked quest closes down if the player finishes it now.
struct TrackedCutoff {
    level: &'static str,
    headline: String,
    quests: Vec<String>,
    details: Vec<String>,
}

/// Every reviewed way finishing this quest costs another open quest.
fn cutoffs(ev: &Eval, short_name: &str) -> Vec<TrackedCutoff> {
    let mut out: Vec<TrackedCutoff> = Vec::new();
    let mut seen: HashSet<String> = HashSet::new();
    for e in &ev.events {
        if e.fired {
            continue;
        }
        for (r, sts) in &e.def.fires {
            if r.split('#').next() != Some(short_name) {
                continue;
            }
            // open steps of the same quest do not count: finishing it does not fail it
            let others: Vec<usize> = e.open.iter().copied().filter(|&d| !model::tracks(&ev.steps[d].n, short_name)).collect();
            if others.is_empty() {
                continue;
            }
            let quests: Vec<String> = others.iter().take(8).map(|&d| model::short(&ev.steps[d].n.title).to_string()).collect();
            // say what the event waits for: an objective of this quest, its end, or (rarely) its start
            let headline = if r.contains('#') {
                format!("Its next step triggers \"{}\"", e.def.name)
            } else if sts.iter().all(|s| s == "Done") {
                format!("Finishing this triggers \"{}\"", e.def.name)
            } else {
                format!("This triggers \"{}\"", e.def.name)
            };
            if !seen.insert(headline.clone()) {
                continue;
            }
            // soft events are the same amber "warn" the alerts use
            let level = if e.def.soft { "warn" } else { "stop" };
            out.push(TrackedCutoff { level, headline, quests, details: Vec::new() });
        }
    }
    for s in &ev.steps {
        if !model::tracks(&s.n, short_name) {
            continue;
        }
        if let Some(h) = &s.held {
            let headline = "Recommended to wait".to_string();
            if !seen.insert(headline.clone()) {
                continue;
            }
            let quests: Vec<String> = h.blockers.iter().take(3).map(|&x| model::short(&ev.steps[x].n.title).to_string()).collect();
            out.push(TrackedCutoff { level: "warn", headline, quests, details: vec![h.why.clone()] });
        }
    }
    out
}

/// Quests this tracked quest would close down if it is finished now. Two reviewed sources feed
/// the same list: the route's loss events (`cutoffs`) and every live reviewed window whose
/// `closed_by` names this quest. The watch row is already read against the save, so a row whose
/// affected quest is finished is gone before it can reach the card.
fn cutoff_rows(ev: &Eval, steps: &[Value], short: &str) -> Vec<Value> {
    let mut out: Vec<Value> = Vec::new();
    let mut named: HashSet<String> = HashSet::new();
    for c in cutoffs(ev, short) {
        let quests: Vec<String> = c.quests.into_iter().filter(|q| named.insert(q.to_lowercase())).collect();
        if quests.is_empty() {
            continue;
        }
        out.push(json!({
            "level": c.level, "live": Value::Null, "headline": c.headline,
            "quests": quests, "details": c.details, "action": Value::Null,
        }));
    }
    let own = all_step_ids(ev, short);
    for v in steps {
        let Some(id) = v.get("id").and_then(|x| x.as_str()) else { continue };
        // A warning attached to one of the tracked quest's own steps is either about this quest
        // (already in `watch`) or about a different closer; it is not this quest closing another.
        if own.contains(id) {
            continue;
        }
        let Some(list) = v.get("watch").and_then(|x| x.as_array()) else { continue };
        for w in list {
            let closes = w.get("closed_by").and_then(|x| x.as_array()).into_iter().flatten()
                .filter_map(|x| x.as_str())
                .any(|x| x.split('#').next() == Some(short));
            let at = w.get("closes_at").and_then(|x| x.as_str())
                .map(|x| x.split('#').next() == Some(short)).unwrap_or(false);
            if !closes && !at {
                continue;
            }
            let Some(live) = w.get("live").and_then(|x| x.as_str()) else { continue };
            // Only a real window state is a cutoff this quest is closing. A refutation or an
            // unanswered note is not; neither is a window that is still ahead (already filtered
            // out of the step payload) or a settled row.
            if !matches!(live, "inside" | "open" | "check" | "passed" | "lost" | "later" | "not_yet") {
                continue;
            }
            let quests: Vec<String> = w.get("affected_titles").and_then(|x| x.as_array()).into_iter().flatten()
                .filter_map(|x| x.as_str())
                .filter(|q| named.insert(q.to_lowercase()))
                .map(String::from)
                .collect();
            if quests.is_empty() {
                continue;
            }
            let mut details: Vec<Value> = Vec::new();
            if let Some(x) = w.get("why").filter(|v| !v.is_null()) {
                details.push(x.clone());
            }
            if let Some(x) = w.get("live_note").filter(|v| !v.is_null()) {
                details.push(x.clone());
            }
            out.push(json!({
                "level": if matches!(live, "inside" | "open" | "check" | "passed" | "lost") { "stop" } else { "warn" },
                "live": live,
                "headline": w.get("headline").cloned().unwrap_or(Value::Null),
                "quests": quests,
                "details": details,
                "action": w.get("action").cloned().unwrap_or(Value::Null),
            }));
        }
    }
    out
}

/// Missable Gwent cards tied to the tracked quest: a one-time grant from one of its steps, a
/// window that opens there, or a window that closes when the quest advances. A card already in
/// the save's collection is not missable and is not repeated here.
fn missable_cards(card_report: &Value, ids: &HashSet<String>) -> Vec<Value> {
    let mut out: Vec<Value> = Vec::new();
    for card in card_report.get("cards").and_then(|x| x.as_array()).into_iter().flatten() {
        if card.get("owned").and_then(|x| x.as_str()) == Some("owned") {
            continue;
        }
        let w = card.get("window").cloned().unwrap_or(Value::Null);
        if w.get("kind").and_then(|x| x.as_str()) != Some("missable") {
            continue;
        }
        let step = w.get("step").and_then(|x| x.as_str()).unwrap_or("");
        let opens = w.get("opens").and_then(|x| x.get("step")).and_then(|x| x.as_str()).unwrap_or("");
        let source = card.get("source_step").and_then(|x| x.as_str()).unwrap_or("");
        if !ids.contains(step) && !ids.contains(opens) && !ids.contains(source) {
            continue;
        }
        let mut window = Map::new();
        for k in ["kind", "tier", "tier_rank", "step", "step_title", "event", "mechanism", "source", "opens"] {
            if let Some(x) = w.get(k) {
                window.insert(k.to_string(), x.clone());
            }
        }
        out.push(json!({
            "id": card.get("id").cloned().unwrap_or(Value::Null),
            "name": card.get("name").cloned().unwrap_or(Value::Null),
            "deck": card.get("deck").cloned().unwrap_or(Value::Null),
            "pack": card.get("pack").cloned().unwrap_or(Value::Null),
            "owned": card.get("owned").cloned().unwrap_or(Value::Null),
            "source_text": card.get("source_text").cloned().unwrap_or(Value::Null),
            "window_live": card.get("window_live").cloned().unwrap_or(Value::Null),
            "window": Value::Object(window),
        }));
    }
    // A window that is open now is the first thing to act on; the rest keep the index order.
    out.sort_by_key(|c| match c.get("window_live").and_then(|x| x.get("state")).and_then(|x| x.as_str()) {
        Some("active") => 0u8,
        Some("check") => 1,
        Some("lost") => 2,
        Some("ahead") => 3,
        _ => 4,
    });
    out
}

/// The ending-choice warning on the tracked quest card.
///
/// A consequential choice belongs to the quest the player is on, not to a separate queue entry
/// underneath it and not to a plan card. With guidance off the card carries only the constant
/// sentence, so no exact line, branch fact or ending id leaves the backend. With guidance on and a
/// selected goal it carries the reviewed line for that scene. A settled or unreachable plan step
/// says nothing: there is no action left to take.
fn choice(ev: &Eval, short: &str, plan: Option<&Value>, guidance_on: bool) -> Value {
    let Some(i) = (0..ev.steps.len()).find(|&i| {
        let s = &ev.steps[i];
        model::tracks(&s.n, short)
            && !matches!(s.status.as_str(), "Done" | "N/A")
            && s.n.ending_relevant
    }) else {
        return Value::Null;
    };
    let id = ev.steps[i].n.id.as_str();
    let step_plan = plan
        .and_then(|p| p.get("steps"))
        .and_then(|x| x.as_array())
        .and_then(|a| a.iter().find(|s| s.get("step").and_then(|x| x.as_str()) == Some(id)));
    if let Some(sp) = step_plan {
        if sp.get("state").and_then(|x| x.as_str()) != Some("ahead") {
            return Value::Null;
        }
    }
    if guidance_on {
        let lines: Vec<Value> = step_plan
            .and_then(|s| s.get("instructions"))
            .and_then(|x| x.as_array())
            .into_iter()
            .flatten()
            .filter_map(|row| {
                let line = row.get("instruction").and_then(|x| x.as_str())?;
                if line.is_empty() {
                    return None;
                }
                Some(json!({"line": line, "target": row.get("target").cloned().unwrap_or(Value::Null)}))
            })
            .collect();
        if !lines.is_empty() {
            return json!({"guided": true, "text": Value::Null, "lines": lines});
        }
    }
    json!({"guided": false, "text": "This choice affects an ending.", "lines": []})
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{self, EventDef, Node, RouteData};
    use crate::{read_json, Inner};
    use crate::save::QuestDb;
    use crate::targets::BranchGraph;
    use std::collections::HashMap;
    use std::path::PathBuf;

    fn node(id: &str, files: &[&str]) -> Node {
        Node {
            section: "Main".into(), id: id.into(), title: id.into(), lv: "20".into(),
            files: files.iter().map(|f| f.to_string()).collect(), hard: vec![],
            hard_facts: HashMap::new(), by: vec![], note: String::new(), kind: "side".into(),
            opt: false, when: vec![], order: 0, desc: "A line about the quest.".into(),
            branch: false, ending_relevant: false, start_known: true,
            provenance: "game_file".into(), review_reason: String::new(),
            review_source: String::new(), reviewed: String::new(),
        }
    }

    fn route(nodes: Vec<Node>) -> RouteData {
        RouteData {
            sections: vec!["Main".into()], nodes, events: vec![], prefs: vec![],
            conditional: HashSet::new(), flags: vec![], manual_audit: Value::Null,
        }
    }

    fn state(pairs: &[(&str, &str)]) -> HashMap<String, String> {
        pairs.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect()
    }

    fn step(id: &str, watch: Value) -> Value {
        json!({"id": id, "title": id, "watch": watch})
    }

    #[test]
    fn the_tracked_quest_names_every_open_quest_it_would_close() {
        let target = node("q402ciri", &["q402ciri"]);
        let mut brother = node("q401_v", &["q401_v"]);
        let mut soprano = node("q401_s", &["q401_s"]);
        brother.by = vec!["brothers_in_arms".into()];
        soprano.by = vec!["brothers_in_arms".into()];
        let mut rd = route(vec![target, brother, soprano]);
        rd.events.push(("brothers_in_arms".into(), EventDef {
            name: "The Isle of Mists".into(),
            fires: vec![("q402ciri".into(), vec!["Done".into()])],
            soft: false,
        }));
        let st = state(&[("q402ciri", "Active"), ("q401_v", "Active"), ("q401_s", "Active")]);
        let ev = model::evaluate(&rd, &st, &HashSet::new(), &HashMap::new(), &HashSet::new());
        let cuts = cutoffs(&ev, "q402ciri");
        assert_eq!(cuts.len(), 1, "one reviewed event, one chip");
        assert_eq!(cuts[0].level, "stop");
        assert_eq!(cuts[0].quests, vec!["q401_v", "q401_s"], "the chip names every open quest");
        assert!(cuts[0].headline.contains("The Isle of Mists"));
        // The event is the tracked quest's own; nothing else may claim it.
        assert!(cutoffs(&ev, "q401_v").is_empty());
        // A finished affected quest is not named: the save already settled it.
        let settled = state(&[("q402ciri", "Active"), ("q401_v", "Done"), ("q401_s", "Active")]);
        let ev = model::evaluate(&rd, &settled, &HashSet::new(), &HashMap::new(), &HashSet::new());
        assert_eq!(cutoffs(&ev, "q402ciri")[0].quests, vec!["q401_s"]);
    }

    #[test]
    fn the_choice_warning_lives_on_the_tracked_card() {
        let mut nd = node("q110postbattle", &["q110postbattle"]);
        nd.ending_relevant = true;
        let rd = route(vec![nd, node("q999plain", &["q999plain"])]);
        let st = HashMap::from([
            ("q110postbattle".to_string(), "Active".to_string()),
            ("q999plain".to_string(), "Active".to_string()),
        ]);
        let ev = model::evaluate(&rd, &st, &HashSet::new(), &HashMap::new(), &HashSet::new());
        // Guidance off: only the constant sentence, no line, no branch fact, no ending id.
        let off = choice(&ev, "q110postbattle", None, false);
        assert_eq!(off["guided"], false);
        assert_eq!(off["text"], "This choice affects an ending.");
        assert!(off["lines"].as_array().unwrap().is_empty());
        let text = serde_json::to_string(&off).unwrap().to_lowercase();
        for leak in ["ciri", "emperor", "radovid", "sorceress", "crown", "blood and wine", "bw_"] {
            assert!(!text.contains(leak), "the constant sentence must not name {leak}");
        }
        // Guidance on plus a goal: only the exact reviewed line, on this quest.
        let plan = json!({"steps": [{"step": "q110postbattle", "state": "ahead",
            "instructions": [{"instruction": "Velen.", "target": "bw_both_sisters"}]}]});
        let on = choice(&ev, "q110postbattle", Some(&plan), true);
        assert_eq!(on["guided"], true);
        assert_eq!(on["lines"][0]["line"], "Velen.");
        assert!(on["text"].is_null());
        // A settled plan step and a quest that does not carry the choice stay silent.
        let settled = json!({"steps": [{"step": "q110postbattle", "state": "settled"}]});
        assert!(choice(&ev, "q110postbattle", Some(&settled), true).is_null());
        assert!(choice(&ev, "q999plain", Some(&plan), true).is_null());
    }

    #[test]
    fn the_tracked_card_carries_only_its_own_gwent_cards() {
        let report = json!({"cards": [
            {"id": "card_dandelion", "name": "Dandelion", "deck": "Neutral", "pack": "base",
             "owned": "not_owned", "source_text": "Scripted quest grant", "source_step": "sq301triss",
             "window": {"kind": "missable", "tier": "community", "tier_rank": "B",
                        "step": "sq301triss", "step_title": "A Matter of Life and Death",
                        "mechanism": "one-time grant", "opens": {"step": "sq301triss"}},
             "window_live": {"state": "active", "tone": "red", "label": "OPEN NOW - COMMUNITY WINDOW"}},
            {"id": "card_geralt", "name": "Geralt of Rivia", "deck": "Neutral", "pack": "base",
             "owned": "not_owned", "source_text": "Quest loot", "source_step": "cgtalar",
             "window": {"kind": "missable", "tier": "community", "tier_rank": "B", "step": "cgtalar"},
             "window_live": {"state": "ahead", "tone": "amber", "label": "OPEN LATER"}},
            {"id": "card_owned", "name": "Owned card", "deck": "Neutral", "pack": "base",
             "owned": "owned", "source_text": "x", "source_step": "sq301triss",
             "window": {"kind": "missable", "step": "sq301triss"},
             "window_live": {"state": "owned", "tone": "green", "label": "OWNED"}},
            {"id": "card_no_window", "name": "No window", "deck": "Nilfgaard", "pack": "base",
             "owned": "not_owned", "source_text": "x", "source_step": "sq301triss",
             "window": {"kind": "none"}, "window_live": {"state": "none"}}
        ]});
        let ids = HashSet::from(["sq301triss".to_string()]);
        let rows = missable_cards(&report, &ids);
        assert_eq!(rows.len(), 1, "only the unowned missable card from this quest: {rows:?}");
        assert_eq!(rows[0]["id"], "card_dandelion");
        assert_eq!(rows[0]["window_live"]["label"], "OPEN NOW - COMMUNITY WINDOW");
        assert_eq!(rows[0]["window"]["step_title"], "A Matter of Life and Death");
    }

    fn tracker_with_shipped_data() -> Inner {
        let data = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("data");
        Inner {
            app_dir: std::env::temp_dir(),
            route: model::load_route(&read_json(&data.join("route.json")).unwrap()).unwrap(),
            db: QuestDb { quests: vec![], display: vec![] },
            db_error: String::new(),
            game_dir: None,
            display: vec![
                ("q402ciri".into(), "The Isle of Mists".into()),
                ("sq301triss".into(), "A Matter of Life and Death".into()),
                ("q110postbattle".into(), "Blood on the Battlefield".into()),
            ],
            derived: read_json(&data.join("derived.json")).unwrap(),
            graph: json!({}),
            qtitles: HashMap::new(),
            endings: read_json(&data.join("endings.json")).unwrap(),
            outcomes: read_json(&data.join("outcomes.json")).unwrap(),
            branches: BranchGraph::from_json(&read_json(&data.join("branches.json")).unwrap()),
            ending_branch_ids: HashSet::new(),
            cards: crate::cards::CardIndex::from_json(&read_json(&data.join("gwent_cards.json")).unwrap()),
            coverage: json!({}),
            exclusive: json!({"edges": []}),
            selected: vec![],
            guidance_on: false,
            setup_v1: true,
            card_manual: HashMap::from([("card_dandelion".to_string(), false)]),
            state: HashMap::new(),
            objective_guids: HashMap::new(),
            objectives: HashMap::new(),
            tracked: Some("guid".into()),
            tracked_file: None,
            highlighted: None,
            facts: HashSet::new(),
            save_path: None,
            save_mtime: None,
            ok_mtime: None,
            error: String::new(),
            card_cache: None,
            ticks: HashSet::new(),
            level: 0,
            flags: HashMap::new(),
            saves_override: None,
            game_override: None,
            folder_msg: String::new(),
        }
    }

    /// The shipped route, derived index and card index through the real `tracked_json`, without a
    /// save file: the save state is set directly, so the cutoff and card aggregation is exercised
    /// on the data the release actually ships.
    #[test]
    fn the_tracked_payload_reads_the_shipped_route_and_card_data() {
        let mut inner = tracker_with_shipped_data();
        inner.tracked_file = Some("q402ciri".into());
        inner.state = HashMap::from([
            ("q402ciri".to_string(), "Active".to_string()),
            ("q402velenallies".to_string(), "Active".to_string()),
            ("q402novigradallies".to_string(), "Not started".to_string()),
        ]);
        let rt = inner.effective_route();
        let ev = model::evaluate(&rt, &inner.state, &HashSet::new(), &HashMap::new(), &HashSet::new());
        let done_q = inner.done_quests(&ev);
        let mut steps: Vec<Value> = (0..ev.steps.len()).map(|i| model::step_json(&rt, &ev, i)).collect();
        for (i, s) in steps.iter_mut().enumerate() {
            inner.attach_derived(s, &ev.steps[i], &done_q);
        }
        let statuses: HashMap<String, String> = ev.steps.iter().map(|s| (s.n.id.clone(), s.status.clone())).collect();
        let card_report = inner.cards.report(None, true, "", &inner.facts, &inner.card_manual, &statuses);
        let tr = inner.tracked_json(&ev, None, &steps, &card_report);
        assert_eq!(tr["short"], "q402ciri");
        assert_eq!(tr["display"], "The Isle of Mists");
        let cuts = tr["cutoffs"].as_array().unwrap();
        assert_eq!(cuts.len(), 1, "the shipped Isle of Mists edge: {tr}");
        let named: Vec<String> = cuts[0]["quests"].as_array().unwrap().iter().filter_map(|x| x.as_str()).map(|x| x.to_lowercase()).collect();
        assert!(named.iter().any(|x| x == "brothers in arms: velen"), "names: {named:?}");
        assert!(named.iter().any(|x| x == "brothers in arms: novigrad"), "names: {named:?}");

        // A quest with a reviewed missable card: the shipped Dandelion row, unowned and its window
        // open on the tracked step.
        inner.tracked_file = Some("sq301triss".into());
        inner.state = HashMap::from([("sq301triss".to_string(), "Active".to_string())]);
        let rt = inner.effective_route();
        let ev = model::evaluate(&rt, &inner.state, &HashSet::new(), &HashMap::new(), &HashSet::new());
        let done_q = inner.done_quests(&ev);
        let mut steps: Vec<Value> = (0..ev.steps.len()).map(|i| model::step_json(&rt, &ev, i)).collect();
        for (i, s) in steps.iter_mut().enumerate() {
            inner.attach_derived(s, &ev.steps[i], &done_q);
        }
        let statuses: HashMap<String, String> = ev.steps.iter().map(|s| (s.n.id.clone(), s.status.clone())).collect();
        let card_report = inner.cards.report(None, true, "", &inner.facts, &inner.card_manual, &statuses);
        let tr = inner.tracked_json(&ev, None, &steps, &card_report);
        let rows = tr["cards"].as_array().unwrap();
        let dandelion = rows.iter().find(|c| c["id"] == "card_dandelion")
            .unwrap_or_else(|| panic!("Dandelion must belong to this quest: {tr}"));
        assert_eq!(dandelion["window_live"]["state"], "active");
        assert_eq!(dandelion["window"]["step"], "sq301triss");
        assert!(rows.iter().all(|c| c["window"]["step"] == "sq301triss" || c["window"]["opens"]["step"] == "sq301triss"),
                "every listed card must belong to the tracked quest: {tr}");
    }

    #[test]
    fn a_tracked_quest_names_the_quests_the_save_still_has_open() {
        let ev = model::evaluate(
            &route(vec![node("q402ciri", &["q402ciri"])]),
            &state(&[("q402ciri", "Active")]),
            &HashSet::new(), &HashMap::new(), &HashSet::new(),
        );
        let steps = vec![
            step("q402ciri", json!([])),
            step("brother", json!([{
                "id": "brothers", "live": "inside", "level": "stop", "headline": "Brothers in Arms: Velen",
                "affected": ["brother"], "affected_titles": ["Brothers in Arms: Velen"],
                "closed_by": ["q402ciri"], "closed_by_titles": ["The Isle of Mists"],
                "why": "the closer is in the log", "action": "Finish it before The Isle of Mists",
                "live_note": "In this save: The Isle of Mists is active."
            }])),
            step("other", json!([{
                "id": "other_cut", "live": "inside", "headline": "A different closer",
                "affected": ["other"], "affected_titles": ["Some Other Quest"],
                "closed_by": ["q999other"], "closed_by_titles": ["A Different Closer"]
            }])),
        ];
        let rows = cutoff_rows(&ev, &steps, "q402ciri");
        assert_eq!(rows.len(), 1, "one row, names every open quest: {rows:?}");
        assert_eq!(rows[0]["level"], "stop", "a window already closing is urgent");
        assert_eq!(rows[0]["quests"], json!(["Brothers in Arms: Velen"]));
        assert_eq!(rows[0]["action"], "Finish it before The Isle of Mists");
        assert!(rows[0]["details"][1].as_str().unwrap().contains("The Isle of Mists is active"));
        // The tracked quest's own step never becomes a warning about itself.
        let own = cutoff_rows(&ev, &[step("q402ciri", json!([{
            "id": "self", "live": "inside", "headline": "self",
            "affected": ["q402ciri"], "affected_titles": ["The Isle of Mists"],
            "closed_by": ["q402ciri"], "closed_by_titles": ["The Isle of Mists"]
        }]))], "q402ciri");
        assert!(own.is_empty(), "a quest does not warn that it cuts itself off");
    }
}
