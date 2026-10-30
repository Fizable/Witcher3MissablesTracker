//! One-run route planner.
//!
//! The plan is built from the selected targets' outcome rows, not from a new hand-written list. A
//! guidance row becomes an instruction only while its step is still ahead; a terminal fact whose
//! phase is still ahead becomes a confirmation step with no invented dialogue; a target/save that
//! cannot reach an outcome becomes a blocker; a selected target without reviewed guidance blocks the
//! plan instead of claiming it is ready. Two selected outcomes in the same `selection: one` group, or
//! an edge in `data/exclusive.json`, is a conflict rather than a plan.
//!
//! Order is suggested level first, route index second. Route index alone is section order, which puts
//! every Secondary quest after every Main one; that is useful for PROGRESS, not for a playable plan.

use crate::model::Eval;
use crate::outcomes;
use crate::targets;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, HashSet};

struct StepAcc {
    step: String,
    order: usize,
    level: Option<i64>,
    title: String,
    targets: BTreeSet<String>,
    states: Vec<String>,
    instructions: Vec<Value>,
    facts: BTreeSet<String>,
    confirmation: bool,
}

impl StepAcc {
    fn new(step: &str, order: usize, level: Option<i64>, title: String) -> Self {
        StepAcc {
            step: step.to_string(),
            order,
            level,
            title,
            targets: BTreeSet::new(),
            states: Vec::new(),
            instructions: Vec::new(),
            facts: BTreeSet::new(),
            confirmation: false,
        }
    }

    fn state(&self) -> String {
        if self.states.iter().any(|s| s == "ahead") {
            return "ahead".into();
        }
        if !self.states.is_empty() && self.states.iter().all(|s| s == "settled") {
            return "settled".into();
        }
        if self.states.iter().any(|s| s == "unknown") {
            return "unknown".into();
        }
        if !self.states.is_empty() && self.states.iter().all(|s| s == "unreachable") {
            return "unreachable".into();
        }
        if self.states.iter().any(|s| s == "settled") {
            return "settled".into();
        }
        "unknown".into()
    }
}

fn step_status<'a>(ev: &'a Eval, id: &str) -> Option<&'a str> {
    ev.byid.get(id).map(|&i| {
        let s = &ev.steps[i];
        if s.tick_disagrees { s.journal.as_str() } else { s.status.as_str() }
    })
}

fn step_closed(ev: &Eval, id: &str) -> bool {
    matches!(step_status(ev, id), Some("Done") | Some("Assumed") | Some("Failed") | Some("N/A"))
}

fn step_level(ev: &Eval, id: &str) -> Option<i64> {
    ev.byid
        .get(id)
        .and_then(|&i| ev.steps[i].n.lv.trim().parse::<i64>().ok())
}

