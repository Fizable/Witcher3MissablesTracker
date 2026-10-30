#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
//! Witcher 3 Missables Tracker (Tauri). Reads the newest save READ-ONLY, evaluates the route model, serves the UI.
//! Unofficial fan tool, not affiliated with CD PROJEKT RED.

mod bundles;
mod cards;
mod journalidx;
mod model;
mod outcomes;
mod plan;
mod save;
mod targets;

use model::{Eval, RouteData};
use targets::BranchGraph;
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::{Emitter, Manager, State};

const ALIASES: [(&str, &str); 7] = [
    ("q002vizimapalace", "Imperial Audience"),
    ("q401_ugliest_man_alive", "Ugly Baby (collecting Uma)"),
    ("q401_konsylium", "Ugly Baby (start)"),
    ("searchforugly", "Ugly Baby (journal)"),
    ("q403battle", "Battle Preparations (Kaer Morhen battle)"),
    ("q402ciri", "The Isle of Mists"),
    ("family", "Family Matters (Bloody Baron)"),
];

struct Inner {
    app_dir: PathBuf,    // per-user folder: progress, settings, cached quest index
    route: RouteData,
    db: save::QuestDb,
    db_error: String,
    game_dir: Option<PathBuf>,
    display: Vec<(String, String)>,
    derived: Value,                  // data/derived.json: what the game's own files say, built by tools/derive.py
    graph: Value,                    // data/quest_graph.json: starts / requires / lost_when, build source + evidence
    qtitles: HashMap<String, String>, // quest stem -> the game's own name, from derived.json
    // reviewed completion data
    endings: Value,                  // data/endings.json: targets and presets, never generated
    outcomes: Value,                 // data/outcomes.json: reviewed terminal facts and lines
    branches: BranchGraph,           // data/branches.json: fact-setting scene choices
    ending_branch_ids: HashSet<String>,
    cards: cards::CardIndex,         // data/gwent_cards.json
    coverage: Value,                 // data/coverage.json
    exclusive: Value,                // data/exclusive.json
    // selected target state
    selected: Vec<String>,
    guidance_on: bool,
    setup_v1: bool,
    card_manual: HashMap<String, bool>,
    // save state
    state: HashMap<String, String>,
    objective_guids: HashMap<String, Vec<String>>, // journal short -> active objective GUIDs
    objectives: HashMap<String, Vec<String>>,      // the save's own labels, debug only
    tracked: Option<String>,         // guid of the quest tracked in the game (read from the save)
    tracked_file: Option<String>,    // journal file of that quest, as the save names it
    facts: HashSet<String>,          // the game's facts this save has set (facts with a value of 1 or more)
    save_path: Option<PathBuf>,
    save_mtime: Option<SystemTime>,
    ok_mtime: Option<SystemTime>,
    error: String,
    // user progress
    ticks: HashSet<String>,
    level: i64,
    flags: HashMap<String, String>,
    saves_override: Option<String>,
    game_override: Option<String>,
    folder_msg: String,
}

struct Shared(Mutex<Inner>);

/// What the route counts as finished, split by how it knows.
///
/// `done` is the journal, or a tick where the save cannot show the step at all (a visit, a tutorial). `ticked` is
/// a step you ticked while the journal still has its quest open - the tick records your memory, the journal records
/// the game, and a warning may never be silenced by the weaker of the two.
#[derive(Default)]
struct DoneQuests {
    done: HashSet<String>,
    ticked: HashSet<String>,
}

fn read_json(p: &Path) -> Result<Value, String> {
    let t = std::fs::read_to_string(p).map_err(|e| format!("{}: {e}", p.display()))?;
    serde_json::from_str(&t).map_err(|e| format!("{}: {e}", p.display()))
}

fn find_data_dir() -> PathBuf {
    let mut cands: Vec<PathBuf> = Vec::new();
    if let Ok(p) = std::env::var("W3TRACKER_DATA") {
        cands.push(PathBuf::from(p));
    }
    if let Ok(exe) = std::env::current_exe() {
        for anc in exe.ancestors().take(6) {
            cands.push(anc.join("data"));
        }
    }
    cands.push(PathBuf::from("data"));
    cands.into_iter().find(|p| p.join("route.json").exists()).unwrap_or_else(|| PathBuf::from("data"))
}

fn find_app_dir(data_dir: &Path) -> PathBuf {
    let base = std::env::var("APPDATA").map(PathBuf::from).unwrap_or_else(|_| data_dir.to_path_buf());
    let d = base.join("Witcher3MissablesTracker");
    let _ = std::fs::create_dir_all(&d);
    d
}

/// Documents folder as Windows sees it (handles a moved Documents folder)
fn known_documents() -> Option<PathBuf> {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        let out = std::process::Command::new("reg")
            .args(["query", "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\User Shell Folders", "/v", "Personal"])
            .creation_flags(0x0800_0000)
            .output()
            .ok()?;
        let t = String::from_utf8_lossy(&out.stdout).to_string();
        let line = t.lines().find(|l| l.contains("Personal"))?;
        let idx = line.find("REG_")?;
        let val = line[idx..].split_whitespace().skip(1).collect::<Vec<_>>().join(" ");
        let profile = std::env::var("USERPROFILE").unwrap_or_default();
        return Some(PathBuf::from(val.replace("%USERPROFILE%", &profile)));
    }
    #[allow(unreachable_code)]
    None
}

fn saves_candidates() -> Vec<PathBuf> {
    let tail = Path::new("The Witcher 3").join("gamesaves");
    let mut docs: Vec<PathBuf> = Vec::new();
    let profile = std::env::var("USERPROFILE").unwrap_or_default();
    docs.push(Path::new(&profile).join("Documents"));
    if let Some(k) = known_documents() {
        docs.push(k);
    }
    for v in ["OneDrive", "OneDriveConsumer", "OneDriveCommercial"] {
        if let Ok(o) = std::env::var(v) {
            docs.push(Path::new(&o).join("Documents"));
        }
    }
    docs.into_iter().map(|d| d.join(&tail)).collect()
}

fn newest_in(dir: &Path) -> Option<(PathBuf, SystemTime)> {
    let rd = std::fs::read_dir(dir).ok()?;
    rd.filter_map(|e| e.ok())
        .filter(|e| e.path().extension().map(|x| x == "sav").unwrap_or(false))
        .filter_map(|e| Some((e.path(), e.metadata().ok()?.modified().ok()?)))
        .max_by_key(|(_, m)| *m)
}

/// the saves folder to use: the one with the newest save among the usual places
fn auto_saves_dir() -> Option<PathBuf> {
    let existing: Vec<PathBuf> = saves_candidates().into_iter().filter(|p| p.is_dir()).collect();
    let best = existing.iter().filter_map(|p| newest_in(p).map(|(_, m)| (p.clone(), m))).max_by_key(|(_, m)| *m).map(|(p, _)| p);
    best.or_else(|| existing.into_iter().next())
}

/// Bumped whenever `bundles::build_quest_db` would read the same game files differently. The stamp
/// alone is the game's own version, so without this a player who upgraded the tracker kept the index
/// built by the older rule: 0.1.6 shipped while the app was still reading a description entry's
/// status for quests whose journal file the builder had just learned to read from the quest entry,
/// and no amount of correct route data could fix what the save reader was told to look at.
/// v1: the journal's own CJournalQuest entry is read first (see bundles.rs).
const INDEX_VERSION: &str = "v1";

/// quest index built from the player's own game files, cached in the app folder until the game is patched
/// or the builder changes
fn load_quest_index(app_dir: &Path, game: &Path) -> Result<Value, String> {
    let cache = app_dir.join("quest_index.json");
    let stamp = format!("{}:{}", bundles::game_stamp(game), INDEX_VERSION);
    if let Ok(c) = read_json(&cache) {
        if c["stamp"].as_str() == Some(stamp.as_str()) && c["db"].is_object() {
            return Ok(c["db"].clone());
        }
    }
    let db = bundles::build_quest_db(game)?;
    let _ = std::fs::write(&cache, serde_json::to_string(&json!({"stamp": stamp, "db": db})).unwrap_or_default());
    Ok(db)
}

/// game entry names carry an internal id: 'mq3005 Shady Deal' -> 'Shady Deal' (names without one are kept)
fn clean_name(s: &str) -> String {
    let t = s.trim();
    if let Some(i) = t.find(|c: char| c.is_ascii_digit()) {
        if i <= 4 && t[..i].chars().all(|c| c.is_ascii_alphabetic()) {
            let rest = t[i..].trim_start_matches(|c: char| c.is_ascii_digit()).trim_start_matches(|c: char| c == '_' || c == ' ');
            if rest.len() >= 3 {
                return rest.to_string();
            }
        }
    }
    t.to_string()
}

