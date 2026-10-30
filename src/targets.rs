//! Reviewed ending targets: state evaluation, the spoiler-free branch summaries, and the opt-in
//! guidance rows. The reviewed `endings.json` decides which outcome is a goal; the save decides
//! whether it is settled, still reachable, impossible or unknown. Nothing here invents a fact or a
//! line, and the default payload never receives `instruction`, a target label or choice text.

use crate::model::Eval;
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};

const PACK_ORDER: [&str; 5] = ["base", "ep1", "bob", "other_dlc", "gwent"];
const ENDING_LABEL: &str = "a choice here affects an ending";
const BRANCH_LABEL: &str = "a choice changes later content";

#[derive(Clone)]
pub struct Branch {
    pub id: String,
    pub sets: Vec<String>,
}

#[derive(Default)]
pub struct BranchGraph {
    pub by_id: HashMap<String, Branch>,
    pub by_step: HashMap<String, Vec<Branch>>,
}

impl BranchGraph {
    pub fn from_json(v: &Value) -> Self {
        let mut out = BranchGraph::default();
        let Some(steps) = v.get("branches").and_then(|x| x.as_object()) else {
            return out;
        };
        for (step, entry) in steps {
            let Some(rows) = entry.get("choices").and_then(|x| x.as_array()) else {
                continue;
            };
            for row in rows {
                let Some(id) = row.get("id").and_then(|x| x.as_str()) else {
                    continue;
                };
                let Some(_branch_step) = row.get("step").and_then(|x| x.as_str()) else {
                    continue;
                };
                if row.get("source").and_then(|x| x.get("file")).and_then(|x| x.as_str()).is_none() {
                    continue;
                }
                if row.get("source").and_then(|x| x.get("locid")).and_then(|x| x.as_i64()).is_none() {
                    continue;
                }
                let sets = row
                    .get("sets")
                    .and_then(|x| x.as_array())
                    .map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect())
                    .unwrap_or_default();
                let branch = Branch { id: id.to_string(), sets };
                out.by_id.insert(id.to_string(), branch.clone());
                out.by_step.entry(step.clone()).or_default().push(branch);
            }
        }
        for rows in out.by_step.values_mut() {
            rows.sort_by(|a, b| a.id.cmp(&b.id));
        }
        out
    }

    /// Every branch a reviewed target names in `requires` or `guidance`. These are the only
    /// branches allowed to carry the vague ending label in the detail pane.
    pub fn ending_branch_ids(endings: &Value) -> HashSet<String> {
        let mut out = HashSet::new();
        for target in target_objects(endings) {
            for key in ["requires", "guidance"] {
                for row in target.get(key).and_then(|x| x.as_array()).into_iter().flatten() {
                    if let Some(id) = row
                        .get("source")
                        .and_then(|x| x.get("branch"))
                        .and_then(|x| x.as_str())
                        .or_else(|| row.get("branch").and_then(|x| x.as_str()))
                    {
                        out.insert(id.to_string());
                    }
                }
            }
        }
        out
    }
}

#[derive(Clone)]
pub struct GuidanceRow {
    pub step: String,
    pub kind: String,
    pub branch: String,
    pub instruction: String,
    pub file: String,
    pub locid: i64,
}

#[derive(Clone)]
pub struct RowEval {
    pub row: GuidanceRow,
    pub facts: Vec<String>,
    pub state: String,
    pub note: Option<String>,
}

pub struct TargetEval {
    pub state: String,
    pub reason: Option<String>,
    pub blocked_by: Vec<Value>,
    pub rows: Vec<RowEval>,
}

fn target_objects(endings: &Value) -> Vec<&Value> {
    endings
        .get("targets")
        .and_then(|x| x.as_object())
        .map(|m| m.values().collect())
        .unwrap_or_default()
}

fn target_pack(target: &Value) -> &str {
    target.get("pack").and_then(|x| x.as_str()).unwrap_or("")
}

/// Canonical order: pack order, then target id ascending.
pub fn canonical_ids(endings: &Value, ids: impl IntoIterator<Item = String>) -> Vec<String> {
    let mut wanted: Vec<String> = ids.into_iter().collect();
    wanted.sort();
    wanted.dedup();
    wanted.sort_by_key(|id| {
        let pack = endings
            .get("targets")
            .and_then(|x| x.get(id))
            .map(target_pack)
            .unwrap_or("");
        let rank = PACK_ORDER.iter().position(|p| *p == pack).unwrap_or(PACK_ORDER.len());
        (rank, id.clone())
    });
    wanted
}

