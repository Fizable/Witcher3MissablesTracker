//! The generated Gwent card index and the save's own collection ledger.
//!
//! The index is `data/gwent_cards.json` (224 collectible definitions). Ownership comes from
//! `CR4GwintManager.SBCollectionCard` / `SBLeaderCollectionCard` by card index; a missing or
//! unreadable block makes every card `unknown`, never `not owned`. Manual ticks are an overlay and
//! always win; a card is never inferred from a quest status. The separate `window` field is the
//! reviewed deadline/one-time/no-window classification; it never changes ownership.

use crate::save::CardCollection;
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};

#[derive(Clone)]
pub struct Card {
    pub id: String,
    pub name: String,
    pub deck: String,
    pub pack: String,
    pub index: i64,
    pub collection: String,
    pub source_text: String,
    pub source_kind: String,
    /// The route step the reviewed source names, when it names one. A tracked quest can show a
    /// missable card granted by its own step even when the window closes somewhere else.
    pub source_step: String,
    pub window: Value,
    pub deck_default: bool,
}

pub struct CardIndex {
    pub cards: Vec<Card>,
    pub denominator: i64,
    pub missable_windows: Value,
}

impl CardIndex {
    pub fn from_json(v: &Value) -> Self {
        let rows = v.get("cards").and_then(|x| x.as_array()).cloned().unwrap_or_default();
        let cards = rows
            .iter()
            .filter_map(|c| {
                let id = c.get("id")?.as_str()?.to_string();
                let index = c.get("index")?.as_i64()?;
                let source = c.get("source").cloned().unwrap_or(Value::Null);
                Some(Card {
                    id,
                    name: c.get("name").and_then(|x| x.as_str()).unwrap_or("").to_string(),
                    deck: c.get("deck").and_then(|x| x.as_str()).unwrap_or("").to_string(),
                    pack: c.get("pack").and_then(|x| x.as_str()).unwrap_or("").to_string(),
                    index,
                    collection: c
                        .get("collection")
                        .and_then(|x| x.as_str())
                        .unwrap_or("main")
                        .to_string(),
                    source_text: source
                        .get("text")
                        .and_then(|x| x.as_str())
                        .unwrap_or("unknown source")
                        .to_string(),
                    source_kind: source
                        .get("kind")
                        .and_then(|x| x.as_str())
                        .unwrap_or("unknown")
                        .to_string(),
                    source_step: source
                        .get("step")
                        .and_then(|x| x.as_str())
                        .unwrap_or("")
                        .to_string(),
                    window: c.get("window").cloned().unwrap_or(Value::Null),
                    deck_default: c.get("ownership").and_then(|x| x.as_str()) == Some("deck_default"),
                })
            })
            .collect::<Vec<_>>();
        CardIndex {
            denominator: v.get("denominator").and_then(|x| x.as_i64()).unwrap_or(cards.len() as i64),
            cards,
            missable_windows: v
                .get("missable_windows")
                .cloned()
                .unwrap_or_else(|| json!({"proven": false, "note": "No card-level window is proven."})),
        }
    }

    pub fn total(&self) -> i64 {
        self.cards.len() as i64
    }