impl Inner {
    fn load(data_dir: PathBuf) -> Result<Inner, String> {
        let app_dir = find_app_dir(&data_dir);
        let route = model::load_route(&read_json(&data_dir.join("route.json"))?)?;
        // progress lives in the per-user folder (an old copy next to the exe is migrated once)
        let prog = read_json(&app_dir.join("progress.json")).or_else(|_| read_json(&data_dir.join("progress.json"))).unwrap_or(json!({}));
        let ticks: HashSet<String> = prog["ticks"].as_array().into_iter().flatten().filter_map(|x| x.as_str().map(String::from)).collect();
        let level = prog["level"].as_i64().unwrap_or(0);
        let flags: HashMap<String, String> = prog["flags"].as_object().map(|m| m.iter().filter_map(|(k, v)| Some((k.clone(), v.as_str()?.to_string()))).collect()).unwrap_or_default();
        let settings = read_json(&app_dir.join("settings.json")).unwrap_or(json!({}));
        // derived from the player's copy of the game's files by tools/derive.py; absent is not an error
        let derived = read_json(&data_dir.join("derived.json")).unwrap_or(json!({"steps": {}, "quests": {}}));
        // the build graph: start blocks and the reviewed loss edges, used as evidence in the detail pane
        let graph = read_json(&data_dir.join("quest_graph.json")).unwrap_or(json!({"starts": {}, "requires": {}, "lost_when": []}));
        let endings = read_json(&data_dir.join("endings.json")).unwrap_or(json!({"version": 1, "targets": {}, "presets": {}}));
        let outcomes = read_json(&data_dir.join("outcomes.json")).unwrap_or(json!({"version": 1, "groups": {}, "outcomes": {}}));
        let branches_doc = read_json(&data_dir.join("branches.json")).unwrap_or(json!({"version": 1, "branches": {}}));
        let branches = BranchGraph::from_json(&branches_doc);
        let mut ending_branch_ids = BranchGraph::ending_branch_ids(&endings);
        ending_branch_ids.extend(outcomes::branch_ids(&outcomes));
        let cards = cards::CardIndex::from_json(&read_json(&data_dir.join("gwent_cards.json")).unwrap_or(json!({"cards": []})));
        let coverage = read_json(&data_dir.join("coverage.json")).unwrap_or(json!({"packs": {}}));
        let exclusive = read_json(&data_dir.join("exclusive.json")).unwrap_or(json!({"edges": []}));
        let known_targets: HashSet<String> = targets::all_ids(&endings).into_iter().collect();
        let mut selected: Vec<String> = settings["endings"]
            .as_array()
            .map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect())
            .unwrap_or_default();
        selected.retain(|id| known_targets.contains(id));
        selected = targets::canonical_ids(&endings, selected);
        let mut guidance_on = !selected.is_empty() && settings["guidance"].as_str() == Some("on");
        if selected.is_empty() {
            guidance_on = false;
        }
        let mut setup_v1 = settings["setup_v1"].as_bool().unwrap_or(false);
        if !selected.is_empty() {
            setup_v1 = true;
        }
        let card_manual: HashMap<String, bool> = prog["cards"]
            .as_object()
            .map(|m| m.iter().filter_map(|(k, v)| Some((k.clone(), v.as_bool()?))).collect())
            .unwrap_or_default();
        // the game's own names, so a warning can name the quest it is talking about instead of its stem
        let qtitles: HashMap<String, String> = derived
            .get("quests")
            .and_then(|q| q.as_object())
            .map(|m| m.iter().filter_map(|(k, v)| Some((k.to_ascii_lowercase(), v.get("title")?.as_str()?.to_string()))).collect())
            .unwrap_or_default();
        let mut inner = Inner {
            app_dir,
            route,
            derived,
            graph,
            qtitles,
            endings,
            outcomes,
            branches,
            ending_branch_ids,
            cards,
            coverage,
            exclusive,
            selected,
            guidance_on,
            setup_v1,
            card_manual,
            db: save::QuestDb { quests: vec![], display: vec![] },
            db_error: String::new(),
            game_dir: None,
            display: vec![],
            state: HashMap::new(),
            objective_guids: HashMap::new(),
            objectives: HashMap::new(),
            tracked: None,
            tracked_file: None,
            facts: HashSet::new(),
            save_path: None,
            save_mtime: None,
            ok_mtime: None,
            error: String::new(),
            ticks,
            level,
            flags,
            saves_override: settings["saves_dir"].as_str().map(String::from),
            game_override: settings["game_dir"].as_str().map(String::from),
            folder_msg: String::new(),
        };
        let g = inner.game_override.clone();
        inner.setup_game(g.as_deref());
        Ok(inner)
    }

    /// locate the game and (re)build the quest index
    fn setup_game(&mut self, configured: Option<&str>) {
        self.save_path = None;
        self.ok_mtime = None;
        match bundles::find_game_dir(configured) {
            None => {
                self.game_dir = None;
                self.db_error = "Could not find your Witcher 3 install. Pick the game folder under 'my game' (the folder that contains 'content' and 'bin').".into();
                self.db = save::QuestDb { quests: vec![], display: vec![] };
            }
            Some(g) => match load_quest_index(&self.app_dir, &g) {
                Ok(v) => {
                    self.db = save::load_db(&v);
                    self.db_error.clear();
                    self.game_dir = Some(g);
                }
                Err(e) => {
                    self.game_dir = Some(g);
                    self.db_error = format!("Could not read the quest list from your game files: {e}");
                    self.db = save::QuestDb { quests: vec![], display: vec![] };
                }
            },
        }
        self.rebuild_display();
    }

    fn rebuild_display(&mut self) {
        // readable names: first entry name, then alias, then the route title for single-file nodes
        let mut display = self.db.display.clone();
        for (short, name) in display.iter_mut() {
            *name = clean_name(name);
            if let Some((_, a)) = ALIASES.iter().find(|(k, _)| k == short) {
                *name = a.to_string();
            }
        }
        for n in &self.route.nodes {
            if n.files.len() == 1 && !n.files[0].contains('#') && !n.files[0].contains('|') {
                if let Some(e) = display.iter_mut().find(|(s, _)| *s == n.files[0]) {
                    e.1 = model::short(&n.title).to_string();
                }
            }
        }
        self.display = display;
    }

    fn saves_dir(&self) -> Option<PathBuf> {
        if let Some(o) = &self.saves_override {
            let p = PathBuf::from(o);
            if p.is_dir() {
                return Some(p);
            }
        }
        auto_saves_dir()
    }

    /// Write the app's settings immediately, preserving keys this version does not know about. A
    /// temporary file in the same folder followed by a rename keeps a crash from truncating it.
    fn write_settings(&self) {
        let path = self.app_dir.join("settings.json");
        let mut doc = read_json(&path)
            .ok()
            .and_then(|v| v.as_object().cloned())
            .unwrap_or_default();
        doc.insert("game_dir".into(), json!(self.game_override));
        doc.insert("saves_dir".into(), json!(self.saves_override));
        doc.insert("endings".into(), json!(self.selected));
        doc.insert("guidance".into(), json!(if self.guidance_on { "on" } else { "off" }));
        doc.insert("setup_v1".into(), json!(self.setup_v1));
        let text = serde_json::to_string(&Value::Object(doc)).unwrap_or_default();
        let tmp = path.with_extension("json.tmp");
        if std::fs::write(&tmp, text).is_ok() {
            let _ = std::fs::rename(&tmp, &path);
        }
    }

    fn set_target(&mut self, ids: Vec<String>) -> Result<(), String> {
        let known: HashSet<String> = targets::all_ids(&self.endings).into_iter().collect();
        if let Some(bad) = ids.iter().find(|id| !known.contains(*id)) {
            return Err(format!("unknown ending target: {bad}"));
        }
        self.selected = targets::canonical_ids(&self.endings, ids);
        self.guidance_on = !self.selected.is_empty();
        self.setup_v1 = true;
        self.write_settings();
        Ok(())
    }

    fn set_guidance(&mut self, on: bool) {
        self.guidance_on = on && !self.selected.is_empty();
        self.write_settings();
    }

    fn target_evals(&self, ev: &Eval) -> HashMap<String, targets::TargetEval> {
        let ok = self.ok_mtime.is_some();
        let mut out = targets::evaluate(&self.endings, &self.branches, ev, &self.facts, ok);
        out.extend(outcomes::evaluate_targets(&self.endings, &self.outcomes, ev, &self.facts, ok));
        out
    }

    /// The opt-in outcome matrix. It is never part of `view()`: the spoiler-free payload must not
    /// receive an ending label or a terminal description.
    fn outcome_report(&self) -> Value {
        let ev = self.eval();
        outcomes::matrix(
            &self.endings,
            &self.outcomes,
            &self.exclusive,
            &ev,
            &self.facts,
            self.ok_mtime.is_some(),
            &self.selected,
        )
    }

    fn plan_report(&self, requested: Option<Vec<String>>) -> Value {
        let ev = self.eval();
        let ids = requested.unwrap_or_else(|| self.selected.clone());
        let mut plan = plan::build(
            &self.endings,
            &self.outcomes,
            &ids,
            &ev,
            &self.facts,
            self.ok_mtime.is_some(),
            &self.exclusive,
        );
        // Guidance off gates the exact lines, not the plan. The plan, its step titles and its goal
        // chips survive; only `instructions` are removed, and they are removed here so no caller
        // can leak a line.
        gate_instructions(&mut plan, self.guidance_on);
        plan
    }

    fn cards_report(&self) -> Value {
        // A card window reads the same route statuses the quest matrix reads; ownership is still
        // only the save or a manual tick, never the quest status.
        let ev = self.eval();
        let statuses: HashMap<String, String> = ev
            .steps
            .iter()
            .map(|s| (s.n.id.clone(), s.status.clone()))
            .collect();
        let Some(path) = self.save_path.as_ref() else {
            return self.cards.report(None, false, "No save loaded.", &self.facts, &self.card_manual, &statuses);
        };
        match save::card_collection(path) {
            Ok(col) => self.cards.report(Some(&col), true, "", &self.facts, &self.card_manual, &statuses),
            Err(e) => self.cards.report(None, false, &e, &self.facts, &self.card_manual, &statuses),
        }
    }

    fn set_card(&mut self, id: String, owned: bool) -> Result<(), String> {
        if !self.cards.cards.iter().any(|c| c.id == id) {
            return Err(format!("unknown card: {id}"));
        }
        self.card_manual.insert(id, owned);
        self.save_progress();
        Ok(())
    }

    /// apply a folder the user typed or picked ("game" or "saves"); returns an error text when it is not valid
    fn apply_folder(&mut self, kind: &str, path: &str) {
        let p = path.trim().trim_matches('"').to_string();
        self.folder_msg.clear();
        if p.is_empty() {
            // empty = go back to automatic detection
            if kind == "game" {
                self.game_override = None;
                self.write_settings();
                self.setup_game(None);
            } else {
                self.saves_override = None;
                self.write_settings();
            }
        } else if kind == "game" {
            if bundles::is_game_dir(Path::new(&p)) {
                self.game_override = Some(p.clone());
                self.write_settings();
                self.setup_game(Some(&p));
            } else {
                self.folder_msg = format!("'{p}' is not a Witcher 3 folder. It must contain content\\content0\\bundles.");
                return;
            }
        } else if Path::new(&p).is_dir() {
            self.saves_override = Some(p.clone());
            self.write_settings();
            if newest_in(Path::new(&p)).is_none() {
                self.folder_msg = "That folder has no .sav files yet. The tracker will use it as soon as one appears.".into();
            }
        } else {
            self.folder_msg = format!("'{p}' is not a folder.");
            return;
        }
        self.save_path = None;
        self.ok_mtime = None;
        self.error.clear();
        self.refresh_save();
    }

    /// Re-read the newest save if it changed. Returns true when the visible state changed.
    fn refresh_save(&mut self) -> bool {
        let dir = self.saves_dir();
        let Some((p, m)) = dir.as_ref().and_then(|d| newest_in(d)) else {
            let msg = match dir {
                Some(d) => format!("No save found in {}. Pick your saves folder under 'my game' if it is somewhere else.", d.display()),
                None => "Could not find your Witcher 3 saves folder. Pick it under 'my game'.".to_string(),
            };
            if self.error != msg {
                self.error = msg;
                return true;
            }
            return false;
        };
        if self.save_path.as_ref() == Some(&p) && self.ok_mtime == Some(m) {
            return false;
        }
        self.save_path = Some(p.clone());
        self.save_mtime = Some(m);
        match save::quest_states(&p, &self.db) {
            Ok(s) => {
                self.state = s.state;
                self.objective_guids = s.objective_guids;
                self.objectives = s.objectives;
                self.tracked = s.tracked;
                self.tracked_file = s.tracked_file;
                self.facts = s.facts;
                self.ok_mtime = Some(m);
                self.error.clear();
            }
            Err(e) => {
                // The game may still be writing the file: keep the old state and retry on the next
                // poll, but name the file and the next step so the header is not a placeholder.
                let name = p.file_name().and_then(|n| n.to_str()).unwrap_or("the newest save");
                self.error = format!(
                    "Could not read {name}: {e}. If the game is running, the tracker retries automatically; otherwise pick another save or check the saves folder under 'my game'."
                );
            }
        }
        true
    }

    /// The active objectives of a quest, in the game's own wording. The save carries GUIDs; the
    /// labels built by the game's bundles are internal ("SQ202 At Larvik"), so the text comes from
    /// the same derived index the cards use.
    fn current_objectives(&self, id: &str, files: &[String]) -> Vec<String> {
        let listed = self.derived.get("steps").and_then(|m| m.get(id))
            .and_then(|d| d.get("objectives")).and_then(|x| x.as_array());
        let mut out: Vec<String> = Vec::new();
        for f in files {
            let stem = f.split('#').next().unwrap_or(f);
            let (Some(guids), Some(list)) = (self.objective_guids.get(stem), listed) else { continue };
            for guid in guids {
                let text = list.iter()
                    .find(|o| o.get("guid").and_then(|x| x.as_str()) == Some(guid.as_str()))
                    .and_then(|o| o.get("text")).and_then(|x| x.as_str());
                if let Some(t) = text {
                    if !t.is_empty() && !out.iter().any(|x| x == t) {
                        out.push(t.to_string());
                    }
                }
            }
        }
        out
    }

    /// the route plus a card for the quest tracked in the game, when no route step covers that quest
    fn effective_route(&self) -> RouteData {
        let mut rt = self.route.clone();
        // A reviewed ending target names a fact a scene branch sets. Mark the step at runtime so the
        // card, the detail pane and the NOW band read one answer; route.json stays generated data.
        let ending = self.ending_branch_steps();
        for n in rt.nodes.iter_mut() {
            if ending.contains(&n.id) {
                n.ending_relevant = true;
            }
        }
        let Some(short) = self.tracked_short() else { return rt };
        if rt.nodes.iter().any(|n| model::tracks(n, &short)) {
            return rt;
        }
        // The 0.2 route covers every quest journal, so this is only reached for a save the game
        // builds from something the route does not know (a debug or cut container). Name it from
        // the save's own display list; do not invent a section, a level or a note for it.
        let title = self.display.iter().find(|(k, _)| *k == short).map(|(_, d)| d.clone()).unwrap_or_else(|| short.clone());
        let lv = "".to_string();
        rt.nodes.push(model::Node {
            section: "Tracked".into(),
            id: format!("tracked_{short}"),
            title,
            lv,
            files: vec![short],
            hard: vec![],
            hard_facts: HashMap::new(),
            by: vec![],
            note: String::new(),
            kind: "side".into(),
            opt: false,
            when: vec![],
            order: 0,
            desc: String::new(),
            branch: false,
            dialogue_choice: false,
            ending_relevant: false,
            start_known: false,
            provenance: "save_only".into(),
            review_reason: String::new(),
            review_source: String::new(),
            reviewed: String::new(),
        });
        rt
    }

    /// Steps whose own scene sections set a fact a reviewed ending target needs. This is the
    /// spoiler-free existence proof behind the NOW choice warning: the step is named, the choice
    /// text and the recommended option are never part of it.
    fn ending_branch_steps(&self) -> HashSet<String> {
        self.branches
            .by_step
            .iter()
            .filter(|(_, rows)| rows.iter().any(|b| self.ending_branch_ids.contains(&b.id)))
            .map(|(step, _)| step.clone())
            .collect()
    }

    fn eval(&self) -> Eval {
        model::evaluate(&self.effective_route(), &self.state, &self.ticks, &self.flags, &self.facts)
    }

    /// Every fact-gated prerequisite in the route and whether this save has the game's own condition for
    /// it set. Written out by `--dump` so tools/contradictions.py can check the settlement against what
    /// the app actually did with a real save, not only against the data files.
    fn gates(&self, ev: &Eval) -> Value {
        let mut out: Vec<Value> = Vec::new();
        for s in ev.steps.iter() {
            for (h, facts) in s.n.hard_facts.iter() {
                let set: Vec<&String> = facts.iter().filter(|f| self.facts.contains(*f)).collect();
                out.push(json!({
                    "step": s.n.id,
                    "requires": h,
                    "prereq_status": ev.byid.get(h).map(|&j| ev.steps[j].status.clone()).unwrap_or_default(),
                    "facts": facts,
                    "set": set,
                    "locked": !s.locked.is_empty(),
                }));
            }
        }
        Value::Array(out)
    }

    /// the journal quest file (short name) of the quest tracked in the game, if the tracker knows it
    fn tracked_short(&self) -> Option<String> {
        self.tracked_file.clone().or_else(|| self.tracked.as_deref().and_then(|g| save::quest_for_guid(&self.db, g)))
    }

    /// the route steps of the tracked quest that are still open (held-back and lost ones included, so they can be warned about)
    fn tracked_steps(&self, ev: &Eval, short: &str) -> Vec<usize> {
        (0..ev.steps.len()).filter(|&i| model::tracks(&ev.steps[i].n, short) && !matches!(ev.steps[i].status.as_str(), "Done" | "N/A")).collect()
    }

    /// DO NEXT order, from the live cutoff boxes the view already computed.
    ///
    /// A step that a fired cutoff already cost is `unsafe`: it is not something to do, it is in the
    /// top section. A step that is the closing quest of a live cutoff is unsafe too: doing it costs
    /// another open quest, and the top section names it. The protected quest is `caution` - it keeps
    /// its place in DO NEXT, with the warning above it.
    fn todo_order(&self, ev: &Eval, steps: &[Value], next_plan: Option<&str>) -> Vec<usize> {
        let mut unsafe_ids: HashSet<usize> = HashSet::new();
        let mut caution: HashSet<usize> = HashSet::new();
        for (i, v) in steps.iter().enumerate() {
            let Some(list) = v.get("watch").and_then(|x| x.as_array()) else { continue };
            let mut live_here = false;
            for w in list {
                let Some(live) = w.get("live").and_then(|x| x.as_str()) else { continue };
                if live.is_empty() {
                    continue;
                }
                live_here = true;
                if matches!(live, "passed" | "lost") {
                    unsafe_ids.insert(i);
                }
                if matches!(live, "inside" | "ahead") {
                    for c in w.get("closed_by").and_then(|x| x.as_array()).into_iter().flatten().filter_map(|x| x.as_str()) {
                        for (j, s) in ev.steps.iter().enumerate() {
                            if model::tracks(&s.n, c) {
                                unsafe_ids.insert(j);
                            }
                        }
                    }
                }
            }
            if live_here && !unsafe_ids.contains(&i) {
                caution.insert(i);
            }
        }
        model::todo_order(ev, self.tracked_short().as_deref(), &unsafe_ids, &caution, next_plan)
    }

    /// the quest tracked in the game for the UI (null when the save has none)
    fn tracked_json(&self, ev: &Eval) -> Value {
        if self.tracked.is_none() {
            return Value::Null;
        }
        let Some(short) = self.tracked_short() else {
            return json!({"short": "", "display": "a quest the tracker does not know yet", "status": "", "steps": [], "warning": null});
        };
        let display = self.display.iter().find(|(k, _)| *k == short).map(|(_, d)| d.clone()).unwrap_or_else(|| short.clone());
        let steps: Vec<String> = self.tracked_steps(ev, &short).iter().map(|&i| ev.steps[i].n.id.clone()).collect();
        let warning = model::tracked_warning(ev, &short).map(|(level, headline, details)| json!({"level": level, "headline": headline, "details": details}));
        json!({"short": short, "display": display, "status": self.state.get(&short).cloned().unwrap_or_default(), "steps": steps, "warning": warning})
    }

    /// Attach what the game's own files say about a step: the game's name for it, its quest-log
    /// objective list, the block that adds its journal entry, its dialogue choices, and the
    /// reviewed cutoffs (each naming the mechanism behind it).
    /// Quests the route already counts as finished - including a step you ticked yourself - so a warning
    /// never contradicts the step card beside it. A tick that the journal contradicts is kept apart instead:
    /// it must not answer for a quest the save still carries as open.
    fn done_quests(&self, ev: &model::Eval) -> DoneQuests {
        let mut out = DoneQuests::default();
        for s in &ev.steps {
            if !matches!(s.status.as_str(), "Done" | "Assumed" | "N/A") {
                continue;
            }
            let Some(d) = self.derived.get("steps").and_then(|m| m.get(&s.n.id)) else { continue };
            let journal = if s.manual { "Not started".to_string() } else { model::journal_status(&s.n, &self.state) };
            let tick_disagrees = self.ticks.contains(&s.n.id) && journal == "Active";
            for k in ["quests", "stems"] {
                for q in d.get(k).and_then(|v| v.as_array()).into_iter().flatten().filter_map(|x| x.as_str()) {
                    let q = q.to_ascii_lowercase();
                    if tick_disagrees {
                        out.ticked.insert(q);
                    } else {
                        out.done.insert(q);
                    }
                }
            }
        }
        out
    }

    fn attach_derived(&self, step: &mut Value, st: &model::Step, done_q: &DoneQuests) {
        let Some(id) = step.get("id").and_then(|v| v.as_str()).map(|s| s.to_string()) else { return };
        let Some(d) = self.derived.get("steps").and_then(|s| s.get(&id)) else { return };
        for k in ["game_title", "objectives", "activators", "watch", "stems"] {
            if let Some(v) = d.get(k) {
                if !v.is_null() {
                    step[k] = v.clone();
                }
            }
        }
        // each cutoff is read against this save: one that protects something already finished is dropped,
        // one that already fired reads as the loss it is, and one you are standing inside says so.
        // A step ticked done while the journal still has its quest open is not over: the cutoff stays on the card.
        let journal = if st.manual { "Not started".to_string() } else { model::journal_status(&st.n, &self.state) };
        let tick_only = self.ticks.contains(&st.n.id) && journal == "Active";
        let over = matches!(st.status.as_str(), "Done" | "Failed" | "N/A") && !tick_only;
        if let Some(Value::Array(list)) = step.get_mut("watch") {
            if over {
                list.clear();
            } else {
                list.retain_mut(|w| model::live_warning(w, &self.state, &self.qtitles, &done_q.done, &done_q.ticked));
            }
        }
    }

    /// The live reviewed warning for a journal quest, read against this save exactly as the step
    /// card reads it. Both the search box and the detail pane answer from here, so one quest cannot
    /// be `safe` on its own page and `at risk` in search.
    fn live_watch_for(&self, ev: &Eval, short_name: &str) -> Option<Value> {
        let i = model::step_for_short(ev, short_name)?;
        let d = self.derived.get("steps")?.get(&ev.steps[i].n.id)?;
        let mut list = d.get("watch")?.as_array()?.clone();
        let done_q = self.done_quests(ev);
        list.retain_mut(|w| model::live_warning(w, &self.state, &self.qtitles, &done_q.done, &done_q.ticked));
        list.into_iter().next()
    }

    /// One save-aware verdict. The route model answers first; a reviewed warning that is still
    /// live in this save outranks it, because it names what is lost and what to do instead.
    fn verdict_for(&self, rt: &RouteData, ev: &Eval, short_name: &str) -> Value {
        let display = self
            .display
            .iter()
            .find(|(k, _)| k == short_name)
            .map(|(_, d)| d.clone())
            .unwrap_or_else(|| short_name.to_string());
        let mut out = model::verdict_json(&model::check_quest(rt, ev, short_name, &self.state), &display);
        let Some(w) = self.live_watch_for(ev, short_name) else { return out };
        let Some(live) = w.get("live").and_then(|x| x.as_str()) else { return out };
        let (verdict, headline) = match live {
            "lost" => ("stop", w.get("headline").cloned().unwrap_or(Value::Null)),
            "inside" | "check" | "passed" => ("stop", w.get("headline").cloned().unwrap_or(Value::Null)),
            "ahead" => ("warn", w.get("headline").cloned().unwrap_or(Value::Null)),
            // settled, missed, unknown: the journal has answered the question, so the route
            // model's own verdict stands and the warning is not repeated as advice
            _ => return out,
        };
        let mut details: Vec<Value> = Vec::new();
        if let Some(x) = w.get("why").filter(|v| !v.is_null()) {
            details.push(x.clone());
        }
        if let Some(x) = w.get("action").and_then(|x| x.as_str()).filter(|s| !s.is_empty()) {
            details.push(json!(format!("Do this first: {x}.")));
        }
        if let Some(x) = w.get("live_note").filter(|v| !v.is_null()) {
            details.push(x.clone());
        }
        out["verdict"] = json!(verdict);
        out["headline"] = headline;
        out["details"] = json!(details);
        out["from_game_files"] = json!(true);
        out["evidence"] = w.get("evidence").cloned().unwrap_or_else(|| json!("files+saves"));
        out
    }

    /// Completion is not a single percentage. The audited matrix has 412 route nodes (403 quests +
    /// 9 reviewed manual rows); the old 403-only quest line stays for callers that already read it,
    /// while `matrix` carries all six states and the manual split. Cards keep `unknown` separate
    /// from `not owned`. A save-only row is counted in `outside_route`, never in the 412.
    fn completion(&self, ev: &Eval, steps: &[Value], card_report: &Value) -> Value {
        let slot = |s: &str| match s {
            "done" => 0,
            "obtainable" => 1,
            "at_risk" => 2,
            "lost" => 3,
            "excluded" => 4,
            _ => 5,
        };
        let mut q = [0i64; 6];
        let mut m = [0i64; 6];
        let mut mx = [0i64; 6];
        let mut outside = 0i64;
        let mut exclusions: Vec<Value> = Vec::new();
        // The matrix owns both the overall totals and the per-section totals. The UI reads these
        // counts rather than recounting statuses, so the section headers cannot drift from the
        // matrix line when a node is manual, optional or excluded.
        let mut section_counts: HashMap<String, [i64; 6]> = self
            .route
            .sections
            .iter()
            .map(|name| (name.clone(), [0i64; 6]))
            .collect();
        let mut section_manual: HashMap<String, i64> = HashMap::new();
        for (i, s) in ev.steps.iter().enumerate() {
            let c = steps[i].get("classification").cloned().unwrap_or_else(|| json!({}));
            let state = c.get("state").and_then(|x| x.as_str()).unwrap_or("unknown");
            let k = slot(state);
            if steps[i].get("in_route").and_then(Value::as_bool) == Some(true) {
                mx[k] += 1;
                if s.manual { m[k] += 1 } else { q[k] += 1 }
                let sc = section_counts.entry(s.n.section.clone()).or_insert([0i64; 6]);
                sc[k] += 1;
                if s.manual {
                    *section_manual.entry(s.n.section.clone()).or_insert(0) += 1;
                }
                if state == "excluded" {
                    exclusions.push(json!({
                        "id": s.n.id, "title": model::short(&s.n.title),
                        "mechanism": s.n.when, "reason": c.get("reason").cloned().unwrap_or(Value::Null),
                    }));
                }
            } else {
                outside += 1;
            }
        }
        let sum = |a: [i64; 6]| a.iter().sum::<i64>();
        let (qt, mt, mxt) = (sum(q), sum(m), sum(mx));
        let mut sections = serde_json::Map::new();
        for name in &self.route.sections {
            let a = section_counts.get(name).copied().unwrap_or([0i64; 6]);
            sections.insert(name.clone(), json!({
                "total": sum(a),
                "done": a[0],
                "obtainable": a[1],
                "at_risk": a[2],
                "lost": a[3],
                "excluded": a[4],
                "unknown": a[5],
                "manual": section_manual.get(name).copied().unwrap_or(0),
            }));
        }
        let audit = &self.route.manual_audit;
        let baseline = audit.get("baseline").and_then(|x| x.as_i64()).unwrap_or(11);
        let replaced = audit.get("replaced").and_then(|x| x.as_i64()).unwrap_or(2);
        let cc = card_report.get("counts").cloned().unwrap_or_else(|| json!({}));
        let card_total = cc.get("total").and_then(|x| x.as_i64()).unwrap_or(0);
        let card_owned = cc.get("owned").and_then(|x| x.as_i64()).unwrap_or(0);
        let card_available = cc.get("not_owned").and_then(|x| x.as_i64()).unwrap_or(0);
        let card_unknown = cc.get("unknown").and_then(|x| x.as_i64()).unwrap_or(0);
        let card_missable = cc.get("missable").and_then(|x| x.as_i64()).unwrap_or(0);
        let card_at_risk = cc.get("active").and_then(|x| x.as_i64()).unwrap_or(0);
        let card_ahead = cc.get("ahead").and_then(|x| x.as_i64()).unwrap_or(0);
        let card_check = cc.get("check").and_then(|x| x.as_i64()).unwrap_or(0);
        let card_windows_lost = cc.get("lost").and_then(|x| x.as_i64()).unwrap_or(0);
        let card_tier_a = cc.get("tier_a").and_then(|x| x.as_i64()).unwrap_or(0);
        let card_tier_b = cc.get("tier_b").and_then(|x| x.as_i64()).unwrap_or(0);
        let card_missable_tier_a = cc.get("missable_tier_a").and_then(|x| x.as_i64()).unwrap_or(0);
        let card_missable_tier_b = cc.get("missable_tier_b").and_then(|x| x.as_i64()).unwrap_or(0);
        json!({
            "quests": {
                "done": q[0],
                "available": q[1],
                "at_risk": q[2],
                "lost": q[3],
                "excluded": q[4],
                "unknown": q[5],
                "total": qt,
                "max_achievable": q[0] + q[1] + q[2],
            },
            "matrix": {
                "total": mxt,
                "quests": qt,
                "manual": mt,
                "done": mx[0],
                "obtainable": mx[1],
                "at_risk": mx[2],
                "lost": mx[3],
                "excluded": mx[4],
                "unknown": mx[5],
                "max_achievable": mx[0] + mx[1] + mx[2],
                "outside_route": outside,
                "sections": sections,
                "manual_audit": audit,
            },
            "manual": {
                "baseline": baseline,
                "kept": mt,
                "replaced": replaced,
                "reviewed": mt,
                "done": m[0],
                "obtainable": m[1],
                "at_risk": m[2],
                "lost": m[3],
                "excluded": m[4],
                "unknown": m[5],
            },
            "exclusions": exclusions,
            "cards": {
                "owned": card_owned,
                "available": card_available,
                "at_risk": card_at_risk,
                "ahead": card_ahead,
                "check": card_check,
                "lost": card_windows_lost,
                "excluded": 0,
                "unknown": card_unknown,
                "total": card_total,
                "missable": card_missable,
                "window_tier_a": card_tier_a,
                "window_tier_b": card_tier_b,
                "missable_tier_a": card_missable_tier_a,
                "missable_tier_b": card_missable_tier_b,
                "max_achievable": card_owned + card_available,
            },
        })
    }

    /// The top section: only what still has a cost in this save.
    ///
    /// One entry per reviewed loss edge, already re-read against the save by `live_cutoff`: a cutoff
    /// that fired over an open quest is a loss, one whose closing quest is in the log is urgent, and
    /// one whose closer is still ahead is missable. `settled`/`unknown`/done never reach here. A
    /// Failed quest is its own entry. The list is empty when nothing is at stake - no heading, no
    /// reassuring placeholder.
    fn view(&self) -> Value {
        let rt = self.effective_route();
        let ev = model::evaluate(&rt, &self.state, &self.ticks, &self.flags, &self.facts);
        let target_evals = self.target_evals(&ev);
        // Goal chips and PLAN AHEAD survive guidance being off; only exact instructions are gated.
        let goal_steps = targets::goal_steps(&self.selected, &target_evals);
        // The one plan step UP NEXT may add: the first ahead step in plan order that the save has
        // not locked. Everything else ahead stays in the collapsed PLAN AHEAD line.
        let next_plan = if self.selected.is_empty() {
            None
        } else {
            self.plan_report(None)
                .get("steps")
                .and_then(|x| x.as_array())
                .and_then(|a| {
                    a.iter().find(|s| {
                        s.get("state").and_then(|x| x.as_str()) == Some("ahead")
                            && s.get("step")
                                .and_then(|x| x.as_str())
                                .and_then(|id| ev.byid.get(id))
                                .map(|&i| ev.steps[i].locked.is_empty())
                                .unwrap_or(false)
                    })
                })
                .and_then(|s| s.get("step"))
                .and_then(|x| x.as_str())
                .map(String::from)
        };
        let age = self.save_mtime.and_then(|m| SystemTime::now().duration_since(m).ok()).map(|d| d.as_secs()).unwrap_or(0);
        let name = self.save_path.as_ref().and_then(|p| p.file_name()).and_then(|n| n.to_str()).unwrap_or("");
        let mut steps: Vec<Value> = (0..ev.steps.len())
            .map(|i| model::step_json_goal(&rt, &ev, i, goal_steps.contains(&ev.steps[i].n.id)))
            .collect();
        let done_q = self.done_quests(&ev);
        let route_ids: HashSet<String> = self.route.nodes.iter().map(|n| n.id.clone()).collect();
        for (i, s) in steps.iter_mut().enumerate() {
            self.attach_derived(s, &ev.steps[i], &done_q);
            let watch = s.get("watch").and_then(Value::as_array).map(Vec::as_slice).unwrap_or(&[]);
            let c = model::classify(&ev.steps[i], watch, self.ticks.contains(&ev.steps[i].n.id));
            s["in_route"] = json!(route_ids.contains(&ev.steps[i].n.id));
            s["classification"] = json!({
                "state": c.state, "reason": c.reason, "source": c.source,
            });
        }
        // The current objective is the one the save has active; when the quest is not started, the
        // game's first objective is the next-best thing. The source of each is the same index.
        let mut objs = serde_json::Map::new();
        for s in &ev.steps {
            if s.manual {
                continue;
            }
            let mut v = self.current_objectives(&s.n.id, &s.n.files);
            if v.is_empty() {
                if let Some(list) = self.derived.get("steps").and_then(|m| m.get(&s.n.id)).and_then(|d| d.get("objectives")) {
                    v.extend(list.as_array().into_iter().flatten().filter_map(|o| o.get("text")).filter_map(|x| x.as_str().map(String::from)).take(2));
                }
            }
            v.truncate(4);
            objs.insert(s.n.id.clone(), json!(v));
        }
        let error = if !self.db_error.is_empty() { self.db_error.clone() } else { self.error.clone() };
        let card_report = self.cards_report();
        let top = self.top_section(&ev, &steps, &card_report);
        let completion = self.completion(&ev, &steps, &card_report);
        let target = targets::target_json(&self.endings, &self.selected, &target_evals, self.guidance_on);
        // Tradeoffs are spoilers: they name endings the player did not select. Keep the whole list
        // out of the spoiler-free payload, and with a target selected show only the edges touching
        // that goal. The raw ids stay for the detail payload; labels are added for the card.
        let tradeoffs = if self.selected.is_empty() {
            json!([])
        } else {
            let selected_outcomes: HashSet<String> = self
                .selected
                .iter()
                .filter_map(|tid| outcomes::target_outcome(&self.endings, tid))
                .collect();
            let hit = |value: &str| {
                let value = value
                    .strip_prefix("target:")
                    .or_else(|| value.strip_prefix("outcome:"))
                    .unwrap_or(value);
                self.selected.iter().any(|tid| tid == value) || selected_outcomes.contains(value)
            };
            let rows: Vec<Value> = self
                .exclusive
                .get("edges")
                .and_then(|x| x.as_array())
                .into_iter()
                .flatten()
                .filter(|e| {
                    hit(e.get("a").and_then(|x| x.as_str()).unwrap_or(""))
                        || hit(e.get("b").and_then(|x| x.as_str()).unwrap_or(""))
                })
                .map(|e| {
                    let mut e = e.clone();
                    if let Some(a) = e.get("a").and_then(|x| x.as_str()) {
                        let label = edge_label(&self.endings, &self.outcomes, a);
                        e["a_label"] = json!(label);
                    }
                    if let Some(b) = e.get("b").and_then(|x| x.as_str()) {
                        let label = edge_label(&self.endings, &self.outcomes, b);
                        e["b_label"] = json!(label);
                    }
                    e
                })
                .collect();
            json!(rows)
        };
        // A measured zero is not a clean bill. Say which pack has no Gwent card model at all, so
        // the COVERAGE row cannot read as six real zeroes.
        let mut coverage_packs = self.coverage.get("packs").cloned().unwrap_or_else(|| json!({}));
        if let Some(packs) = coverage_packs.as_object_mut() {
            for (name, p) in packs.iter_mut() {
                if p.get("with_cards").and_then(|x| x.as_i64()).unwrap_or(0) == 0 {
                    p["not_modelled"] = json!(true);
                    p["note"] = json!(if name == "gwent" {
                        "Gwent is a route section, not a Gwent card pack; no cards are measured for it."
                    } else {
                        "No Gwent card pack is measured for this pack; Hearts of Stone has none."
                    });
                }
            }
        }
        let setup = json!({
            "needed": !self.setup_v1 && self.selected.is_empty(),
            "has_targets": !targets::all_ids(&self.endings).is_empty(),
        });
        json!({
            "save": {"name": name, "age_secs": age, "error": error},
            "level": self.level,
            "game_dir": self.game_dir.as_ref().map(|p| p.display().to_string()).unwrap_or_default(),
            "folders": {
                "game": {"path": self.game_dir.as_ref().map(|p| p.display().to_string()).unwrap_or_default(), "ok": self.game_dir.is_some() && self.db_error.is_empty(), "auto": self.game_override.is_none()},
                "saves": {"path": self.saves_dir().map(|p| p.display().to_string()).unwrap_or_default(), "ok": self.saves_dir().and_then(|d| newest_in(&d)).is_some(), "auto": self.saves_override.is_none()},
                "message": self.folder_msg,
            },
            "sections": rt.sections,
            "steps": steps,
            "todo": self.todo_order(&ev, &steps, next_plan.as_deref()).iter().map(|&i| ev.steps[i].n.id.clone()).collect::<Vec<_>>(),
            "tracked": self.tracked_json(&ev),
            "top": top,
            "objectives": Value::Object(objs),
            "flags": self.route.flags.iter().map(|f| json!({"id": f.id, "label": f.label, "note": f.note, "value": self.flags.get(&f.id).cloned().unwrap_or_default()})).collect::<Vec<_>>(),
            "target": target,
            "setup": setup,
            "completion": completion,
            "coverage": {"packs": coverage_packs},
            "tradeoffs": tradeoffs,
        })
    }

    /// The NOW band, built once. `--dump` and the window must not disagree about it.
    fn top_section(&self, ev: &Eval, steps: &[Value], card_report: &Value) -> Value {
        let mut top = top_items(ev, steps);
        let Some(list) = top.as_array_mut() else { return top };
        list.extend(cards::top_items(card_report));
        let covered: HashSet<String> = list
            .iter()
            .flat_map(|i| i.get("ids").and_then(|x| x.as_array()).into_iter().flatten())
            .filter_map(|x| x.as_str().map(String::from))
            .collect();
        list.extend(choice_items(ev, &covered));
        sort_top(list);
        top
    }

    fn save_progress(&self) {
        let p = self.app_dir.join("progress.json");
        let mut ticks: Vec<&String> = self.ticks.iter().collect();
        ticks.sort();
        let cur = json!({"ticks": ticks, "level": self.level, "flags": self.flags, "cards": self.card_manual});
        let _ = std::fs::write(&p, serde_json::to_string(&cur).unwrap_or_default()); // only ever written in the tracker's own app folder
    }
}

