//! Terminal outcomes: the reviewed `data/outcomes.json` rows, evaluated against the save.
//!
//! A target in `endings.json` may point at an outcome instead of carrying its own `requires` and
//! `guidance`. The outcome owns the terminal facts, the exact line and the journal description; the
//! target only says the player wants that ending. This keeps the matrix, the picker and the detail
//! pane from disagreeing about the same goal.
//!
//! Nothing here invents evidence. A requirement resolves through the fact the save has, the route
//! step that has to be finished for an absent fact to prove the negative branch, or `unknown` when
//! the save or the route cannot answer. The default view never receives an instruction or a label:
//! `get_outcomes` is a separate, spoiler-gated call.

use crate::model::Eval;
use crate::targets::{GuidanceRow, RowEval, TargetEval};
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};

const PACK_ORDER: [&str; 5] = ["base", "ep1", "bob", "other_dlc", "gwent"];

#[derive(Clone)]
pub struct OutcomeEval {
    pub state: String,
    pub reason: Option<String>,
    pub blocked_by: Vec<Value>,
    pub rows: Vec<RowEval>,
}

fn pack_rank(pack: &str) -> usize {
    PACK_ORDER.iter().position(|p| *p == pack).unwrap_or(PACK_ORDER.len())
}

pub fn all_ids(doc: &Value) -> Vec<String> {
    let mut ids: Vec<String> = doc
        .get("outcomes")
        .and_then(|x| x.as_object())
        .map(|m| m.keys().cloned().collect())
        .unwrap_or_default();
    ids.sort();
    ids
}

pub fn label(doc: &Value, id: &str) -> String {
    doc.get("outcomes")
        .and_then(|x| x.get(id))
        .and_then(|x| x.get("label"))
        .and_then(|x| x.as_str())
        .unwrap_or(id)
        .to_string()
}

pub fn target_outcome(endings: &Value, tid: &str) -> Option<String> {
    endings
        .get("targets")
        .and_then(|x| x.get(tid))
        .and_then(|x| x.get("outcome"))
        .and_then(|x| x.as_str())
        .map(String::from)
}

fn target_for_outcome(endings: &Value, oid: &str) -> Option<String> {
    let mut ids: Vec<String> = endings
        .get("targets")
        .and_then(|x| x.as_object())
        .map(|m| {
            m.iter()
                .filter(|(_, t)| t.get("outcome").and_then(|x| x.as_str()) == Some(oid))
                .map(|(id, _)| id.clone())
                .collect()
        })
        .unwrap_or_default();
    ids.sort();
    ids.into_iter().next()
}

/// Every branch an outcome names in its requirements or guidance. Used to mark the detail pane's
/// scene choices as ending-relevant, including outcomes that are not currently selected.
pub fn branch_ids(doc: &Value) -> HashSet<String> {
    let mut out = HashSet::new();
    for outcome in doc.get("outcomes").and_then(|x| x.as_object()).into_iter().flat_map(|m| m.values()) {
        for key in ["requires", "guidance"] {
            for row in outcome.get(key).and_then(|x| x.as_array()).into_iter().flatten() {
                if let Some(bid) = row
                    .get("branch")
                    .and_then(|x| x.as_str())
                    .or_else(|| row.get("source").and_then(|x| x.get("branch")).and_then(|x| x.as_str()))
                {
                    if !bid.is_empty() {
                        out.insert(bid.to_string());
                    }
                }
            }
        }
    }
    out
}

fn step_title(ev: &Eval, id: &str) -> String {
    ev.byid
        .get(id)
        .map(|&i| ev.steps[i].n.title.clone())
        .filter(|t| !t.is_empty())
        .unwrap_or_else(|| id.to_string())
}

fn status_of(s: &crate::model::Step) -> &str {
    if s.tick_disagrees { s.journal.as_str() } else { s.status.as_str() }
}

fn finished(s: &crate::model::Step) -> bool {
    matches!(status_of(s), "Done" | "Assumed")
}

fn closed(s: &crate::model::Step) -> bool {
    matches!(status_of(s), "Done" | "Assumed" | "Failed" | "N/A")
}

#[derive(Clone, Copy, PartialEq)]
enum Req {
    Met,
    Open,
    Closed,
    Unknown,
}