/// Build the plan for `requested` target ids. An unknown id is reported, never silently ignored.
pub fn build(
    endings: &Value,
    outcomes_doc: &Value,
    requested: &[String],
    ev: &Eval,
    facts: &HashSet<String>,
    save_ok: bool,
    exclusive: &Value,
) -> Value {
    let known: HashSet<String> = targets::all_ids(endings).into_iter().collect();
    let mut invalid: Vec<String> = Vec::new();
    let selected: Vec<String> = requested
        .iter()
        .filter(|id| {
            if known.contains(*id) {
                true
            } else {
                invalid.push((*id).clone());
                false
            }
        })
        .cloned()
        .collect();
    let selected = targets::canonical_ids(endings, selected);

    let evals = outcomes::evaluate_targets(endings, outcomes_doc, ev, facts, save_ok);
    let selected_outcomes = outcomes::selected_outcomes(endings, &selected);
    let unguided: Vec<String> = selected
        .iter()
        .filter(|tid| {
            !selected_outcomes.contains_key(*tid)
                || evals
                    .get(*tid)
                    .map(|e| e.state == "not_guided_yet")
                    .unwrap_or(true)
        })
        .cloned()
        .collect();

    let conflicts = outcomes::selected_conflicts(outcomes_doc, exclusive, &selected, &selected_outcomes);

    let blocked_by: Vec<Value> = selected
        .iter()
        .filter_map(|tid| {
            let e = evals.get(tid)?;
            if e.state != "impossible" {
                return None;
            }
            Some(json!({
                "target": tid,
                "outcome": selected_outcomes.get(tid),
                "reason": e.reason.clone(),
                "blocked_by": e.blocked_by.clone(),
            }))
        })
        .collect();

    let met = selected.iter().filter(|tid| evals.get(*tid).map(|e| e.state == "settled").unwrap_or(false)).count();
    let open = selected.iter().filter(|tid| evals.get(*tid).map(|e| e.state == "reachable").unwrap_or(false)).count();
    let impossible = selected.iter().filter(|tid| evals.get(*tid).map(|e| e.state == "impossible").unwrap_or(false)).count();
    let unknown = selected.iter().filter(|tid| evals.get(*tid).map(|e| e.state == "unknown").unwrap_or(false)).count();

    let selected_len = selected.len();
    let guided_len = selected_len - unguided.len();
    let group_count = outcomes_doc.get("groups").and_then(|x| x.as_object()).map(|m| m.len()).unwrap_or(0);
    if !conflicts.is_empty() {
        // Do not merge two mutually exclusive goals into one route. The conflict cards are the whole
        // answer until the player narrows the selection; returning steps here would silently mix them.
        return json!({
            "version": 1,
            "state": "conflict",
            "selected": selected,
            "unguided": unguided,
            "invalid": invalid,
            "conflicts": conflicts,
            "blocked_by": blocked_by,
            "steps": [],
            "coverage": {
                "targets": selected_len,
                "guided": guided_len,
                "groups": group_count,
                "steps": 0,
                "ahead": 0,
                "met": met,
                "open": open,
                "impossible": impossible,
                "unknown": unknown,
            },
            "note": "Conflicting goals: no route plan is shown until the selection is narrowed.",
        });
    }
    if !unguided.is_empty() {
        // A target without reviewed guidance is a failure, not a ready plan. Do not build a route
        // from terminal facts alone: that would present an unguided goal as if it had a plan.
        return json!({
            "version": 1,
            "state": "blocked",
            "selected": selected,
            "unguided": unguided,
            "invalid": invalid,
            "conflicts": conflicts,
            "blocked_by": blocked_by,
            "steps": [],
            "coverage": {
                "targets": selected_len,
                "guided": guided_len,
                "groups": group_count,
                "steps": 0,
                "ahead": 0,
                "met": met,
                "open": open,
                "impossible": impossible,
                "unknown": unknown,
            },
            "note": "Some selected goals have no reviewed guidance yet; no route plan is shown.",
        });
    }

    let mut steps: BTreeMap<String, StepAcc> = BTreeMap::new();
    for tid in &selected {
        let Some(e) = evals.get(tid) else { continue };
        let guidance_steps: HashSet<String> = e.rows.iter().map(|r| r.row.step.clone()).collect();
        for row in &e.rows {
            let order = ev.byid.get(&row.row.step).copied().unwrap_or(usize::MAX);
            let level = step_level(ev, &row.row.step);
            let title = ev
                .byid
                .get(&row.row.step)
                .map(|&i| ev.steps[i].n.title.clone())
                .filter(|t| !t.is_empty())
                .unwrap_or_else(|| row.row.step.clone());
            let acc = steps
                .entry(row.row.step.clone())
                .or_insert_with(|| StepAcc::new(&row.row.step, order, level, title));
            acc.targets.insert(tid.clone());
            let row_state = if row.state == "ahead" && e.state != "reachable" {
                "unknown"
            } else {
                row.state.as_str()
            };
            acc.states.push(row_state.to_string());
            acc.facts.extend(row.facts.iter().cloned());
            if row_state == "ahead" {
                acc.instructions.push(json!({
                    "target": tid,
                    "instruction": row.row.instruction,
                    "kind": row.row.kind,
                    "branch": row.row.branch,
                    "file": row.row.file,
                    "locid": row.row.locid,
                    "facts": row.facts,
                }));
            }
        }

        // A terminal phase fact is a plan step too. It has no dialogue line, so it never carries an
        // instruction: the plan names the quest and the fact, and says the phase confirms it.
        let Some(oid) = selected_outcomes.get(tid) else { continue };
        let requires = outcomes_doc
            .get("outcomes")
            .and_then(|x| x.get(oid))
            .and_then(|x| x.get("requires"))
            .and_then(|x| x.as_array())
            .cloned()
            .unwrap_or_default();
        for req in &requires {
            let Some(step) = req.get("source").and_then(|x| x.get("step")).and_then(|x| x.as_str()) else { continue };
            if step.is_empty() || guidance_steps.contains(step) {
                continue;
            }
            let order = ev.byid.get(step).copied().unwrap_or(usize::MAX);
            let level = step_level(ev, step);
            let title = ev
                .byid
                .get(step)
                .map(|&i| ev.steps[i].n.title.clone())
                .filter(|t| !t.is_empty())
                .unwrap_or_else(|| step.to_string());
            let acc = steps
                .entry(step.to_string())
                .or_insert_with(|| StepAcc::new(step, order, level, title));
            acc.targets.insert(tid.clone());
            acc.confirmation = true;
            if let Some(fact) = req.get("fact").and_then(|x| x.as_str()) {
                acc.facts.insert(fact.to_string());
            }
            let confirmation_state = match e.state.as_str() {
                "settled" => "settled",
                "impossible" => "unreachable",
                "unknown" => "unknown",
                _ => {
                    if !save_ok {
                        "unknown"
                    } else if step_closed(ev, step) {
                        // The target is still reachable, so a closed confirmation step did what it
                        // needed to do; the open requirement is elsewhere.
                        "settled"
                    } else {
                        "ahead"
                    }
                }
            };
            acc.states.push(confirmation_state.into());
        }
    }

    let mut step_rows: Vec<Value> = steps
        .into_values()
        .map(|acc| {
            let state = acc.state();
            let instructions: Vec<Value> = if state == "ahead" {
                acc.instructions.clone()
            } else {
                Vec::new()
            };
            let note = if acc.confirmation && state == "ahead" && instructions.is_empty() {
                Some("No dialogue line: the game phase sets the terminal fact. This is the confirmation step, not a choice.")
            } else if state == "unreachable" {
                Some("This step is already behind the save without the required outcome.")
            } else if state == "unknown" {
                Some("The save or the route cannot decide this step.")
            } else {
                None
            };
            let prerequisites = ev
                .byid
                .get(&acc.step)
                .map(|&i| ev.steps[i].n.hard.clone())
                .unwrap_or_default();
            json!({
                "step": acc.step,
                "title": acc.title,
                "order": acc.order,
                "level": acc.level,
                "state": state,
                "targets": acc.targets.iter().cloned().collect::<Vec<_>>(),
                "instructions": instructions,
                "facts": acc.facts.iter().cloned().collect::<Vec<_>>(),
                "confirmation": acc.confirmation,
                "note": note,
                "prerequisites": prerequisites,
            })
        })
        .collect();
    step_rows.sort_by_key(|s| {
        (
            s.get("level").and_then(|x| x.as_i64()).unwrap_or(i64::MAX),
            s.get("order").and_then(|x| x.as_u64()).unwrap_or(u64::MAX),
        )
    });
    let ahead = step_rows.iter().filter(|s| s.get("state").and_then(|x| x.as_str()) == Some("ahead")).count();

    let state = if selected.is_empty() {
        "empty"
    } else if !conflicts.is_empty() {
        "conflict"
    } else if !blocked_by.is_empty() {
        "blocked"
    } else if !save_ok {
        "unknown"
    } else {
        "ready"
    };

    json!({
        "version": 1,
        "state": state,
        "selected": selected,
        "unguided": unguided,
        "invalid": invalid,
        "conflicts": conflicts,
        "blocked_by": blocked_by,
        "steps": step_rows,
        "coverage": {
            "targets": selected.len(),
            "guided": guided_len,
            "groups": outcomes_doc.get("groups").and_then(|x| x.as_object()).map(|m| m.len()).unwrap_or(0),
            "steps": step_rows.len(),
            "ahead": ahead,
            "met": met,
            "open": open,
            "impossible": impossible,
            "unknown": unknown,
        },
        "note": "Suggested level, then route order. Instructions are present only for steps still ahead; a confirmation step names the phase fact and has no dialogue line.",
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{Eval, Node, Step};
    use serde_json::json;
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
        let mut e = Eval { steps: Vec::new(), byid: HashMap::new(), events: Vec::new(), todo: Vec::new() };
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

    fn docs() -> (Value, Value) {
        let outcomes = json!({
            "groups": {
                "main_ciri": {"pack": "base", "label": "Ciri", "selection": "one", "outcomes": ["ciri_witcher", "ciri_empress"]}
            },
            "outcomes": {
                "ciri_witcher": {
                    "group": "main_ciri", "pack": "base", "label": "Ciri lives", "guidance_status": "guided",
                    "requires": [
                        {"fact": "q110_to_emperor", "value": false, "source": {"kind": "phase_fact", "step": "q110postbattle", "file": "q110.w2phase", "fact": "q110_to_emperor"}},
                        {"fact": "q502_ciri_survives", "value": true, "source": {"kind": "phase_fact", "step": "q502avallach", "file": "q502.w2phase", "fact": "q502_ciri_survives"}}
                    ],
                    "guidance": [{"step": "q110postbattle", "kind": "scene_choice", "branch": "b1", "instruction": "Velen.", "facts": [], "source": {"kind": "scene_choice", "file": "s.w2scene", "locid": 1}}]
                },
                "ciri_empress": {
                    "group": "main_ciri", "pack": "base", "label": "Ciri empress", "guidance_status": "guided",
                    "requires": [{"fact": "q110_to_emperor", "value": true, "source": {"kind": "phase_fact", "step": "q110postbattle", "file": "q110.w2phase", "fact": "q110_to_emperor"}}],
                    "guidance": [{"step": "q110postbattle", "kind": "scene_choice", "branch": "b2", "instruction": "Emhyr.", "facts": ["q110_to_emperor"], "source": {"kind": "scene_choice", "file": "s.w2scene", "locid": 2}}]
                }
            }
        });
        let endings = json!({"targets": {
            "ciri_witcher": {"label": "Ciri lives", "pack": "base", "outcome": "ciri_witcher", "guidance_status": "guided"},
            "ciri_empress": {"label": "Ciri empress", "pack": "base", "outcome": "ciri_empress", "guidance_status": "guided"}
        }});
        (endings, outcomes)
    }

    #[test]
    fn the_plan_orders_by_level_then_route_and_only_ahead_steps_carry_instructions() {
        let (endings, outcomes) = docs();
        let ev = eval(&[("q110postbattle", "Active"), ("q502avallach", "Not started")]);
        let plan = build(&endings, &outcomes, &["ciri_witcher".into()], &ev, &HashSet::new(), true, &json!({"edges": []}));
        assert_eq!(plan["state"], "ready");
        assert_eq!(plan["steps"][0]["step"], "q110postbattle");
        assert_eq!(plan["steps"][0]["state"], "ahead");
        assert_eq!(plan["steps"][0]["instructions"][0]["instruction"], "Velen.");
        assert_eq!(plan["steps"][1]["step"], "q502avallach");
        assert_eq!(plan["steps"][1]["confirmation"], true);
        assert_eq!(plan["steps"][1]["instructions"].as_array().unwrap().len(), 0);
    }

    #[test]
    fn suggested_level_precedes_the_sectioned_route_index() {
        let (endings, outcomes) = docs();
        let mut ev = eval(&[("q110postbattle", "Active"), ("q502avallach", "Not started")]);
        ev.steps[0].n.lv = "20".into();
        ev.steps[1].n.lv = "10".into();
        let plan = build(&endings, &outcomes, &["ciri_witcher".into()], &ev, &HashSet::new(), true, &json!({"edges": []}));
        assert_eq!(plan["steps"][0]["step"], "q502avallach");
        assert_eq!(plan["steps"][0]["level"], 10);
        assert_eq!(plan["steps"][1]["step"], "q110postbattle");
    }

    #[test]
    fn a_settled_step_does_not_leak_its_instruction() {
        let (endings, outcomes) = docs();
        let ev = eval(&[("q110postbattle", "Done"), ("q502avallach", "Done")]);
        let facts = HashSet::from(["q502_ciri_survives".to_string()]);
        let plan = build(&endings, &outcomes, &["ciri_witcher".into()], &ev, &facts, true, &json!({"edges": []}));
        assert_eq!(plan["state"], "ready");
        assert_eq!(plan["steps"][0]["state"], "settled");
        assert!(plan["steps"][0]["instructions"].as_array().unwrap().is_empty());
        assert_eq!(plan["coverage"]["met"], 1);
    }

    #[test]
    fn two_outcomes_in_one_group_are_a_conflict() {
        let (endings, outcomes) = docs();
        let ev = eval(&[("q110postbattle", "Active")]);
        let plan = build(&endings, &outcomes, &["ciri_witcher".into(), "ciri_empress".into()], &ev, &HashSet::new(), true, &json!({"edges": []}));
        assert_eq!(plan["state"], "conflict");
        assert_eq!(plan["conflicts"][0]["kind"], "outcome_group");
        assert!(plan["steps"].as_array().unwrap().is_empty(), "a conflicting pair must not be merged into one route");
        assert_eq!(plan["coverage"]["steps"], 0);
    }

    #[test]
    fn a_not_guided_target_blocks_the_plan() {
        let (mut endings, outcomes) = docs();
        endings["targets"]["ciri_empress"]["guidance_status"] = json!("not_guided_yet");
        let ev = eval(&[("q110postbattle", "Active")]);
        let plan = build(&endings, &outcomes, &["ciri_empress".into()], &ev, &HashSet::new(), true, &json!({"edges": []}));
        assert_eq!(plan["state"], "blocked");
        assert_eq!(plan["unguided"][0], "ciri_empress");
        assert_eq!(plan["coverage"]["guided"], 0);
        assert!(plan["steps"].as_array().unwrap().is_empty());
    }

    #[test]
    fn an_impossible_target_blocks_the_plan() {
        let (endings, outcomes) = docs();
        let ev = eval(&[("q110postbattle", "Done")]);
        let facts = HashSet::from(["q110_to_emperor".to_string()]);
        let plan = build(&endings, &outcomes, &["ciri_witcher".into()], &ev, &facts, true, &json!({"edges": []}));
        assert_eq!(plan["state"], "blocked");
        assert_eq!(plan["blocked_by"][0]["target"], "ciri_witcher");
    }

    #[test]
    fn an_empty_selection_is_empty_not_ready() {
        let (endings, outcomes) = docs();
        let ev = eval(&[("q110postbattle", "Active")]);
        let plan = build(&endings, &outcomes, &[], &ev, &HashSet::new(), true, &json!({"edges": []}));
        assert_eq!(plan["state"], "empty");
        assert!(plan["steps"].as_array().unwrap().is_empty());
    }

    #[test]
    fn an_unknown_target_is_reported() {
        let (endings, outcomes) = docs();
        let ev = eval(&[("q110postbattle", "Active")]);
        let plan = build(&endings, &outcomes, &["not_a_target".into()], &ev, &HashSet::new(), true, &json!({"edges": []}));
        assert_eq!(plan["invalid"][0], "not_a_target");
        assert_eq!(plan["state"], "empty");
    }
}