/// The fourth warning: a choice that matters to the endings in play. It names the quest and
/// nothing about the choice; only a quest the journal already has open is in play.
fn choice_items(ev: &Eval, covered: &HashSet<String>) -> Vec<Value> {
    let mut out = Vec::new();
    for s in &ev.steps {
        if s.status != "Active" || !s.n.ending_relevant || covered.contains(&s.n.id) {
            continue;
        }
        let title = model::short(&s.n.title);
        out.push(json!({
            "kind": "choice", "level": "warn", "tag": "ENDING CHOICE AHEAD",
            "headline": format!("{title} contains a choice that matters to the endings in play."),
            "detail": "A scene section of this quest sets a fact a reviewed ending target needs.",
            "action": Value::Null, "live_note": Value::Null, "mechanism": "scene choice rows",
            "file": "", "quests": [title], "ids": [s.n.id],
        }));
    }
    out
}

/// Guidance off removes the exact lines and nothing else: the plan, its steps and its goal chips
/// are still the answer to "what is coming". The gate lives in the payload so no UI can leak a line.
fn gate_instructions(plan: &mut Value, guidance_on: bool) {
    if guidance_on {
        return;
    }
    if let Some(steps) = plan.get_mut("steps").and_then(|x| x.as_array_mut()) {
        for s in steps {
            s["instructions"] = json!([]);
        }
    }
}