fn evaluate_req(req: &Value, ev: &Eval, facts: &HashSet<String>, save_ok: bool) -> Req {
    let Some(fact) = req.get("fact").and_then(|x| x.as_str()) else { return Req::Unknown };
    let want = req.get("value").and_then(|x| x.as_bool()).unwrap_or(true);
    let present = facts.contains(fact);
    let step = req
        .get("source")
        .and_then(|x| x.get("step"))
        .and_then(|x| x.as_str())
        .unwrap_or("");
    let step = ev.byid.get(step).map(|&i| &ev.steps[i]);
    if !save_ok {
        return Req::Unknown;
    }
    if want {
        if present {
            Req::Met
        } else if let Some(s) = step {
            if s.lost || closed(s) { Req::Closed } else { Req::Open }
        } else {
            Req::Unknown
        }
    } else if present {
        Req::Closed
    } else if let Some(s) = step {
        if s.lost || matches!(status_of(s), "Failed" | "N/A") {
            Req::Unknown
        } else if finished(s) {
            Req::Met
        } else {
            Req::Open
        }
    } else {
        Req::Unknown
    }
}

fn blocker(req: &Value, ev: &Eval) -> Value {
    let fact = req.get("fact").and_then(|x| x.as_str()).unwrap_or("");
    let step = req
        .get("source")
        .and_then(|x| x.get("step"))
        .and_then(|x| x.as_str())
        .unwrap_or("");
    json!({
        "kind": "fact",
        "id": fact,
        "value": req.get("value").and_then(|x| x.as_bool()).unwrap_or(true),
        "step": step,
        "title": step_title(ev, step),
        "source": req.get("source").cloned().unwrap_or(Value::Null),
    })
}

fn note_for(state: &str) -> Option<String> {
    match state {
        "settled" => Some("In this save: this outcome is already set.".into()),
        "unreachable" => Some("In this save: this choice is already behind you.".into()),
        "unknown" => Some("The tracker cannot decide this step from the save and the branch data.".into()),
        _ => None,
    }
}

fn row_state(row: &GuidanceRow, row_facts: &[String], save_facts: &HashSet<String>, outcome: &str, ev: &Eval, save_ok: bool) -> String {
    if outcome == "met" {
        return "settled".into();
    }
    if !row_facts.is_empty() && row_facts.iter().all(|f| save_facts.contains(f)) {
        return "settled".into();
    }
    if !save_ok {
        return "unknown".into();
    }
    if outcome == "impossible" {
        return "unreachable".into();
    }
    let Some(&i) = ev.byid.get(&row.step) else { return "unknown".into() };
    let s = &ev.steps[i];
    if s.lost || closed(s) {
        "unreachable".into()
    } else {
        "ahead".into()
    }
}

fn evaluate_one(
    outcome: &Value,
    ev: &Eval,
    facts: &HashSet<String>,
    save_ok: bool,
) -> OutcomeEval {
    let requires = outcome.get("requires").and_then(|x| x.as_array()).cloned().unwrap_or_default();
    let mut first_closed: Option<Value> = None;
    let mut any_unknown = false;
    let mut all_met = true;
    for req in &requires {
        match evaluate_req(req, ev, facts, save_ok) {
            Req::Met => {}
            Req::Open => all_met = false,
            Req::Closed => {
                all_met = false;
                if first_closed.is_none() {
                    first_closed = Some(req.clone());
                }
            }
            Req::Unknown => {
                all_met = false;
                any_unknown = true;
            }
        }
    }

    let (state, reason, blocked_by) = if let Some(req) = first_closed {
        let fact = req.get("fact").and_then(|x| x.as_str()).unwrap_or("");
        let want = req.get("value").and_then(|x| x.as_bool()).unwrap_or(true);
        let step = req.get("source").and_then(|x| x.get("step")).and_then(|x| x.as_str()).unwrap_or("");
        let title = step_title(ev, step);
        let text = if want {
            format!("The {title} step is already behind this save and does not set {fact}.")
        } else {
            format!("The {title} step is already behind this save and set {fact}.")
        };
        ("impossible".to_string(), Some(text), vec![blocker(&req, ev)])
    } else if all_met {
        ("met".to_string(), None, Vec::new())
    } else if any_unknown {
        (
            "unknown".to_string(),
            Some("The save or the route cannot decide whether this outcome is still reachable.".into()),
            Vec::new(),
        )
    } else {
        ("open".to_string(), None, Vec::new())
    };

    let mut rows: Vec<RowEval> = Vec::new();
    for value in outcome.get("guidance").and_then(|x| x.as_array()).into_iter().flatten() {
        let Some(step) = value.get("step").and_then(|x| x.as_str()) else { continue };
        let Some(file) = value.get("source").and_then(|x| x.get("file")).and_then(|x| x.as_str()) else { continue };
        let Some(locid) = value.get("source").and_then(|x| x.get("locid")).and_then(|x| x.as_i64()) else { continue };
        let row = GuidanceRow {
            step: step.to_string(),
            kind: value.get("kind").and_then(|x| x.as_str()).unwrap_or("scene_choice").to_string(),
            branch: value.get("branch").and_then(|x| x.as_str()).unwrap_or("").to_string(),
            instruction: value.get("instruction").and_then(|x| x.as_str()).unwrap_or("").to_string(),
            file: file.to_string(),
            locid,
        };
        let row_facts: Vec<String> = value
            .get("facts")
            .and_then(|x| x.as_array())
            .map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect())
            .unwrap_or_default();
        let row_status = row_state(&row, &row_facts, facts, &state, ev, save_ok);
        rows.push(RowEval {
            row,
            facts: row_facts,
            note: note_for(&row_status),
            state: row_status,
        });
    }

    OutcomeEval {
        state,
        reason,
        blocked_by,
        rows,
    }
}