pub fn all_ids(endings: &Value) -> Vec<String> {
    let mut ids: Vec<String> = endings
        .get("targets")
        .and_then(|x| x.as_object())
        .map(|m| m.keys().cloned().collect())
        .unwrap_or_default();
    ids = canonical_ids(endings, ids);
    ids
}

pub fn label(endings: &Value, id: &str) -> String {
    endings
        .get("targets")
        .and_then(|x| x.get(id))
        .and_then(|x| x.get("label"))
        .and_then(|x| x.as_str())
        .unwrap_or(id)
        .to_string()
}

fn step_title(ev: &Eval, id: &str) -> String {
    ev.byid
        .get(id)
        .map(|&i| ev.steps[i].n.title.clone())
        .filter(|t| !t.is_empty())
        .unwrap_or_else(|| id.to_string())
}

fn step_state(ev: &Eval, id: &str, row_facts: &[String], facts: &HashSet<String>, save_ok: bool) -> String {
    if !row_facts.is_empty() && row_facts.iter().all(|f| facts.contains(f)) {
        return "settled".into();
    }
    if !save_ok {
        return "unknown".into();
    }
    let Some(&i) = ev.byid.get(id) else {
        return "unknown".into();
    };
    let s = &ev.steps[i];
    if s.lost {
        return "unreachable".into();
    }
    // A tick that contradicts the journal is bookkeeping, not evidence; the journal wins.
    let status = if s.tick_disagrees { s.journal.as_str() } else { s.status.as_str() };
    if matches!(status, "Done" | "Assumed" | "Failed" | "N/A") {
        return "unreachable".into();
    }
    "ahead".into()
}

fn note_for(state: &str) -> Option<String> {
    match state {
        "settled" => Some("In this save: this outcome is already set.".into()),
        "unreachable" => Some("In this save: this choice is already behind you.".into()),
        "unknown" => Some("The tracker cannot decide this step from the save and the branch data.".into()),
        _ => None,
    }
}

fn parse_guidance(target: &Value) -> Vec<GuidanceRow> {
    let mut out = Vec::new();
    for row in target.get("guidance").and_then(|x| x.as_array()).into_iter().flatten() {
        let (Some(step), Some(branch), Some(file), Some(locid)) = (
            row.get("step").and_then(|x| x.as_str()),
            row.get("branch").and_then(|x| x.as_str()),
            row.get("source").and_then(|x| x.get("file")).and_then(|x| x.as_str()),
            row.get("source").and_then(|x| x.get("locid")).and_then(|x| x.as_i64()),
        ) else {
            continue;
        };
        out.push(GuidanceRow {
            step: step.to_string(),
            kind: row.get("kind").and_then(|x| x.as_str()).unwrap_or("scene_choice").to_string(),
            branch: branch.to_string(),
            instruction: row
                .get("instruction")
                .and_then(|x| x.as_str())
                .unwrap_or("")
                .to_string(),
            file: file.to_string(),
            locid,
        });
    }
    out
}

fn requirement_source(req: &Value) -> Value {
    let file = req
        .get("source")
        .and_then(|x| x.get("file"))
        .and_then(|x| x.as_str())
        .unwrap_or("");
    let locid = req
        .get("source")
        .and_then(|x| x.get("locid"))
        .and_then(|x| x.as_i64())
        .unwrap_or(0);
    if !file.is_empty() {
        json!({"kind": "file", "value": file})
    } else if locid > 0 {
        json!({"kind": "locid", "value": locid.to_string()})
    } else {
        json!({"kind": "save", "value": "this save"})
    }
}