fn top_items(ev: &Eval, steps: &[Value]) -> Value {
    let mut out: Vec<Value> = Vec::new();
    let mut seen: HashSet<String> = HashSet::new();
    let mut covered: HashSet<usize> = HashSet::new();
    for v in steps {
        let Some(list) = v.get("watch").and_then(|x| x.as_array()) else { continue };
        for w in list {
            let Some(id) = w.get("id").and_then(|x| x.as_str()) else { continue };
            let Some(live) = w.get("live").and_then(|x| x.as_str()) else { continue };
            let (kind, level, tag) = match live {
                "lost" => ("lost", "lost", "LOST IN THIS SAVE"),
                // the cutoff fired but the journal still has the quest open: say what the save says
                "passed" | "check" => ("risk", "stop", "CUTOFF PASSED - CHECK NOW"),
                "inside" => ("risk", "stop", "DO THIS NOW"),
                "ahead" => ("missable", "warn", "MISSABLE"),
                _ => continue,
            };
            let affected: Vec<String> = w.get("affected").and_then(|x| x.as_array()).into_iter().flatten()
                .filter_map(|x| x.as_str().map(String::from)).collect();
            // A quest the save has started is actionable even before its cutoff fires; that is the
            // MISSABLE case. A quest the journal never started is only shown when you are already
            // inside the closer, because then the next step can still save it. A wall of late-game
            // cutoffs in the prologue would be the noise 0.2 exists to remove.
            let hits: Vec<usize> = ev.steps.iter().enumerate()
                .filter(|(_, s)| {
                    let reachable = match live {
                        "inside" => matches!(s.journal.as_str(), "Active" | "Not started" | "Failed"),
                        "ahead" => matches!(s.journal.as_str(), "Active" | "Failed"),
                        _ => matches!(s.journal.as_str(), "Active" | "Failed"),
                    };
                    affected.iter().any(|a| model::tracks(&s.n, a)) && (reachable || s.tick_disagrees)
                })
                .map(|(i, _)| i).collect();
            if hits.is_empty() || !seen.insert(id.to_string()) {
                continue;
            }
            covered.extend(hits.iter().copied());
            let mut quests: Vec<String> = w.get("affected_titles").and_then(|x| x.as_array()).into_iter().flatten()
                .filter_map(|x| x.as_str().map(String::from)).collect();
            for t in w.get("closed_by_titles").and_then(|x| x.as_array()).into_iter().flatten().filter_map(|x| x.as_str()) {
                if !quests.iter().any(|q| q == t) {
                    quests.push(t.to_string());
                }
            }
            let file = w.get("files").and_then(|x| x.as_array()).and_then(|x| x.first()).and_then(|x| x.as_str()).unwrap_or("");
            out.push(json!({
                "kind": kind, "level": level, "tag": tag,
                "headline": w.get("headline").cloned().unwrap_or(Value::Null),
                "detail": w.get("why").cloned().unwrap_or(Value::Null),
                "action": if live == "lost" { Value::Null } else { w.get("action").cloned().unwrap_or(Value::Null) },
                "live_note": w.get("live_note").cloned().unwrap_or(Value::Null),
                "mechanism": match w.get("mechanism").and_then(|x| x.as_str()) {
                    Some("spawnset") => "CDeactivateSpawnset",
                    Some("journal_failure") => "journal Failure block",
                    other => other.unwrap_or("game files"),
                },
                "file": file,
                "quests": quests,
                "ids": hits.iter().map(|&i| ev.steps[i].n.id.clone()).collect::<Vec<_>>(),
            }));
        }
    }
    for (i, s) in ev.steps.iter().enumerate() {
        if s.status == "Failed" && !s.n.opt && !covered.contains(&i) {
            out.push(json!({
                "kind": "failed", "level": "lost", "tag": "FAILED IN YOUR QUEST LOG",
                "headline": format!("{} failed in your journal.", model::short(&s.n.title)),
                "detail": Value::Null, "action": Value::Null, "live_note": Value::Null,
                "mechanism": "save", "file": "your save's quest log", "quests": [s.n.title], "ids": [s.n.id],
            }));
        }
    }
    sort_top(&mut out);
    Value::Array(out)
}