    /// One card row per definition, with the save-derived state. `manual` maps card id -> bool and
    /// is the only override; a manual `false` means explicitly not owned.
    pub fn rows(
        &self,
        collection: Option<&CardCollection>,
        save_ok: bool,
        save_reason: &str,
        facts: &HashSet<String>,
        manual: &HashMap<String, bool>,
        statuses: &HashMap<String, String>,
    ) -> Vec<Value> {
        self.cards
            .iter()
            .map(|c| {
                let (owned, note) = if let Some(value) = manual.get(&c.id) {
                    (if *value { "owned" } else { "not_owned" }.to_string(), Some("manual".to_string()))
                } else if !save_ok {
                    ("unknown".to_string(), Some(save_reason.to_string()))
                } else if let Some(col) = collection {
                    if c.collection == "main" {
                        (if col.normal.get(&c.index).copied().unwrap_or(0) > 0 { "owned" } else { "not_owned" }.to_string(), None)
                    } else if c.deck_default && !col.leaders.contains_key(&c.index) {
                        if facts.contains("skel_gwint_base_deck_given") {
                            ("owned".to_string(), None)
                        } else {
                            ("unknown".to_string(), Some("deck leader with no collection row and no deck-unlock fact".to_string()))
                        }
                    } else {
                        (if col.leaders.get(&c.index).copied().unwrap_or(0) > 0 { "owned" } else { "not_owned" }.to_string(), None)
                    }
                } else {
                    ("unknown".to_string(), Some(save_reason.to_string()))
                };
                let live = window_live(&c.window, &owned, save_ok, facts, statuses);
                json!({
                    "id": c.id,
                    "name": c.name,
                    "deck": c.deck,
                    "pack": c.pack,
                    "collection": c.collection,
                    "owned": owned,
                    "source_text": c.source_text,
                    "source_kind": c.source_kind,
                    "source_step": c.source_step,
                    "window": c.window,
                    "window_live": live,
                    "note": note,
                })
            })
            .collect()
    }

    pub fn report(
        &self,
        collection: Option<&CardCollection>,
        save_ok: bool,
        save_reason: &str,
        facts: &HashSet<String>,
        manual: &HashMap<String, bool>,
        statuses: &HashMap<String, String>,
    ) -> Value {
        let cards = self.rows(collection, save_ok, save_reason, facts, manual, statuses);
        let mut owned = 0i64;
        let mut not_owned = 0i64;
        let mut unknown = 0i64;
        let mut missable = 0i64;
        let mut missable_tier_a = 0i64;
        let mut missable_tier_b = 0i64;
        let mut one_time = 0i64;
        let mut no_window = 0i64;
        let mut tier_a = 0i64;
        let mut tier_b = 0i64;
        let mut tier_c = 0i64;
        let mut active = 0i64;
        let mut ahead = 0i64;
        let mut passed = 0i64;
        let mut check = 0i64;
        let mut lost = 0i64;
        for card in &cards {
            match card.get("owned").and_then(|x| x.as_str()) {
                Some("owned") => owned += 1,
                Some("not_owned") => not_owned += 1,
                _ => unknown += 1,
            }
            let w = card.get("window").cloned().unwrap_or(Value::Null);
            match w.get("kind").and_then(|x| x.as_str()) {
                Some("missable") => {
                    missable += 1;
                    match w.get("tier_rank").and_then(|x| x.as_str()) {
                        Some("A") => missable_tier_a += 1,
                        Some("B") => missable_tier_b += 1,
                        _ => {}
                    }
                }
                Some("one_time") => one_time += 1,
                _ => no_window += 1,
            }
            match w.get("tier_rank").and_then(|x| x.as_str()) {
                Some("A") => tier_a += 1,
                Some("B") => tier_b += 1,
                _ => tier_c += 1,
            }
            match card.get("window_live").and_then(|x| x.get("state")).and_then(|x| x.as_str()) {
                Some("active") => active += 1,
                Some("ahead") => ahead += 1,
                Some("passed") => passed += 1,
                Some("check") => check += 1,
                Some("lost") => lost += 1,
                _ => {}
            }
        }
        json!({
            "cards": cards,
            "counts": {
                "owned": owned,
                "not_owned": not_owned,
                "unknown": unknown,
                "total": self.total(),
                "missable": missable,
                "missable_tier_a": missable_tier_a,
                "missable_tier_b": missable_tier_b,
                "one_time": one_time,
                "no_window": no_window,
                "tier_a": tier_a,
                "tier_b": tier_b,
                "tier_c": tier_c,
                "active": active,
                "ahead": ahead,
                "passed": passed,
                "check": check,
                "lost": lost,
            },
            "denominator": self.denominator,
            "block_ok": save_ok && collection.is_some(),
            "reason": save_reason,
            "missable_windows": self.missable_windows,
        })
    }
}