/// Evaluate every reviewed target. The result is not cached: it is recomputed from the current save,
/// which is the only way a stale `reachable` cannot survive a save reload or a target change.
pub fn evaluate(
    endings: &Value,
    branches: &BranchGraph,
    ev: &Eval,
    facts: &HashSet<String>,
    save_ok: bool,
) -> HashMap<String, TargetEval> {
    let mut out = HashMap::new();
    for (tid, target) in endings.get("targets").and_then(|x| x.as_object()).into_iter().flatten() {
        // Outcome-backed targets are evaluated by outcomes.rs, which owns the terminal facts and the
        // phase-confirmation rows. Evaluating them here would treat an empty `requires` as settled.
        if target.get("outcome").is_some() {
            continue;
        }
        let status = target.get("guidance_status").and_then(|x| x.as_str()).unwrap_or("");
        if status != "guided" {
            out.insert(
                tid.clone(),
                TargetEval {
                    state: "not_guided_yet".into(),
                    reason: target
                        .get("guidance_reason")
                        .and_then(|x| x.as_str())
                        .map(String::from)
                        .or_else(|| Some("This goal has no reviewed guidance yet.".into())),
                    blocked_by: Vec::new(),
                    rows: Vec::new(),
                },
            );
            continue;
        }

        let requires = target.get("requires").and_then(|x| x.as_array()).cloned().unwrap_or_default();
        let req_facts: HashSet<String> = requires
            .iter()
            .filter_map(|r| r.get("fact").and_then(|x| x.as_str()).map(String::from))
            .collect();
        let guidance = parse_guidance(target);

        let mut rows: Vec<RowEval> = Vec::new();
        for row in guidance {
            let branch = branches.by_id.get(&row.branch);
            let sets = branch.map(|b| b.sets.clone()).unwrap_or_default();
            let mut row_facts: Vec<String> = sets
                .iter()
                .filter(|f| req_facts.contains(*f))
                .cloned()
                .collect();
            row_facts.sort();
            row_facts.dedup();
            let state = if row_facts.is_empty() {
                "unknown".to_string()
            } else {
                step_state(ev, &row.step, &row_facts, facts, save_ok)
            };
            rows.push(RowEval {
                row,
                facts: row_facts,
                state,
                note: None,
            });
        }

        // Requirement result: met, open, closed, or unknown.
        let mut closed_req: Option<&Value> = None;
        let mut any_unknown = false;
        let mut all_met = true;
        for req in &requires {
            let Some(fact) = req.get("fact").and_then(|x| x.as_str()) else {
                any_unknown = true;
                all_met = false;
                continue;
            };
            if facts.contains(fact) {
                continue;
            }
            all_met = false;
            let applicable: Vec<&RowEval> = rows.iter().filter(|r| r.facts.iter().any(|f| f == fact)).collect();
            if applicable.is_empty() {
                any_unknown = true;
            } else if applicable.iter().any(|r| r.state == "ahead") {
                // open: another requirement/row can still decide it
            } else if applicable.iter().any(|r| r.state == "unknown") {
                any_unknown = true;
            } else {
                closed_req = Some(req);
            }
        }

        let (state, reason, blocked_by) = if let Some(req) = closed_req {
            let fact = req.get("fact").and_then(|x| x.as_str()).unwrap_or("");
            let step = req
                .get("source")
                .and_then(|x| x.get("step"))
                .and_then(|x| x.as_str())
                .unwrap_or("");
            let title = step_title(ev, step);
            let blocked = vec![json!({
                "kind": "fact",
                "id": fact,
                "source": requirement_source(req),
            })];
            (
                "impossible".to_string(),
                Some(format!("The choice at {title} is already behind this save.")),
                blocked,
            )
        } else if all_met {
            ("settled".to_string(), None, Vec::new())
        } else if any_unknown {
            (
                "unknown".to_string(),
                Some("The save or the branch data cannot decide whether this goal is still reachable.".into()),
                Vec::new(),
            )
        } else {
            ("reachable".to_string(), None, Vec::new())
        };

        // Target state overrides the per-step warning: no row is `ahead` unless the goal is still
        // reachable. A settled row stays settled even if another requirement made the goal impossible.
        for row in &mut rows {
            let all_set = !row.facts.is_empty() && row.facts.iter().all(|f| facts.contains(f));
            row.state = match state.as_str() {
                "impossible" if !all_set => "unreachable".into(),
                "unknown" if !all_set => "unknown".into(),
                "settled" => "settled".into(),
                _ => row.state.clone(),
            };
            row.note = note_for(&row.state);
        }

        out.insert(
            tid.clone(),
            TargetEval {
                state,
                reason,
                blocked_by,
                rows,
            },
        );
    }
    out
}

pub fn target_json(
    endings: &Value,
    selected: &[String],
    evals: &HashMap<String, TargetEval>,
    guidance_on: bool,
) -> Value {
    if selected.is_empty() {
        return Value::Null;
    }
    let ids: Vec<String> = selected.to_vec();
    let labels: Vec<String> = ids.iter().map(|id| label(endings, id)).collect();
    let mut states = serde_json::Map::new();
    for id in &ids {
        let e = evals.get(id);
        states.insert(
            id.clone(),
            json!({
                "state": e.map(|x| x.state.as_str()).unwrap_or("unknown"),
                "reason": e.and_then(|x| x.reason.clone()),
                "blocked_by": e.map(|x| x.blocked_by.clone()).unwrap_or_default(),
            }),
        );
    }
    json!({
        "ids": ids,
        "labels": labels,
        "guidance": if guidance_on { "on" } else { "off" },
        "states": Value::Object(states),
    })
}