/// One ordering for the whole band, whichever producer added the item.
fn sort_top(list: &mut [Value]) {
    let rank = |kind: &str| match kind {
        "risk" => 0u8,
        "lost" => 1,
        "failed" => 2,
        "choice" => 3,
        "card" => 4,
        _ => 5,
    };
    list.sort_by_cached_key(|item| {
        let kind = item.get("kind").and_then(|x| x.as_str()).unwrap_or("");
        (
            rank(kind),
            item.get("headline").and_then(|x| x.as_str()).unwrap_or("").to_string(),
        )
    });
}

/// A tradeoff edge names either a target id or an outcome id; the card should show the game's own
/// reviewed label, never the internal id.
fn edge_label(endings: &Value, outcomes_doc: &Value, value: &str) -> String {
    let value = value
        .strip_prefix("target:")
        .or_else(|| value.strip_prefix("outcome:"))
        .unwrap_or(value);
    if let Some(label) = endings
        .get("targets")
        .and_then(|x| x.get(value))
        .and_then(|x| x.get("label"))
        .and_then(|x| x.as_str())
    {
        return label.to_string();
    }
    outcomes::label(outcomes_doc, value)
}

#[tauri::command]
fn get_view(st: State<Shared>) -> Value {
    st.0.lock().unwrap().view()
}