fn tier_label(kind: &str, tier: &str) -> String {
    match kind {
        "missable" if tier == "community" => "COMMUNITY WINDOW".to_string(),
        "missable" => "GAMEFILE WINDOW".to_string(),
        "one_time" => "ONE-TIME · TIER A".to_string(),
        _ if tier == "unknown" => "UNKNOWN SOURCE · NO WINDOW".to_string(),
        _ => "NO WINDOW".to_string(),
    }
}

/// The save-relative state of one reviewed window. It never changes ownership and never turns a
/// Tier B community row into a hard loss: that needs save ownership plus a file-backed step.
/// This is the only producer of the card row label; the UI renders `label` and `tone` directly.
fn window_live(
    window: &Value,
    owned: &str,
    save_ok: bool,
    facts: &HashSet<String>,
    statuses: &HashMap<String, String>,
) -> Value {
    if window.is_null() {
        return json!({"state": "none", "tone": "dim", "label": "NO WINDOW"});
    }
    let kind = window.get("kind").and_then(|x| x.as_str()).unwrap_or("none");
    let tier = window.get("tier").and_then(|x| x.as_str()).unwrap_or("unknown");
    let base = tier_label(kind, tier);
    // A window opens on its own step, not necessarily on the step that closes it (Thaler opens
    // before Reason of State). A fact gate is the save's own answer to "is the source here yet?".
    let opens = window.get("opens").filter(|x| x.is_object());
    let gate_step = opens
        .and_then(|x| x.get("step"))
        .and_then(|x| x.as_str())
        .or_else(|| window.get("step").and_then(|x| x.as_str()))
        .unwrap_or("");
    let gate_status = statuses.get(gate_step).map(String::as_str).unwrap_or("Not started");
    let requires_met = opens
        .and_then(|x| x.get("requires"))
        .and_then(|x| x.as_array())
        .map(|rows| {
            rows.iter().all(|r| {
                if r.get("kind").and_then(|x| x.as_str()) != Some("fact") {
                    return true;
                }
                r.get("value")
                    .and_then(|x| x.as_str())
                    .map(|f| facts.contains(f))
                    .unwrap_or(true)
            })
        })
        .unwrap_or(true);
    let has_fallback = window
        .get("fallback")
        .and_then(|x| x.as_array())
        .map(|a| !a.is_empty())
        .unwrap_or(false);
    let (state, tone, label) = if owned == "owned" {
        ("owned", "green", base.clone())
    } else if !save_ok || owned == "unknown" {
        ("unknown", "dim", base.clone())
    } else if kind == "none" {
        (
            if tier == "unknown" { "unknown_source" } else { "none" },
            "dim",
            base.clone(),
        )
    } else if !requires_met {
        ("not_yet", "dim", format!("SOURCE NOT YET · {base}"))
    } else if gate_status == "Not started" || gate_status.is_empty() {
        (
            "ahead",
            if kind == "missable" { "amber" } else { "blue" },
            format!("OPEN LATER · {base}"),
        )
    } else if gate_status == "Active" {
        (
            "active",
            if kind == "missable" { "red" } else { "blue" },
            if kind == "missable" { format!("OPEN NOW · {base}") } else { base.clone() },
        )
    } else if has_fallback {
        ("check", "amber", format!("PASSED - CHECK FALLBACK · {base}"))
    } else {
        match (kind, gate_status) {
            ("missable", s) if matches!(s, "Done" | "Failed" | "N/A") && tier == "gamefile" => {
                ("lost", "lost", format!("LOST · {base}"))
            }
            ("missable", s) if matches!(s, "Done" | "Failed" | "N/A") || s.is_empty() => {
                ("check", "lost", format!("PASSED - CHECK · {base}"))
            }
            ("one_time", s) if matches!(s, "Done" | "Failed" | "N/A") || s.is_empty() => {
                ("passed", "dim", "ONE-TIME · PASSED · TIER A".to_string())
            }
            _ => ("unknown", "dim", base.clone()),
        }
    };
    if kind == "none" {
        return json!({
            "state": state,
            "tone": tone,
            "label": label,
            "reason": window.get("reason").cloned().unwrap_or(Value::Null),
        });
    }
    json!({
        "state": state,
        "tone": tone,
        "label": label,
        "step": window.get("step").and_then(|x| x.as_str()).unwrap_or(""),
        "step_title": window.get("step_title").cloned().unwrap_or(Value::Null),
        "event": window.get("event").cloned().unwrap_or(Value::Null),
        "mechanism": window.get("mechanism").cloned().unwrap_or(Value::Null),
        "opens": window.get("opens").cloned().unwrap_or(Value::Null),
        "fallback": window.get("fallback").cloned().unwrap_or(Value::Null),
    })
}