/// Evaluate every outcome in `outcomes.json`, then apply `selection: one` group precedence.
pub fn evaluate_all(
    doc: &Value,
    ev: &Eval,
    facts: &HashSet<String>,
    save_ok: bool,
) -> HashMap<String, OutcomeEval> {
    let mut out = HashMap::new();
    for (oid, outcome) in doc.get("outcomes").and_then(|x| x.as_object()).into_iter().flatten() {
        out.insert(oid.clone(), evaluate_one(outcome, ev, facts, save_ok));
    }
    for group in doc.get("groups").and_then(|x| x.as_object()).into_iter().flat_map(|m| m.values()) {
        let members: Vec<String> = group
            .get("outcomes")
            .and_then(|x| x.as_array())
            .map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect())
            .unwrap_or_default();
        let met: Vec<String> = members
            .iter()
            .filter(|oid| out.get(*oid).map(|e| e.state == "met").unwrap_or(false))
            .cloned()
            .collect();
        if met.len() != 1 {
            continue;
        }
        let winner = met[0].clone();
        let winner_label = label(doc, &winner);
        let group_label = group.get("label").and_then(|x| x.as_str()).unwrap_or("this group");
        for oid in &members {
            if *oid == winner {
                continue;
            }
            let Some(e) = out.get_mut(oid) else { continue };
            if e.state == "met" {
                continue;
            }
            e.state = "impossible".into();
            e.reason = Some(format!(
                "{winner_label} is the outcome this save took in {group_label}."
            ));
            e.blocked_by.push(json!({
                "kind": "outcome",
                "id": winner,
                "title": winner_label,
            }));
            for row in &mut e.rows {
                if !row.facts.iter().all(|f| facts.contains(f)) {
                    row.state = "unreachable".into();
                    row.note = note_for("unreachable");
                }
            }
        }
    }
    out
}

pub fn evaluate_targets(
    endings: &Value,
    doc: &Value,
    ev: &Eval,
    facts: &HashSet<String>,
    save_ok: bool,
) -> HashMap<String, TargetEval> {
    let evals = evaluate_all(doc, ev, facts, save_ok);
    let mut out = HashMap::new();
    for (tid, target) in endings.get("targets").and_then(|x| x.as_object()).into_iter().flatten() {
        let Some(oid) = target.get("outcome").and_then(|x| x.as_str()) else { continue };
        let status = target.get("guidance_status").and_then(|x| x.as_str()).unwrap_or("");
        if status != "guided" {
            out.insert(
                tid.clone(),
                TargetEval {
                    state: "not_guided_yet".into(),
                    reason: target.get("guidance_reason").and_then(|x| x.as_str()).map(String::from)
                        .or_else(|| Some("This goal has no reviewed guidance yet.".into())),
                    blocked_by: Vec::new(),
                    rows: Vec::new(),
                },
            );
            continue;
        }
        let Some(e) = evals.get(oid) else {
            out.insert(
                tid.clone(),
                TargetEval {
                    state: "unknown".into(),
                    reason: Some(format!("The reviewed outcome {oid} is missing from this build.")),
                    blocked_by: Vec::new(),
                    rows: Vec::new(),
                },
            );
            continue;
        };
        let state = match e.state.as_str() {
            "met" => "settled",
            "open" => "reachable",
            "impossible" => "impossible",
            _ => "unknown",
        };
        out.insert(
            tid.clone(),
            TargetEval {
                state: state.into(),
                reason: e.reason.clone(),
                blocked_by: e.blocked_by.clone(),
                rows: e.rows.clone(),
            },
        );
    }
    out
}