#[tauri::command]
fn get_detail(id: String, st: State<Shared>) -> Value {
    let g = st.0.lock().unwrap();
    detail_json(&g, &id)
}

// Shared by the command and the headless `--detail` check so the two can never drift.
fn detail_json(g: &Inner, id: &str) -> Value {
    let rt = g.effective_route();
    let ev = model::evaluate(&rt, &g.state, &g.ticks, &g.flags, &g.facts);
    let Some(&i) = ev.byid.get(id) else { return Value::Null };
    let target_evals = g.target_evals(&ev);
    let branches = targets::branches_for_step(&g.branches, &g.ending_branch_ids, &id);
    let guidance = targets::guidance_for_step(&g.endings, &g.selected, &target_evals, g.guidance_on, &id);
    let n = &ev.steps[i].n;
    let tracking = if n.files.is_empty() {
        "Not readable from the save: tick it yourself.".to_string()
    } else {
        let names: Vec<&str> = n.files.iter().take(4).map(|f| f.rsplit('#').next().unwrap_or(f)).collect();
        format!("Read automatically from your save ({}).", names.join(", "))
    };
    // The graph is the evidence behind the route: the game's own start block and the reviewed
    // loss edge. The card never shows this; the detail pane does.
    let starts = n.files.iter().find_map(|f| {
        let stem = f.split('|').next().unwrap_or(f).split('#').next().unwrap_or(f);
        g.graph.get("starts").and_then(|s| s.get(stem)).cloned()
    }).unwrap_or(json!([]));
    let requires: Vec<Value> = n.hard.iter().map(|h| json!({
        "step": h, "facts": n.hard_facts.get(h).cloned().unwrap_or_default(),
    })).collect();
    let lost: Vec<Value> = g.graph.get("lost_when").and_then(|x| x.as_array()).into_iter().flatten()
        .filter(|l| l.get("affected").and_then(|a| a.as_array()).map(|a| a.iter().any(|x| x.as_str() == Some(n.id.as_str()))).unwrap_or(false))
        .cloned().collect();
    // The objectives the save itself marks active, worded by the game; the journal's full list is
    // the fallback for a quest that has not started (or a save with no active objective for it).
    let mut current = g.current_objectives(&n.id, &n.files);
    current.truncate(4);
    json!({
        "step": model::step_json(&rt, &ev, i),
        "current_objectives": current,
        "derived": g.derived.get("steps").and_then(|s| s.get(id)).cloned().unwrap_or(Value::Null),
        "derived_source": g.derived.get("note").cloned().unwrap_or(Value::Null),
        "graph": {"starts": starts, "requires": requires, "lost_when": lost},
        "branches": branches,
        "guidance": guidance,
        "tracking": tracking,
        "overridden": g.ticks.contains(&n.id) && !ev.steps[i].manual,
        "verdict": n.files.first().map(|f| {
            let sh = f.split('|').next().unwrap_or(f).split('#').next().unwrap_or(f).to_string();
            g.verdict_for(&rt, &ev, &sh)
        }).unwrap_or(Value::Null),
    })
}

#[tauri::command]
fn get_targets(st: State<Shared>) -> Value {
    let g = st.0.lock().unwrap();
    let ev = g.eval();
    let evals = g.target_evals(&ev);
    json!({
        "targets": targets::target_options(&g.endings, &evals),
        "presets": targets::preset_options(&g.endings),
    })
}

#[tauri::command]
fn get_outcomes(st: State<Shared>) -> Value {
    st.0.lock().unwrap().outcome_report()
}

#[tauri::command]
fn get_plan(targets: Option<Vec<String>>, st: State<Shared>) -> Value {
    st.0.lock().unwrap().plan_report(targets)
}

#[tauri::command]
fn set_target(ids: Vec<String>, app: tauri::AppHandle, st: State<Shared>) -> Result<Value, String> {
    let v = {
        let mut g = st.0.lock().unwrap();
        g.set_target(ids)?;
        g.view()
    };
    let _ = app.emit("view", v.clone());
    Ok(v)
}

#[tauri::command]
fn set_guidance(on: bool, app: tauri::AppHandle, st: State<Shared>) -> Value {
    let v = {
        let mut g = st.0.lock().unwrap();
        g.set_guidance(on);
        g.view()
    };
    let _ = app.emit("view", v.clone());
    v
}

#[tauri::command]
fn get_cards(st: State<Shared>) -> Value {
    st.0.lock().unwrap().cards_report()
}

#[tauri::command]
fn set_card(id: String, owned: bool, app: tauri::AppHandle, st: State<Shared>) -> Result<Value, String> {
    let (report, view) = {
        let mut g = st.0.lock().unwrap();
        g.set_card(id, owned)?;
        (g.cards_report(), g.view())
    };
    let _ = app.emit("view", view);
    Ok(report)
}

#[tauri::command]
fn search(q: String, st: State<Shared>) -> Value {
    let g = st.0.lock().unwrap();
    let q = q.trim().to_lowercase();
    if q.chars().count() < 2 {
        return json!([]);
    }
    let skip = ["lw", "poi", "e3", "test", "temp", "demo", "biddebug"];
    let ev = g.eval();
    let hits: Vec<Value> = g
        .display
        .iter()
        .filter(|(k, d)| (k.to_lowercase().contains(&q) || d.to_lowercase().contains(&q)) && !skip.iter().any(|s| k.starts_with(s)))
        .take(7)
        .map(|(k, d)| json!({"short": k, "display": d, "status": g.state.get(k).cloned().unwrap_or_else(|| "Not started".into()), "step": model::step_for_short(&ev, k).map(|i| ev.steps[i].n.id.clone())}))
        .collect();
    Value::Array(hits)
}

#[tauri::command]
fn check_quest(short: String, st: State<Shared>) -> Value {
    let g = st.0.lock().unwrap();
    let rt = g.effective_route();
    let ev = model::evaluate(&rt, &g.state, &g.ticks, &g.flags, &g.facts);
    g.verdict_for(&rt, &ev, &short)
}

#[tauri::command]
fn toggle_tick(id: String, app: tauri::AppHandle, st: State<Shared>) -> Value {
    let v = {
        let mut g = st.0.lock().unwrap();
        if !g.ticks.remove(&id) {
            g.ticks.insert(id);
        }
        g.save_progress();
        g.view()
    };
    let _ = app.emit("view", v.clone());
    v
}

#[tauri::command]
fn set_level(level: i64, app: tauri::AppHandle, st: State<Shared>) -> Value {
    let v = {
        let mut g = st.0.lock().unwrap();
        g.level = level.clamp(0, 100);
        g.save_progress();
        g.view()
    };
    let _ = app.emit("view", v.clone());
    v
}

#[tauri::command]
fn set_flag(flag: String, value: String, app: tauri::AppHandle, st: State<Shared>) -> Value {
    let v = {
        let mut g = st.0.lock().unwrap();
        if g.route.flags.iter().any(|f| f.id == flag) && (value == "yes" || value == "no" || value.is_empty()) {
            if value.is_empty() {
                g.flags.remove(&flag);
            } else {
                g.flags.insert(flag, value);
            }
            g.save_progress();
        }
        g.view()
    };
    let _ = app.emit("view", v.clone());
    v
}

#[tauri::command]
fn set_folder(kind: String, path: String, app: tauri::AppHandle, st: State<Shared>) -> Value {
    let v = {
        let mut g = st.0.lock().unwrap();
        g.apply_folder(&kind, &path);
        g.view()
    };
    let _ = app.emit("view", v.clone());
    v
}