fn text<'a>(value: &'a Value, key: &str) -> &'a str {
    value.get(key).and_then(|x| x.as_str()).unwrap_or("")
}

/// Card windows share the top warning surface with quest cutoffs. They are grouped by their
/// closing step so a party or tournament with three cards does not become three near-identical
/// cards. Only a window the player can act on now is a band row; a closed or passed window is a
/// STATUS row.
pub fn top_items(report: &Value) -> Vec<Value> {
    grouped(report, &["active"])
}

/// A card window that has closed or passed is a check, not an action now.
pub fn status_items(report: &Value) -> Vec<Value> {
    grouped(report, &["check", "lost"])
}

fn grouped(report: &Value, wanted: &[&str]) -> Vec<Value> {
    let mut groups: HashMap<String, Vec<&Value>> = HashMap::new();
    for card in report.get("cards").and_then(|x| x.as_array()).into_iter().flatten() {
        let window = card.get("window").cloned().unwrap_or(Value::Null);
        // A one-time source is a window in the ledger, but it is not a reviewed deadline; only a
        // missable row belongs in the warning surfaces.
        if text(&window, "kind") != "missable" {
            continue;
        }
        let live = card.get("window_live").cloned().unwrap_or(Value::Null);
        let state = text(&live, "state");
        // A window whose closing quest has not started is ledger-only. An active window is the
        // only card state the warning ledger may carry; check and lost are STATUS rows.
        if !wanted.contains(&state) {
            continue;
        }
        let step = text(&live, "step");
        if !step.is_empty() {
            groups.entry(step.to_string()).or_default().push(card);
        }
    }
    let mut out: Vec<(u8, String, Value)> = Vec::new();
    for (step, cards) in groups {
        let states: Vec<&str> = cards
            .iter()
            .map(|card| text(card.get("window_live").unwrap_or(&Value::Null), "state"))
            .collect();
        let state = if states.iter().any(|s| *s == "active") {
            "active"
        } else if states.iter().any(|s| *s == "check") {
            "check"
        } else {
            "lost"
        };
        let window = cards[0].get("window").cloned().unwrap_or(Value::Null);
        let step_title = text(&window, "step_title");
        let event = text(&window, "event");
        let mechanism = text(&window, "mechanism");
        let mut names: Vec<String> = cards
            .iter()
            .filter_map(|card| card.get("name").and_then(|x| x.as_str()).map(String::from))
            .collect();
        names.sort();
        names.dedup();
        let headline = if names.len() == 1 {
            format!("Gwent card: {}", names[0])
        } else {
            let shown = names.iter().take(4).cloned().collect::<Vec<_>>().join(", ");
            let more = if names.len() > 4 { format!(" and {} more", names.len() - 4) } else { String::new() };
            format!("{} Gwent cards: {}{}", names.len(), shown, more)
        };
        let (level, tag, rank) = match state {
            "active" => ("stop", "CARD WINDOW OPEN", 0u8),
            "check" => ("stop", "CARD WINDOW PASSED - CHECK NOW", 1u8),
            _ => ("lost", "CARD LOST IN THIS SAVE", 2u8),
        };
        let place = if step_title == event { event.to_string() } else { format!("{step_title} - {event}") };
        let action = format!("{place}. {mechanism}");
        let live_note = match state {
            "active" => "Not owned, and the closing step is active in your save.",
            "check" => "Not owned; the closing step is done or failed. Check whether a fallback still exists.",
            _ => "Not owned; the file-backed window is past.",
        };
        let file = window
            .get("evidence")
            .and_then(|x| x.as_array())
            .and_then(|x| x.iter().find(|row| text(row, "kind") == "file"))
            .and_then(|row| row.get("value"))
            .and_then(|x| x.as_str())
            .unwrap_or("");
        out.push((rank, headline.clone(), json!({
            "kind": "card",
            "level": level,
            "tag": tag,
            "headline": headline,
            "detail": mechanism,
            "action": action,
            "lost_titles": names,
            "closing_titles": [step_title],
            "live_note": live_note,
            "mechanism": "reviewed card window",
            "file": file,
            "quests": [step_title],
            "ids": [step],
        })));
    }
    out.sort_by(|a, b| a.0.cmp(&b.0).then_with(|| a.1.cmp(&b.1)));
    out.into_iter().map(|(_, _, value)| value).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::save::CardCollection;

    fn index(window: Value) -> CardIndex {
        CardIndex::from_json(&json!({
            "denominator": 1,
            "cards": [{
                "id": "card_test",
                "index": 1,
                "collection": "main",
                "name": "Test card",
                "deck": "Neutral",
                "pack": "base",
                "source": {"kind": "phase_grant", "text": "Scripted grant"},
                "window": window
            }]
        }))
    }

    fn report(index: &CardIndex, owned: bool, save_ok: bool, status: &str) -> Value {
        let mut normal = HashMap::new();
        if owned {
            normal.insert(1, 1);
        }
        let collection = CardCollection { normal, leaders: HashMap::new() };
        let statuses = HashMap::from([("sq301triss".to_string(), status.to_string())]);
        index.report(
            if save_ok { Some(&collection) } else { None },
            save_ok,
            if save_ok { "" } else { "No save loaded." },
            &HashSet::new(),
            &HashMap::new(),
            &statuses,
        )
    }

    fn card(report: &Value) -> &Value {
        &report["cards"][0]
    }

    #[test]
    fn a_missable_window_opens_then_checks_then_owns() {
        let index = index(json!({
            "kind": "missable", "tier": "community", "tier_rank": "B",
            "step": "sq301triss", "step_title": "A Matter of Life and Death",
            "event": "The party ends", "mechanism": "Win the rounds.",
            "source": {"name": "Reviewed guide", "url": "https://example.test", "reviewed": "2026-10-29"}
        }));
        let active = report(&index, false, true, "Active");
        assert_eq!(card(&active)["window_live"]["state"], "active");
        assert_eq!(card(&active)["window_live"]["label"], "OPEN NOW · COMMUNITY WINDOW");
        assert_eq!(card(&active)["window_live"]["tone"], "red");
        assert_eq!(active["counts"]["active"], 1);
        let passed = report(&index, false, true, "Done");
        assert_eq!(card(&passed)["window_live"]["state"], "check");
        assert_eq!(card(&passed)["window_live"]["label"], "PASSED - CHECK · COMMUNITY WINDOW");
        assert_eq!(passed["counts"]["check"], 1);
        let owned = report(&index, true, true, "Done");
        assert_eq!(card(&owned)["window_live"]["state"], "owned");
        assert_eq!(card(&owned)["window_live"]["label"], "COMMUNITY WINDOW");
        assert_eq!(card(&owned)["window_live"]["tone"], "green");
    }

    #[test]
    fn a_missing_collection_block_is_unknown_not_lost() {
        let index = index(json!({
            "kind": "missable", "tier": "community", "tier_rank": "B",
            "step": "sq301triss", "step_title": "A Matter of Life and Death",
            "event": "The party ends", "mechanism": "Win the rounds.",
            "source": {"name": "Reviewed guide", "url": "https://example.test", "reviewed": "2026-10-29"}
        }));
        let out = report(&index, false, false, "Done");
        assert_eq!(card(&out)["owned"], "unknown");
        assert_eq!(card(&out)["window_live"]["state"], "unknown");
        assert_eq!(card(&out)["window_live"]["label"], "COMMUNITY WINDOW");
        assert_eq!(out["counts"]["lost"], 0);
    }

    #[test]
    fn a_manual_tick_is_an_overlay_and_wins() {
        let index = index(json!({
            "kind": "none", "tier": "gamefile", "tier_rank": "A",
            "reason": "Persistent source."
        }));
        let collection = CardCollection { normal: HashMap::new(), leaders: HashMap::new() };
        let statuses = HashMap::new();
        let owned_manually = HashMap::from([("card_test".to_string(), true)]);
        let out = index.report(
            Some(&collection), true, "", &HashSet::new(), &owned_manually, &statuses,
        );
        assert_eq!(card(&out)["owned"], "owned");
        assert_eq!(card(&out)["note"], "manual");

        let mut normal = HashMap::new();
        normal.insert(1, 1);
        let owned_by_save = CardCollection { normal, leaders: HashMap::new() };
        let not_owned_manually = HashMap::from([("card_test".to_string(), false)]);
        let out = index.report(
            Some(&owned_by_save), true, "", &HashSet::new(), &not_owned_manually, &statuses,
        );
        assert_eq!(card(&out)["owned"], "not_owned");
        assert_eq!(card(&out)["note"], "manual");
    }

    #[test]
    fn card_top_items_group_by_step_and_keep_the_tier_b_tag() {
        let report = json!({
            "cards": [
                {
                    "name": "Card A",
                    "window": {"kind": "missable", "tier": "community", "tier_rank": "B",
                               "step": "sq301triss", "step_title": "A Matter of Life and Death",
                               "event": "The party ends", "mechanism": "Win the rounds.",
                               "evidence": [{"kind": "file", "value": "q301.w2phase"}]},
                    "window_live": {"state": "ahead", "tone": "amber",
                                    "label": "OPEN LATER · COMMUNITY WINDOW", "step": "sq301triss"}
                },
                {
                    "name": "Card B",
                    "window": {"kind": "missable", "tier": "community", "tier_rank": "B",
                               "step": "sq301triss", "step_title": "A Matter of Life and Death",
                               "event": "The party ends", "mechanism": "Win the rounds.",
                               "evidence": [{"kind": "file", "value": "q301.w2phase"}]},
                    "window_live": {"state": "ahead", "tone": "amber",
                                    "label": "OPEN LATER · COMMUNITY WINDOW", "step": "sq301triss"}
                }
            ]
        });
        let items = top_items(&report);
        assert!(items.is_empty(), "a window that has not opened is a ledger row, not a NOW warning");
        assert!(status_items(&report).is_empty(), "and it is not a STATUS row either");
    }

    #[test]
    fn a_closed_card_window_moves_to_status_not_the_band() {
        let report = json!({
            "cards": [{
                "name": "Card A",
                "window": {"kind": "missable", "tier": "community", "tier_rank": "B",
                           "step": "sq301triss", "step_title": "A Matter of Life and Death",
                           "event": "The party ends", "mechanism": "Win the rounds.",
                           "evidence": [{"kind": "file", "value": "q301.w2phase"}]},
                "window_live": {"state": "check", "tone": "amber", "label": "PASSED", "step": "sq301triss"}
            }]
        });
        assert!(top_items(&report).is_empty(), "a passed window is not actionable now");
        let status = status_items(&report);
        assert_eq!(status.len(), 1);
        assert!(status[0]["tag"].as_str().unwrap().contains("CHECK NOW"));
    }

    #[test]
    fn a_one_time_window_passes_without_a_hard_loss_claim() {
        let index = index(json!({
            "kind": "one_time", "tier": "gamefile", "tier_rank": "A",
            "step": "sq301triss", "step_title": "A Matter of Life and Death",
            "event": "The one-time source passes", "mechanism": "Scripted grant."
        }));
        let out = report(&index, false, true, "Done");
        assert_eq!(card(&out)["window_live"]["state"], "passed");
        assert_eq!(out["counts"]["one_time"], 1);
        assert_eq!(out["counts"]["lost"], 0);
    }

    #[test]
    fn a_window_opens_on_its_gate_and_checks_a_fallback() {
        let window = json!({
            "kind": "one_time", "tier": "gamefile", "tier_rank": "A",
            "step": "sq301triss", "step_title": "A Matter of Life and Death",
            "event": "The source passes", "mechanism": "Grant.",
            "opens": {"step": "gate"},
            "fallback": [{"kind": "container", "value": "The office"}]
        });
        let mut statuses = HashMap::from([
            ("sq301triss".to_string(), "Active".to_string()),
            ("gate".to_string(), "Not started".to_string()),
        ]);
        let ahead = window_live(&window, "not_owned", true, &HashSet::new(), &statuses);
        assert_eq!(ahead["state"], "ahead", "the closing step is active but the gate is not open");
        statuses.insert("gate".to_string(), "Active".to_string());
        let active = window_live(&window, "not_owned", true, &HashSet::new(), &statuses);
        assert_eq!(active["state"], "active");
        statuses.insert("gate".to_string(), "Done".to_string());
        let check = window_live(&window, "not_owned", true, &HashSet::new(), &statuses);
        assert_eq!(check["state"], "check", "a fallback keeps a passed source soft");
        assert!(check["label"].as_str().unwrap().contains("FALLBACK"));
        let mut no_fallback = window.clone();
        no_fallback.as_object_mut().unwrap().remove("fallback");
        let passed = window_live(&no_fallback, "not_owned", true, &HashSet::new(), &statuses);
        assert_eq!(passed["state"], "passed");
    }

    #[test]
    fn a_fact_gate_keeps_a_source_not_yet_until_the_save_has_it() {
        let window = json!({
            "kind": "one_time", "tier": "gamefile", "tier_rank": "A",
            "step": "cgnomansland", "step_title": "Gwent: Velen Players",
            "event": "The Baron's game ends", "mechanism": "Win the card.",
            "opens": {"step": "cgnomansland",
                      "requires": [{"kind": "fact", "value": "cg_baron_discovered"}]}
        });
        let statuses = HashMap::from([("cgnomansland".to_string(), "Active".to_string())]);
        let early = window_live(&window, "not_owned", true, &HashSet::new(), &statuses);
        assert_eq!(early["state"], "not_yet");
        assert!(early["label"].as_str().unwrap().contains("SOURCE NOT YET"));
        let facts = HashSet::from(["cg_baron_discovered".to_string()]);
        let open = window_live(&window, "not_owned", true, &facts, &statuses);
        assert_eq!(open["state"], "active");
    }

    #[test]
    fn the_shipped_dijkstra_window_is_open_before_the_baron_line_and_gone_after() {
        let data: Value = serde_json::from_str(include_str!("../data/gwent_cards.json")).unwrap();
        let index = CardIndex::from_json(&data);
        let facts = HashSet::from(["cg_baron_discovered".to_string()]);
        let empty = CardCollection { normal: HashMap::new(), leaders: HashMap::new() };
        let owned = CardCollection { normal: HashMap::from([(109, 1)]), leaders: HashMap::new() };
        let statuses = |gate: &str| HashMap::from([("cgnomansland".to_string(), gate.to_string())]);
        let row = |collection: &CardCollection, statuses: &HashMap<String, String>, facts: &HashSet<String>| {
            let report = index.report(Some(collection), true, "", facts, &HashMap::new(), statuses);
            report["cards"].as_array().unwrap().iter().find(|c| c["id"] == "card_dijkstra").unwrap().clone()
        };
        let live = |card: &Value| card["window_live"].clone();

        // The Baron is not in the save's facts yet: the source is not available, not missed.
        let early = row(&empty, &statuses("Active"), &HashSet::new());
        assert_eq!(early["owned"], "not_owned");
        assert_eq!(live(&early)["state"], "not_yet");
        assert!(live(&early)["label"].as_str().unwrap().contains("SOURCE NOT YET"));

        // Before the Baron line ends the invitation is open. A one-time row is never a band item.
        for gate in ["Not started", "Active"] {
            let report = index.report(Some(&empty), true, "", &facts, &HashMap::new(), &statuses(gate));
            let card = report["cards"].as_array().unwrap().iter().find(|c| c["id"] == "card_dijkstra").unwrap();
            assert_eq!(card["window_live"]["state"], if gate == "Active" { "active" } else { "ahead" });
            assert!(top_items(&report).is_empty(), "a one-time card is never a NOW row ({gate})");
            assert!(status_items(&report).is_empty(), "and never a STATUS row ({gate})");
        }

        // After the line the invitation is gone; the reviewed office fallback keeps it a check,
        // never a proved loss, and a one-time row still never reaches NOW or STATUS.
        let passed = row(&empty, &statuses("Done"), &facts);
        assert_eq!(live(&passed)["state"], "check");
        assert_eq!(live(&passed)["label"], "PASSED - CHECK FALLBACK · ONE-TIME · TIER A");
        let report = index.report(Some(&empty), true, "", &facts, &HashMap::new(), &statuses("Done"));
        assert!(top_items(&report).is_empty());
        assert!(status_items(&report).is_empty());

        // The save's own collection is the only thing that can say owned.
        let got = row(&owned, &statuses("Done"), &HashSet::new());
        assert_eq!(got["owned"], "owned");
        assert_eq!(live(&got)["state"], "owned");
    }

    #[test]
    fn the_shipped_iorveth_card_is_a_one_time_reward_and_never_a_band_row() {
        let data: Value = serde_json::from_str(include_str!("../data/gwent_cards.json")).unwrap();
        let index = CardIndex::from_json(&data);
        let empty = CardCollection { normal: HashMap::new(), leaders: HashMap::new() };
        let statuses = |gate: &str| HashMap::from([("mq2039vowofsilence".to_string(), gate.to_string())]);
        let card = |gate: &str| {
            let report = index.report(Some(&empty), true, "", &HashSet::new(), &HashMap::new(), &statuses(gate));
            report["cards"].as_array().unwrap().iter().find(|c| c["id"] == "card_iorveth").unwrap().clone()
        };

        // Iorveth is the completion reward of Shock Therapy, not a reviewed failure branch: the
        // shipped ledger must keep it a one-time source so it can never open a warning.
        let row = card("Active");
        assert_eq!(row["window"]["kind"], "one_time");
        assert_eq!(row["window"]["step"], "mq2039vowofsilence");
        assert_eq!(row["window"]["tier"], "community");

        // However the Shock Therapy journal state moves, a one-time row is never NOW or STATUS.
        for gate in ["Not started", "Active", "Done"] {
            let report = index.report(Some(&empty), true, "", &HashSet::new(), &HashMap::new(), &statuses(gate));
            assert!(top_items(&report).is_empty(), "Iorveth is not actionable now ({gate})");
            assert!(status_items(&report).is_empty(), "and not a settled check ({gate})");
        }
    }
}