/// The reviewed one-of groups, as `(group id, label, member outcome ids)`.
/// Both conflict checks and the matrix read this, so group membership has one owner.
fn group_members(doc: &Value) -> Vec<(String, String, Vec<String>)> {
    let mut out = Vec::new();
    for (gid, group) in doc.get("groups").and_then(|x| x.as_object()).into_iter().flatten() {
        let members: Vec<String> = group
            .get("outcomes")
            .and_then(|x| x.as_array())
            .map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect())
            .unwrap_or_default();
        let label = group.get("label").and_then(|x| x.as_str()).unwrap_or(gid).to_string();
        out.push((gid.clone(), label, members));
    }
    out
}

/// The outcome each selected target names, in the same shape the planner and matrix use.
pub fn selected_outcomes(endings: &Value, selected: &[String]) -> HashMap<String, String> {
    selected
        .iter()
        .filter_map(|tid| target_outcome(endings, tid).map(|oid| (tid.clone(), oid)))
        .collect()
}

fn split_prefix<'a>(value: &'a str, prefix: &str) -> &'a str {
    value.strip_prefix(prefix).unwrap_or(value)
}

/// Two selected targets that name different outcomes in one `selection: one` group, or that are
/// connected by a reviewed edge in `exclusive.json`, cannot both be achieved in this run. This is a
/// reviewed selection conflict, not a claim that the save is broken.
pub fn selected_conflicts(
    doc: &Value,
    exclusive: &Value,
    selected: &[String],
    selected_outcomes: &HashMap<String, String>,
) -> Vec<Value> {
    let mut out = Vec::new();
    for (gid, label, members) in group_members(doc) {
        let picked: Vec<(String, String)> = selected
            .iter()
            .filter_map(|tid| selected_outcomes.get(tid).map(|oid| (tid.clone(), oid.clone())))
            .filter(|(_, oid)| members.contains(oid))
            .collect();
        let distinct: HashSet<String> = picked.iter().map(|(_, oid)| oid.clone()).collect();
        if distinct.len() > 1 {
            out.push(json!({
                "kind": "outcome_group",
                "group": gid,
                "label": label,
                "targets": picked.iter().map(|(tid, _)| tid).collect::<Vec<_>>(),
                "outcomes": picked.iter().map(|(_, oid)| oid).collect::<Vec<_>>(),
                "reason": "The selected goals are different outcomes in the same one-of group; one save cannot take both.",
            }));
        }
    }
    let mut seen: HashSet<(String, String)> = HashSet::new();
    for edge in exclusive.get("edges").and_then(|x| x.as_array()).into_iter().flatten() {
        let kind = edge.get("kind").and_then(|x| x.as_str()).unwrap_or("");
        let a = edge.get("a").and_then(|x| x.as_str()).unwrap_or("");
        let b = edge.get("b").and_then(|x| x.as_str()).unwrap_or("");
        if a.is_empty() || b.is_empty() {
            continue;
        }
        let (hit_a, hit_b) = match kind {
            "target" => {
                let a = split_prefix(a, "target:");
                let b = split_prefix(b, "target:");
                (selected.iter().any(|t| t == a), selected.iter().any(|t| t == b))
            }
            "outcome" => {
                let a = split_prefix(a, "outcome:");
                let b = split_prefix(b, "outcome:");
                (
                    selected_outcomes.values().any(|o| o == a),
                    selected_outcomes.values().any(|o| o == b),
                )
            }
            _ => (false, false),
        };
        if !hit_a || !hit_b {
            continue;
        }
        let mut pair = [a.to_string(), b.to_string()];
        pair.sort();
        if !seen.insert((pair[0].clone(), pair[1].clone())) {
            continue;
        }
        let a_clean = split_prefix(a, if kind == "target" { "target:" } else { "outcome:" });
        let b_clean = split_prefix(b, if kind == "target" { "target:" } else { "outcome:" });
        let mut hit_targets: Vec<String> = Vec::new();
        for tid in selected {
            let hit = match kind {
                "target" => tid == a_clean || tid == b_clean,
                "outcome" => selected_outcomes
                    .get(tid)
                    .map(|oid| oid == a_clean || oid == b_clean)
                    .unwrap_or(false),
                _ => false,
            };
            if hit {
                hit_targets.push(tid.clone());
            }
        }
        out.push(json!({
            "kind": "exclusive",
            "a": a,
            "b": b,
            "targets": hit_targets,
            "reason": edge.get("reason").and_then(|x| x.as_str()).unwrap_or("These outcomes cannot both happen in one run."),
            "mechanism": edge.get("mechanism").cloned().unwrap_or(Value::Null),
            "evidence": edge.get("evidence").cloned().unwrap_or_else(|| json!([])),
        }));
    }
    out
}