/// native folder dialog (PowerShell + a topmost owner so it is not hidden behind the always-on-top window)
fn run_picker(description: &str, initial: &str) -> Option<String> {
    let esc = |t: &str| t.replace('\'', "''");
    let script = format!(
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; \
         $f=New-Object System.Windows.Forms.Form; $f.TopMost=$true; $f.ShowInTaskbar=$false; $f.StartPosition='Manual'; \
         $f.Location=New-Object System.Drawing.Point(-3000,-3000); $f.Size=New-Object System.Drawing.Size(1,1); $f.Show(); \
         $d=New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description='{}'; $d.SelectedPath='{}'; $d.ShowNewFolderButton=$false; \
         if($d.ShowDialog($f) -eq 'OK'){{[Console]::Out.Write($d.SelectedPath)}}; $f.Close()",
        esc(description),
        esc(initial)
    );
    let mut cmd = std::process::Command::new("powershell");
    cmd.args(["-NoProfile", "-STA", "-NonInteractive", "-Command", &script]);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000);
    }
    let out = cmd.output().ok()?;
    let t = String::from_utf8_lossy(&out.stdout).trim().to_string();
    if t.is_empty() { None } else { Some(t) }
}

#[tauri::command]
async fn pick_folder(kind: String, app: tauri::AppHandle) -> Result<Value, String> {
    let (desc, initial) = {
        let st = app.state::<Shared>();
        let g = st.0.lock().unwrap();
        if kind == "game" {
            ("Choose your Witcher 3 game folder (it contains the folders content and bin)", g.game_dir.as_ref().map(|p| p.display().to_string()).unwrap_or_default())
        } else {
            ("Choose your Witcher 3 saves folder (it contains the .sav files)", g.saves_dir().map(|p| p.display().to_string()).unwrap_or_default())
        }
    };
    let picked = tauri::async_runtime::spawn_blocking(move || run_picker(desc, &initial)).await.map_err(|e| e.to_string())?;
    let st = app.state::<Shared>();
    let v = {
        let mut g = st.0.lock().unwrap();
        if let Some(p) = picked {
            g.apply_folder(&kind, &p);
        }
        g.view()
    };
    let _ = app.emit("view", v.clone());
    Ok(v)
}

#[tauri::command]
fn set_pin(pin: bool, window: tauri::WebviewWindow) -> Result<(), String> {
    window.set_always_on_top(pin).map_err(|e| e.to_string())
}

#[tauri::command]
fn open_url(url: String) {
    if url.starts_with("https://") || url.starts_with("http://") {
        let _ = std::process::Command::new("rundll32").args(["url.dll,FileProtocolHandler", &url]).spawn();
    }
}

fn main() {
    // `--build-index out.json` writes the quest index built from the game files and exits (used to verify the build)
    let a0: Vec<String> = std::env::args().collect();
    if let Some(i) = a0.iter().position(|a| a == "--build-index") {
        let res = bundles::find_game_dir(None).ok_or_else(|| "game not found".to_string()).and_then(|g| bundles::build_quest_db(&g));
        let out = a0.get(i + 1).cloned().unwrap_or_else(|| "index.json".into());
        let _ = std::fs::write(out, match res { Ok(v) => serde_json::to_string(&v).unwrap_or_default(), Err(e) => format!("{{\"error\": \"{e}\"}}") });
        return;
    }
    let data_dir = find_data_dir();
    let mut inner = match Inner::load(data_dir) {
        Ok(i) => i,
        Err(e) => {
            eprintln!("cannot load tracker data: {e}");
            std::process::exit(1);
        }
    };
    inner.refresh_save();
    // `--names out.txt` writes every name the newest save holds (quests, facts, flags) and exits (used to find signals)
    if let Some(i) = a0.iter().position(|a| a == "--names") {
        let out = a0.get(i + 1).cloned().unwrap_or_else(|| "names.txt".into());
        let names = inner.save_path.as_ref().and_then(|p| save::load_raw(p).ok()).and_then(|raw| save::name_table(&raw).ok()).unwrap_or_default();
        let _ = std::fs::write(out, names.join("\n"));
        return;
    }
    // `--facts out.txt [needle]` writes the save's FactsDB (name -> values), optionally filtered, and exits
    // (ground truth for what one quest sets and another checks, independent of journal status)
    if let Some(i) = a0.iter().position(|a| a == "--facts") {
        let out = a0.get(i + 1).cloned().unwrap_or_else(|| "facts.txt".into());
        let needle = a0.get(i + 2).cloned().unwrap_or_default();
        let facts = inner.save_path.as_ref().and_then(|p| save::load_raw(p).ok()).and_then(|raw| save::facts(&raw).ok()).unwrap_or_default();
        let mut lines: Vec<String> = facts.iter().filter(|(k, _)| k.contains(&needle)).map(|(k, v)| format!("{k} = {v:?}")).collect();
        lines.sort();
        let _ = std::fs::write(out, lines.join("\n"));
        return;
    }
    // `--dump out.json` writes the computed state and exits (used to verify the build)
    let args: Vec<String> = std::env::args().collect();
    // `--view out.json` writes exactly what the window is handed, so the rendered text can be checked
    if let Some(i) = args.iter().position(|a| a == "--view") {
        let out = args.get(i + 1).cloned().unwrap_or_else(|| "view.json".into());
        let _ = std::fs::write(out, serde_json::to_string_pretty(&inner.view()).unwrap_or_default());
        return;
    }
    // `--detail <step id> <out.json>` writes one mission's detail pane, including guidance
    if let Some(i) = args.iter().position(|a| a == "--detail") {
        let id = args.get(i + 1).cloned().unwrap_or_default();
        let out = args.get(i + 2).cloned().unwrap_or_else(|| "detail.json".into());
        let _ = std::fs::write(out, serde_json::to_string_pretty(&detail_json(&inner, &id)).unwrap_or_default());
        return;
    }
    // `--cards out.json` and `--targets out.json` expose the two reports the screen builds from,
    // so a packaged build can be checked without opening a window.
    if let Some(i) = args.iter().position(|a| a == "--cards") {
        let out = args.get(i + 1).cloned().unwrap_or_else(|| "cards.json".into());
        let _ = std::fs::write(out, serde_json::to_string_pretty(&inner.cards_report()).unwrap_or_default());
        return;
    }
    if let Some(i) = args.iter().position(|a| a == "--targets") {
        let out = args.get(i + 1).cloned().unwrap_or_else(|| "targets.json".into());
        let ev = inner.eval();
        let evals = inner.target_evals(&ev);
        let doc = json!({
            "targets": targets::target_options(&inner.endings, &evals),
            "presets": targets::preset_options(&inner.endings),
        });
        let _ = std::fs::write(out, serde_json::to_string_pretty(&doc).unwrap_or_default());
        return;
    }
    // `--outcomes out.json` and `--plan out.json [id,id]` are the headless forms of the two
    // spoiler-gated commands. The plan accepts an explicit target list so a packaged build can be
    // checked without editing the user's settings.
    if let Some(i) = args.iter().position(|a| a == "--outcomes") {
        let out = args.get(i + 1).cloned().unwrap_or_else(|| "outcomes-report.json".into());
        let _ = std::fs::write(out, serde_json::to_string_pretty(&inner.outcome_report()).unwrap_or_default());
        return;
    }
    if let Some(i) = args.iter().position(|a| a == "--plan") {
        let out = args.get(i + 1).cloned().unwrap_or_else(|| "plan.json".into());
        let ids: Option<Vec<String>> = args
            .get(i + 2)
            .filter(|a| !a.starts_with("--"))
            .map(|s| s.split(',').filter(|x| !x.trim().is_empty()).map(|x| x.trim().to_string()).collect());
        let _ = std::fs::write(out, serde_json::to_string_pretty(&inner.plan_report(ids)).unwrap_or_default());
        return;
    }
    if let Some(i) = args.iter().position(|a| a == "--dump") {
        let rt = inner.effective_route();
        let ev = model::evaluate(&rt, &inner.state, &inner.ticks, &inner.flags, &inner.facts);
        let status: serde_json::Map<String, Value> = ev.steps.iter().map(|s| (s.n.id.clone(), json!(s.status))).collect();
        let done_q = inner.done_quests(&ev);
        let mut steps: Vec<Value> = (0..ev.steps.len()).map(|i| model::step_json(&rt, &ev, i)).collect();
        for (i, s) in steps.iter_mut().enumerate() {
            inner.attach_derived(s, &ev.steps[i], &done_q);
        }
        let card_report = inner.cards_report();
        let top = inner.top_section(&ev, &steps, &card_report);
        let dump = json!({
            "save": inner.save_path.as_ref().and_then(|p| p.file_name()).and_then(|n| n.to_str()).unwrap_or(""),
            "game_dir": inner.game_dir.as_ref().map(|p| p.display().to_string()),
            "quest_files": inner.db.quests.len(),
            "states": inner.state,
            "status": status,
            "todo": inner.todo_order(&ev, &steps, None).iter().map(|&i| ev.steps[i].n.id.clone()).collect::<Vec<_>>(),
            "tracked": inner.tracked_json(&ev),
            "objectives": inner.objectives,
            // the route's fact-gated prerequisites, and whether this save has the game's own condition
            // set, so the settlement can be checked against what the app actually did
            "gates": inner.gates(&ev),
            // the top section, exactly as the window is handed it (empty is a valid, tested answer)
            "top": top,
            // what the app actually shows for each step, so the data files can be checked against it
            "watch": steps.iter().map(|s| {
                let items = s.get("watch").and_then(|x| x.as_array()).cloned().unwrap_or_default();
                json!({
                    "id": s.get("id"), "title": s.get("title"), "status": s.get("status"),
                    "watch": items.len(),
                    "headline": items.first().and_then(|x| x.get("headline")).cloned().unwrap_or(Value::Null),
                    "live": items.first().and_then(|x| x.get("live")).cloned().unwrap_or(Value::Null),
                    "tag": items.first().and_then(|x| x.get("tag")).cloned().unwrap_or(Value::Null),
                    "live_note": items.first().and_then(|x| x.get("live_note")).cloned().unwrap_or(Value::Null),
                    "game_title": s.get("game_title").cloned().unwrap_or(Value::Null),
                })
            }).collect::<Vec<_>>(),
            "derived_note": inner.derived.get("note").cloned().unwrap_or(Value::Null),
            "error": if inner.db_error.is_empty() { inner.error.clone() } else { inner.db_error.clone() },
        });
        let out = args.get(i + 1).cloned().unwrap_or_else(|| "dump.json".into());
        let _ = std::fs::write(out, serde_json::to_string_pretty(&dump).unwrap_or_default());
        return;
    }
    tauri::Builder::default()
        .manage(Shared(Mutex::new(inner)))
        .setup(|app| {
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let mut last_emit = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
                loop {
                    std::thread::sleep(Duration::from_millis(2000));
                    let shared = handle.state::<Shared>();
                    let view = {
                        let mut g = shared.0.lock().unwrap();
                        if g.refresh_save() { Some(g.view()) } else { None }
                    };
                    let now = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
                    if let Some(v) = view {
                        let _ = handle.emit("view", v);
                        last_emit = now;
                    } else if now.saturating_sub(last_emit) >= 20 {
                        // keep the "saved Xm ago" text fresh
                        let v = shared.0.lock().unwrap().view();
                        let _ = handle.emit("view", v);
                        last_emit = now;
                    }
                }
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_view, get_detail, get_targets, get_outcomes, get_plan, set_target, set_guidance, get_cards, set_card,
            search, check_quest, toggle_tick, set_level, set_flag, set_folder, pick_folder, set_pin, open_url
        ])
        .run(tauri::generate_context!())
        .expect("error while running the tracker");
}
#[cfg(test)]
mod top_tests {
    use super::*;
    use model::{Node, RouteData};