pub fn target_options(
    endings: &Value,
    evals: &HashMap<String, TargetEval>,
) -> Vec<Value> {
    all_ids(endings)
        .into_iter()
        .filter_map(|id| {
            let target = endings.get("targets")?.get(&id)?;
            let e = evals.get(&id);
            Some(json!({
                "id": id,
                "label": label(endings, &id),
                "pack": target_pack(target),
                "spoiler": true,
                "guidance_status": target.get("guidance_status").and_then(|x| x.as_str()).unwrap_or("not_guided_yet"),
                "state": e.map(|x| x.state.as_str()).unwrap_or("unknown"),
                "reason": e.and_then(|x| x.reason.clone()),
                "blocked_by": e.map(|x| x.blocked_by.clone()).unwrap_or_default(),
            }))
        })
        .collect()
}

pub fn preset_options(endings: &Value) -> Vec<Value> {
    let mut out: Vec<Value> = endings
        .get("presets")
        .and_then(|x| x.as_object())
        .map(|m| {
            m.iter()
                .map(|(id, p)| {
                    json!({
                        "id": id,
                        "label": p.get("label").and_then(|x| x.as_str()).unwrap_or(id),
                        "targets": p.get("targets").cloned().unwrap_or_else(|| json!([])),
                        "reviewed": p.get("reviewed").cloned().unwrap_or(Value::Null),
                    })
                })
                .collect()
        })
        .unwrap_or_default();
    out.sort_by(|a, b| a["id"].as_str().unwrap_or("").cmp(b["id"].as_str().unwrap_or("")));
    out
}

pub fn branches_for_step(graph: &BranchGraph, ending_ids: &HashSet<String>, step: &str) -> Value {
    let rows: Vec<Value> = graph
        .by_step
        .get(step)
        .map(|rows| {
            rows.iter()
                .map(|b| {
                    let ending = ending_ids.contains(&b.id);
                    json!({
                        "id": b.id,
                        "ending_relevant": ending,
                        "label": if ending { ENDING_LABEL } else { BRANCH_LABEL },
                    })
                })
                .collect()
        })
        .unwrap_or_default();
    json!(rows)
}

pub fn guidance_for_step(
    endings: &Value,
    selected: &[String],
    evals: &HashMap<String, TargetEval>,
    guidance_on: bool,
    step: &str,
) -> Value {
    if !guidance_on || selected.is_empty() {
        return Value::Null;
    }
    let mut out: Vec<Value> = Vec::new();
    for id in selected {
        let Some(target_eval) = evals.get(id) else { continue };
        for row in target_eval.rows.iter().filter(|r| r.row.step == step) {
            let ahead = row.state == "ahead";
            out.push(json!({
                "target": id,
                "label": label(endings, id),
                "step_state": row.state,
                "instruction": if ahead { Value::String(row.row.instruction.clone()) } else { Value::Null },
                "facts": row.facts,
                "note": row.note,
                "source": {
                    "kind": if row.row.kind.is_empty() { "scene_choice" } else { row.row.kind.as_str() },
                    "file": row.row.file,
                    "locid": row.row.locid,
                },
            }));
        }
    }
    if out.is_empty() {
        Value::Null
    } else {
        Value::Array(out)
    }
}