/// Two outcomes in one group that are both set in the save. This means the reviewed partition or the
/// save is inconsistent; it is not a selection conflict.
pub fn save_conflicts(doc: &Value, evals: &HashMap<String, OutcomeEval>) -> Vec<Value> {
    let mut out = Vec::new();
    for (gid, label, members) in group_members(doc) {
        let met: Vec<String> = members
            .iter()
            .filter(|oid| evals.get(*oid).map(|e| e.state == "met").unwrap_or(false))
            .cloned()
            .collect();
        if met.len() > 1 {
            out.push(json!({
                "kind": "outcome_group",
                "group": gid,
                "label": label,
                "outcomes": met,
                "reason": "Two terminal outcomes in this group are set in the save; the reviewed partition or the save is inconsistent.",
            }));
        }
    }
    out
}

pub fn matrix(
    endings: &Value,
    doc: &Value,
    exclusive: &Value,
    ev: &Eval,
    facts: &HashSet<String>,
    save_ok: bool,
    selected_targets: &[String],
) -> Value {
    let evals = evaluate_all(doc, ev, facts, save_ok);
    let selected: HashSet<String> = selected_targets.iter().cloned().collect();
    let mut groups: Vec<Value> = Vec::new();
    for (gid, group) in doc.get("groups").and_then(|x| x.as_object()).into_iter().flatten() {
        let pack = group.get("pack").and_then(|x| x.as_str()).unwrap_or("");
        let members: Vec<Value> = group
            .get("outcomes")
            .and_then(|x| x.as_array())
            .into_iter()
            .flatten()
            .filter_map(|x| x.as_str())
            .map(|oid| {
                let e = evals.get(oid);
                let target_id = target_for_outcome(endings, oid);
                json!({
                    "id": oid,
                    "label": label(doc, oid),
                    "pack": doc.get("outcomes").and_then(|x| x.get(oid)).and_then(|x| x.get("pack")).and_then(|x| x.as_str()).unwrap_or(pack),
                    "state": e.map(|x| x.state.as_str()).unwrap_or("unknown"),
                    "reason": e.and_then(|x| x.reason.clone()),
                    "blocked_by": e.map(|x| x.blocked_by.clone()).unwrap_or_default(),
                    "guidance_status": doc.get("outcomes").and_then(|x| x.get(oid)).and_then(|x| x.get("guidance_status")).and_then(|x| x.as_str()).unwrap_or(""),
                    "target_id": target_id,
                    "selected": target_id.as_ref().map(|t| selected.contains(t)).unwrap_or(false),
                })
            })
            .collect();
        groups.push(json!({
            "id": gid,
            "label": group.get("label").and_then(|x| x.as_str()).unwrap_or(gid),
            "pack": pack,
            "selection": group.get("selection").and_then(|x| x.as_str()).unwrap_or("one"),
            "outcomes": members,
        }));
    }
    groups.sort_by_key(|g| {
        let pack = g.get("pack").and_then(|x| x.as_str()).unwrap_or("");
        (pack_rank(pack), g.get("id").and_then(|x| x.as_str()).unwrap_or("").to_string())
    });
    let selected_outcomes = selected_outcomes(endings, selected_targets);
    let mut conflicts = save_conflicts(doc, &evals);
    conflicts.extend(selected_conflicts(doc, exclusive, selected_targets, &selected_outcomes));
    json!({
        "version": 1,
        "note": doc.get("note").cloned().unwrap_or(Value::Null),
        "groups": groups,
        "selected": selected_targets,
        "selected_outcomes": selected_targets
            .iter()
            .filter_map(|tid| selected_outcomes.get(tid).cloned())
            .collect::<Vec<_>>(),
        "conflicts": conflicts,
        "counts": {
            "groups": doc.get("groups").and_then(|x| x.as_object()).map(|m| m.len()).unwrap_or(0),
            "outcomes": all_ids(doc).len(),
            "targets": endings.get("targets").and_then(|x| x.as_object()).map(|m| m.len()).unwrap_or(0),
        },
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{Eval, Node, Step};
    use std::collections::HashMap;

    fn node(id: &str) -> Node {
        Node {
            section: "Main".into(), id: id.into(), title: format!("Step {id}"), lv: String::new(),
            files: vec![id.into()], hard: vec![], hard_facts: HashMap::new(), by: vec![],
            note: String::new(), kind: "main".into(), opt: false, when: vec![], order: 0,
            desc: String::new(), branch: false, ending_relevant: false,
            start_known: true, provenance: "game_file".into(), review_reason: String::new(),
            review_source: String::new(), reviewed: String::new(),
        }
    }

    fn eval(steps: &[(&str, &str)]) -> Eval {
        let mut e = Eval { steps: Vec::new(), byid: HashMap::new(), events: Vec::new() };
        for (i, (id, status)) in steps.iter().enumerate() {
            e.steps.push(Step {
                n: node(id), status: status.to_string(), journal: status.to_string(), manual: false,
                locked: vec![], held: None, lost: false, evs: vec![], cond_unknown: false,
                tick_disagrees: false, frontier: "available",
            });
            e.byid.insert(id.to_string(), i);
        }
        e
    }

    fn doc() -> Value {
        json!({
            "groups": {
                "main_ciri": {"pack": "base", "label": "Ciri", "selection": "one",
                              "outcomes": ["ciri_witcher", "ciri_empress"]}
            },
            "outcomes": {
                "ciri_witcher": {
                    "group": "main_ciri", "pack": "base", "label": "Ciri lives", "guidance_status": "guided",
                    "requires": [
                        {"fact": "q110_to_emperor", "value": false,
                         "source": {"kind": "phase_fact", "step": "q110postbattle", "file": "q110.w2phase", "fact": "q110_to_emperor"}},
                        {"fact": "q502_ciri_survives", "value": true,
                         "source": {"kind": "phase_fact", "step": "q502avallach", "file": "q502.w2phase", "fact": "q502_ciri_survives"}}
                    ],
                    "guidance": [{"step": "q110postbattle", "kind": "scene_choice", "branch": "b1",
                                  "instruction": "Velen.", "facts": [], "source": {"kind": "scene_choice", "file": "s.w2scene", "locid": 1}}]
                },
                "ciri_empress": {
                    "group": "main_ciri", "pack": "base", "label": "Ciri empress", "guidance_status": "not_guided_yet",
                    "requires": [{"fact": "q110_to_emperor", "value": true,
                                  "source": {"kind": "phase_fact", "step": "q110postbattle", "file": "q110.w2phase", "fact": "q110_to_emperor"}}],
                    "guidance": []
                }
            }
        })
    }

    #[test]
    fn an_absent_fact_only_proves_the_negative_branch_after_the_step_finishes() {
        let d = doc();
        let ev = eval(&[("q110postbattle", "Active"), ("q502avallach", "Not started")]);
        let e = evaluate_all(&d, &ev, &HashSet::new(), true);
        assert_eq!(e["ciri_witcher"].state, "open");
        assert_eq!(e["ciri_witcher"].rows[0].state, "ahead");

        let ev = eval(&[("q110postbattle", "Done"), ("q502avallach", "Not started")]);
        let e = evaluate_all(&d, &ev, &HashSet::new(), true);
        assert_eq!(e["ciri_witcher"].state, "open");
        assert_eq!(e["ciri_empress"].state, "impossible");
    }

    #[test]
    fn the_positive_confirmation_settles_and_a_set_negative_closes() {
        let d = doc();
        let ev = eval(&[("q110postbattle", "Done"), ("q502avallach", "Done")]);
        let facts = HashSet::from(["q502_ciri_survives".to_string()]);
        let e = evaluate_all(&d, &ev, &facts, true);
        assert_eq!(e["ciri_witcher"].state, "met");
        assert_eq!(e["ciri_witcher"].rows[0].state, "settled");

        let facts = HashSet::from(["q110_to_emperor".to_string(), "q502_ciri_survives".to_string()]);
        let e = evaluate_all(&d, &ev, &facts, true);
        assert_eq!(e["ciri_witcher"].state, "impossible");
    }

    #[test]
    fn no_save_is_unknown_not_a_negative() {
        let d = doc();
        let e = evaluate_all(&d, &eval(&[("q110postbattle", "Done"), ("q502avallach", "Done")]), &HashSet::new(), false);
        assert_eq!(e["ciri_witcher"].state, "unknown");
    }

    #[test]
    fn the_group_turns_the_sibling_into_an_explained_impossible() {
        let d = doc();
        let ev = eval(&[("q110postbattle", "Done"), ("q502avallach", "Done")]);
        let facts = HashSet::from(["q110_to_emperor".to_string(), "q502_ciri_survives".to_string()]);
        let e = evaluate_all(&d, &ev, &facts, true);
        assert_eq!(e["ciri_empress"].state, "met");
        assert_eq!(e["ciri_witcher"].state, "impossible");
        assert!(e["ciri_witcher"].reason.as_deref().unwrap_or("").contains("Ciri empress"));
        assert!(e["ciri_witcher"].blocked_by.iter().any(|b| b["kind"] == "outcome"));
    }

    #[test]
    fn target_evaluation_reuses_the_outcome_rows() {
        let d = doc();
        let endings = json!({"targets": {"ciri_witcher": {"label": "Ciri lives", "outcome": "ciri_witcher", "guidance_status": "guided"}}});
        let ev = eval(&[("q110postbattle", "Done"), ("q502avallach", "Done")]);
        let facts = HashSet::from(["q502_ciri_survives".to_string()]);
        let e = evaluate_targets(&endings, &d, &ev, &facts, true);
        assert_eq!(e["ciri_witcher"].state, "settled");
        assert_eq!(e["ciri_witcher"].rows.len(), 1);
    }

    #[test]
    fn the_matrix_reports_the_same_selected_conflict_as_the_planner() {
        let d = doc();
        let endings = json!({"targets": {
            "ciri_witcher": {"outcome": "ciri_witcher"},
            "ciri_empress": {"outcome": "ciri_empress"}
        }});
        let ev = eval(&[("q110postbattle", "Active")]);
        let exclusive = json!({"edges": [{"kind": "outcome", "a": "ciri_witcher", "b": "ciri_empress",
                                             "reason": "one run", "mechanism": "test", "evidence": []}]});
        let m = matrix(&endings, &d, &exclusive, &ev, &HashSet::new(), true,
                       &["ciri_witcher".into(), "ciri_empress".into()]);
        assert_eq!(m["conflicts"].as_array().unwrap().len(), 2);
        assert_eq!(m["conflicts"][0]["kind"], "outcome_group");
        assert_eq!(m["conflicts"][0]["group"], "main_ciri");
        assert_eq!(m["conflicts"][0]["targets"].as_array().unwrap().len(), 2);
        assert_eq!(m["conflicts"][1]["kind"], "exclusive");
    }

    #[test]
    fn the_shipped_data_parses_and_covers_the_four_requested_targets() {
        let doc: Value = serde_json::from_str(include_str!("../data/outcomes.json")).expect("outcomes.json");
        let endings: Value = serde_json::from_str(include_str!("../data/endings.json")).expect("endings.json");
        assert_eq!(all_ids(&doc).len(), 11);
        for id in ["ciri_witcher", "baron_wife_cured", "olgierd_saved", "bw_both_sisters"] {
            assert_eq!(target_outcome(&endings, id).as_deref(), Some(id));
            assert_eq!(doc["outcomes"][id]["guidance_status"], "guided");
        }
        let recommended = endings["presets"]["recommended"]["targets"].as_array().unwrap();
        assert_eq!(recommended.len(), 4);
    }
}