    fn node(id: &str, files: &[&str]) -> Node {
        Node {
            section: "Main".into(), id: id.into(), title: id.into(), lv: String::new(),
            files: files.iter().map(|f| f.to_string()).collect(), hard: vec![],
            hard_facts: HashMap::new(), by: vec![], note: String::new(), kind: "side".into(),
            opt: false, when: vec![], order: 0, desc: String::new(), branch: false,
            dialogue_choice: false, ending_relevant: false, start_known: true,
            provenance: "game_file".into(), review_reason: String::new(),
            review_source: String::new(), reviewed: String::new(),
        }
    }

    fn eval(id: &str, status: &str) -> Eval {
        let rd = RouteData { sections: vec!["Main".into()], nodes: vec![node(id, &[id])], events: vec![],
                             prefs: vec![], conditional: HashSet::new(), flags: vec![], manual_audit: Value::Null };
        let st = HashMap::from([(id.to_string(), status.to_string())]);
        model::evaluate(&rd, &st, &HashSet::new(), &HashMap::new(), &HashSet::new())
    }

    fn step(id: &str, watch: Value) -> Value {
        json!({"id": id, "watch": watch})
    }

    fn watch(live: &str, affected: &str) -> Value {
        json!([{
            "id": "edge", "live": live, "level": "stop",
            "affected": [affected], "affected_titles": ["The Quest"],
            "closed_by": ["closer"], "closed_by_titles": ["The Closer"],
            "headline": "A sentence about the loss.", "why": "the file mechanism",
            "action": "Finish The Quest", "files": ["quests\\x.w2phase switches off y.w2comm"],
            "mechanism": "spawnset", "live_note": "In this save: ..."
        }])
    }

    #[test]
    fn nothing_at_stake_renders_nothing() {
        let ev = eval("mq3012noblestatuette", "Active");
        let top = top_items(&ev, &[step("mq3012noblestatuette", json!([]))]);
        assert_eq!(top, json!([]), "an empty top section is the correct answer");
    }

    #[test]
    fn settled_and_unknown_never_reach_the_top() {
        let ev = eval("mq3012noblestatuette", "Active");
        for live in ["settled", "unknown", ""] {
            let top = top_items(&ev, &[step("mq3012noblestatuette", watch(live, "mq3012noblestatuette"))]);
            assert_eq!(top, json!([]), "{live} must not render");
        }
    }

    #[test]
    fn only_the_journal_can_declare_a_loss() {
        let ev = eval("mq3012noblestatuette", "Active");
        let lost = top_items(&ev, &[step("mq3012noblestatuette", watch("lost", "mq3012noblestatuette"))]);
        assert_eq!(lost[0]["kind"], "lost");
        assert!(lost[0]["tag"].as_str().unwrap().contains("LOST"));
        assert_eq!(lost[0]["mechanism"], "CDeactivateSpawnset");
        assert!(lost[0]["file"].as_str().unwrap().contains("w2phase"));
        // a cutoff that passed without a Failed journal entry is a check, not a loss
        let check = top_items(&ev, &[step("mq3012noblestatuette", watch("passed", "mq3012noblestatuette"))]);
        assert_eq!(check[0]["kind"], "risk");
        assert!(check[0]["tag"].as_str().unwrap().contains("CHECK NOW"));
        assert_eq!(check[0]["action"], "Finish The Quest");
        let risk = top_items(&ev, &[step("mq3012noblestatuette", watch("inside", "mq3012noblestatuette"))]);
        assert_eq!(risk[0]["kind"], "risk");
        assert!(risk[0]["tag"].as_str().unwrap().contains("DO THIS NOW"));
        assert_eq!(risk[0]["action"], "Finish The Quest");
        let miss = top_items(&ev, &[step("mq3012noblestatuette", watch("ahead", "mq3012noblestatuette"))]);
        assert_eq!(miss[0]["kind"], "missable");
        assert!(miss[0]["tag"].as_str().unwrap().contains("MISSABLE"));
    }

    #[test]
    fn an_unstarted_quest_inside_the_closer_is_urgent_but_a_distant_one_is_silent() {
        let ev = eval("mq3012noblestatuette", "Not started");
        let inside = top_items(&ev, &[step("mq3012noblestatuette", watch("inside", "mq3012noblestatuette"))]);
        assert_eq!(inside[0]["kind"], "risk", "the closer is in the log and this quest can still be saved");
        assert!(inside[0]["action"].as_str().unwrap().contains("Finish"));
        let ahead = top_items(&ev, &[step("mq3012noblestatuette", watch("ahead", "mq3012noblestatuette"))]);
        assert_eq!(ahead, json!([]), "a distant cutoff on an unstarted quest is not yet a decision");
        // the same unstarted quest is not reported as a loss: a fired cutoff did not catch it open
        let lost = top_items(&ev, &[step("mq3012noblestatuette", watch("passed", "mq3012noblestatuette"))]);
        assert_eq!(lost, json!([]));
    }

    #[test]
    fn a_failed_quest_is_its_own_entry() {
        let ev = eval("sq301triss", "Failed");
        let top = top_items(&ev, &[step("sq301triss", json!([]))]);
        assert_eq!(top[0]["kind"], "failed");
        assert!(top[0]["headline"].as_str().unwrap().contains("failed"));
    }

    #[test]
    fn guidance_off_gates_only_the_lines() {
        let mut plan = json!({"steps": [{"step": "a", "state": "ahead",
                                         "instructions": [{"instruction": "Say this."}]}]});
        gate_instructions(&mut plan, false);
        assert!(plan["steps"][0]["instructions"].as_array().unwrap().is_empty());
        assert_eq!(plan["steps"][0]["state"], "ahead", "the plan step survives");
        let mut on = json!({"steps": [{"instructions": [{"instruction": "Say this."}]}]});
        gate_instructions(&mut on, true);
        assert_eq!(on["steps"][0]["instructions"].as_array().unwrap().len(), 1);
    }

    #[test]
    fn a_live_choice_is_a_now_item_with_no_choice_text() {
        let mut n = node("endingstep", &["endingstep"]);
        n.ending_relevant = true;
        n.title = "The Choice Quest".into();
        let rd = RouteData { sections: vec!["Main".into()], nodes: vec![n], events: vec![],
                             prefs: vec![], conditional: HashSet::new(), flags: vec![], manual_audit: Value::Null };
        let st = HashMap::from([("endingstep".to_string(), "Active".to_string())]);
        let ev = model::evaluate(&rd, &st, &HashSet::new(), &HashMap::new(), &HashSet::new());
        let items = choice_items(&ev, &HashSet::new());
        assert_eq!(items.len(), 1, "an open quest with an ending branch is one NOW item");
        assert_eq!(items[0]["kind"], "choice");
        assert!(items[0]["headline"].as_str().unwrap().contains("The Choice Quest"));
        assert!(items[0].get("instruction").is_none(), "the band never carries choice text");
        // a choice on a quest the journal has not reached is ledger-only, not a warning
        let ev = model::evaluate(&rd, &HashMap::new(), &HashSet::new(), &HashMap::new(), &HashSet::new());
        assert!(choice_items(&ev, &HashSet::new()).is_empty());
    }

    #[test]
    fn the_app_has_no_network_client_and_never_writes_a_save() {
        let manifest = include_str!("../Cargo.toml").to_lowercase();
        for c in ["reqwest", "hyper", "ureq", "isahc", "attohttpc", "curl"] {
            assert!(!manifest.contains(c), "network crate {c} in Cargo.toml");
        }
        let src = concat!(env!("CARGO_MANIFEST_DIR"), "/src");
        // Build the needles at run time so this test's own source cannot match them.
        let needles = [
            format!("{}{}", "Tcp", "Stream"),
            format!("{}{}", "req", "west::"),
            format!("{}{}", "ur", "eq::"),
            format!("{}{}", "hy", "per::client"),
            format!("{}{}", "std::", "net"),
        ];
        for e in std::fs::read_dir(src).unwrap() {
            let p = e.unwrap().path();
            if p.extension().map(|x| x == "rs").unwrap_or(false) {
                let body = std::fs::read_to_string(&p).unwrap();
                for c in &needles {
                    assert!(!body.contains(c.as_str()), "{} contains {c}", p.display());
                }
            }
        }
        let save = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/src/save.rs")).unwrap();
        assert!(!save.contains("fs::write") && !save.contains("File::create"),
                "save.rs must stay read-only: no write and no create");
    }

    #[test]
    fn a_ticked_step_with_a_fired_cutoff_still_appears_at_the_top() {
        let id = "mq3012noblestatuette";
        let rd = RouteData {
            sections: vec!["Main".into()], nodes: vec![node(id, &[id])], events: vec![],
            prefs: vec![], conditional: HashSet::new(), flags: vec![], manual_audit: Value::Null,
        };
        let st = HashMap::from([(id.to_string(), "Active".to_string())]);
        let ticks = HashSet::from([id.to_string()]);
        let ev = model::evaluate(&rd, &st, &ticks, &HashMap::new(), &HashSet::new());
        assert!(ev.steps[0].tick_disagrees);
        let mut w = watch("check", id);
        w[0]["live_note"] = json!("In this save: done: Now or Never. You ticked The Nobleman Statuette done, but the journal still has it open - the journal wins here.");
        let top = top_items(&ev, &[step(id, w)]);
        assert_eq!(top[0]["kind"], "risk", "a tick must not hide the passed cutoff");
        assert!(top[0]["tag"].as_str().unwrap().contains("CHECK NOW"));
        assert!(top[0]["live_note"].as_str().unwrap().contains("You ticked"));
    }
}