/// Steps whose exact line is still ahead for a selected target. This is a goal marker, not
/// guidance: it has no `guidance_on` switch, so turning exact lines off cannot delete the plan,
/// the PLAN AHEAD line or the goal chips. Only `instructions` are gated.
pub fn goal_steps(
    selected: &[String],
    evals: &HashMap<String, TargetEval>,
) -> HashSet<String> {
    let mut out = HashSet::new();
    for id in selected {
        let Some(e) = evals.get(id) else { continue };
        if e.state != "reachable" {
            continue;
        }
        for row in &e.rows {
            if row.state == "ahead" {
                out.insert(row.row.step.clone());
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{Eval, Node, Step};

    const STEP: &str = "q704bfairyland";
    const TARGET: &str = "bw_both_sisters";

    fn eval_with(status: &str, journal: &str, tick_disagrees: bool) -> Eval {
        let n = Node {
            section: "Main".into(), id: STEP.into(), title: "Beyond Hill and Dale...".into(),
            lv: "34".into(), files: vec!["q704b_fairy_tale".into()], hard: vec![],
            hard_facts: HashMap::new(), by: vec![], note: String::new(), kind: "main".into(),
            opt: false, when: vec![], order: 0, desc: String::new(), branch: true,
            ending_relevant: true, start_known: true,
            provenance: "game_file".into(), review_reason: String::new(),
            review_source: String::new(), reviewed: String::new(),
        };
        let step = Step {
            n, status: status.into(), journal: journal.into(), manual: false, locked: vec![],
            held: None, lost: false, evs: vec![], cond_unknown: false, tick_disagrees,
            frontier: "available",
        };
        Eval {
            steps: vec![step],
            byid: HashMap::from([(STEP.to_string(), 0)]),
            events: vec![], todo: vec![],
        }
    }

    #[test]
    fn a_goal_is_settled_only_when_the_save_has_the_fact() {
        let ev = eval_with("Active", "Active", false);
        let facts = HashSet::from(["q704_ft_ribbon_won".to_string()]);
        assert_eq!(step_state(&ev, STEP, &["q704_ft_ribbon_won".to_string()], &facts, true), "settled");
        assert_eq!(step_state(&ev, STEP, &["q704_ft_ribbon_won".to_string()], &HashSet::new(), true), "ahead");
    }

    #[test]
    fn a_finished_step_without_the_fact_is_no_longer_reachable() {
        assert_eq!(step_state(&eval_with("Done", "Done", false), STEP, &["f".to_string()], &HashSet::new(), true), "unreachable");
        assert_eq!(step_state(&eval_with("Failed", "Failed", false), STEP, &["f".to_string()], &HashSet::new(), true), "unreachable");
        assert_eq!(step_state(&eval_with("Active", "Active", false), STEP, &["f".to_string()], &HashSet::new(), false), "unknown");
    }

    #[test]
    fn a_tick_never_makes_an_open_journal_step_unreachable() {
        // Your word is bookkeeping, not evidence: the journal still has the step open.
        let ev = eval_with("Done", "Active", true);
        assert_eq!(step_state(&ev, STEP, &["f".to_string()], &HashSet::new(), true), "ahead");
    }

    fn row(step: &str, instruction: &str) -> RowEval {
        RowEval {
            row: GuidanceRow {
                step: step.into(), kind: "scene_choice".into(), branch: format!("{step}__1__f"),
                instruction: instruction.into(), file: "scenes\\choice.w2scene".into(), locid: 1154229,
            },
            facts: vec!["f".into()], state: "ahead".into(), note: None,
        }
    }

    #[test]
    fn no_target_means_no_guidance_at_all() {
        let endings = json!({"targets": {TARGET: {"label": "Blood and Wine: both sisters live"}}});
        let evals = HashMap::new();
        assert_eq!(guidance_for_step(&endings, &[], &evals, true, STEP), Value::Null);
        let selected = vec![TARGET.to_string()];
        assert_eq!(guidance_for_step(&endings, &selected, &evals, true, STEP), Value::Null);
    }

    #[test]
    fn only_the_selected_targets_line_is_returned() {
        let endings = json!({"targets": {
            TARGET: {"label": "Blood and Wine: both sisters live"},
            "other": {"label": "A different ending"}
        }});
        let evals = HashMap::from([
            (TARGET.to_string(), TargetEval {
                state: "reachable".into(), reason: None, blocked_by: vec![],
                rows: vec![row(STEP, "I'll pay you for the ribbon.")],
            }),
            ("other".to_string(), TargetEval {
                state: "reachable".into(), reason: None, blocked_by: vec![],
                rows: vec![row(STEP, "A line for the other goal.")],
            }),
        ]);
        let out = guidance_for_step(&endings, &[TARGET.to_string()], &evals, true, STEP);
        assert_eq!(out[0]["instruction"], "I'll pay you for the ribbon.");
        assert!(!out.to_string().contains("A different ending"));
        assert!(!out.to_string().contains("A line for the other goal."));
        // Guidance off keeps the selected label out of the detail payload too.
        assert_eq!(guidance_for_step(&endings, &[TARGET.to_string()], &evals, false, STEP), Value::Null);
    }
}
