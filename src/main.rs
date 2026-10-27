#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
//! Witcher 3 Missables Tracker (Tauri). Reads the newest save READ-ONLY, evaluates the route model, serves the UI.
//! Unofficial fan tool, not affiliated with CD PROJEKT RED.

mod bundles;
mod journalidx;
mod model;
mod save;

use model::{Eval, RouteData};
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
    data_dir: PathBuf,   // read-only research data shipped with the app
    app_dir: PathBuf,    // per-user folder: progress, settings, cached quest index
    route: RouteData,
    db: save::QuestDb,
    db_error: String,
    game_dir: Option<PathBuf>,
    display: Vec<(String, String)>,
    kb: HashMap<String, Value>,      // journal file -> audit quest
    guide: Value,                    // merged guide_*.json
    guide_alias: HashMap<String, String>,
    feed: Value,                     // data/feed.json: quest-order warnings with evidence labels
    // save state
    state: HashMap<String, String>,
    objectives: HashMap<String, Vec<String>>,
    tracked: Option<String>,         // guid of the quest tracked in the game (read from the save)
    tracked_file: Option<String>,    // journal file of that quest, as the save names it
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

/// quest index built from the player's own game files, cached in the app folder until the game is patched
fn load_quest_index(app_dir: &Path, game: &Path) -> Result<Value, String> {
    let cache = app_dir.join("quest_index.json");
    let stamp = bundles::game_stamp(game);
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

/// research titles the audit could not identify ('Unmapped journal file ...') are not names
fn is_placeholder(title: &str) -> bool {
    title.starts_with("Unmapped") || title.starts_with("Unknown")
}

impl Inner {
    fn load(data_dir: PathBuf) -> Result<Inner, String> {
        let app_dir = find_app_dir(&data_dir);
        let route = model::load_route(&read_json(&data_dir.join("route.json"))?)?;
        // research data
        let mut kb: HashMap<String, Value> = HashMap::new();
        let mut guide = serde_json::Map::new();
        let mut files: Vec<PathBuf> = std::fs::read_dir(&data_dir).map_err(|e| e.to_string())?.filter_map(|e| e.ok()).map(|e| e.path()).collect();
        files.sort();
        for p in &files {
            let name = p.file_name().and_then(|x| x.to_str()).unwrap_or("");
            if name.starts_with("audit_") && name.ends_with(".json") {
                if let Ok(v) = read_json(p) {
                    for q in v["quests"].as_array().into_iter().flatten() {
                        for jf in q["journal_files"].as_array().into_iter().flatten().filter_map(|x| x.as_str()) {
                            kb.entry(jf.to_string()).or_insert_with(|| q.clone());
                        }
                    }
                }
            } else if name.starts_with("guide_") && name.ends_with(".json") && name != "guide_alias.json" {
                if let Ok(Value::Object(m)) = read_json(p) {
                    for (k, v) in m {
                        guide.insert(k, v);
                    }
                }
            }
        }
        let guide_alias: HashMap<String, String> = read_json(&data_dir.join("guide_alias.json"))
            .ok()
            .and_then(|v| serde_json::from_value(v).ok())
            .unwrap_or_default();
        // progress lives in the per-user folder (an old copy next to the exe is migrated once)
        let prog = read_json(&app_dir.join("progress.json")).or_else(|_| read_json(&data_dir.join("progress.json"))).unwrap_or(json!({}));
        let ticks: HashSet<String> = prog["ticks"].as_array().into_iter().flatten().filter_map(|x| x.as_str().map(String::from)).collect();
        let level = prog["level"].as_i64().unwrap_or(0);
        let flags: HashMap<String, String> = prog["flags"].as_object().map(|m| m.iter().filter_map(|(k, v)| Some((k.clone(), v.as_str()?.to_string()))).collect()).unwrap_or_default();
        let settings = read_json(&app_dir.join("settings.json")).unwrap_or(json!({}));
        let feed = read_json(&data_dir.join("feed.json")).unwrap_or(json!({"items": []}));
        let mut inner = Inner {
            data_dir,
            app_dir,
            route,
            feed,
            db: save::QuestDb { quests: vec![], display: vec![] },
            db_error: String::new(),
            game_dir: None,
            display: vec![],
            kb,
            guide: Value::Object(guide),
            guide_alias,
            state: HashMap::new(),
            objectives: HashMap::new(),
            tracked: None,
            tracked_file: None,
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

    fn write_settings(&self) {
        let v = json!({"game_dir": self.game_override, "saves_dir": self.saves_override});
        let _ = std::fs::write(self.app_dir.join("settings.json"), serde_json::to_string(&v).unwrap_or_default());
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
                self.objectives = s.objectives;
                self.tracked = s.tracked;
                self.tracked_file = s.tracked_file;
                self.ok_mtime = Some(m);
                self.error.clear();
            }
            Err(e) => {
                // the game may still be writing the file: keep the old state and retry on the next poll
                self.error = format!("reading save... ({e})");
            }
        }
        true
    }

    /// the route plus a card for the quest tracked in the game, when no route step covers that quest
    fn effective_route(&self) -> RouteData {
        let mut rt = self.route.clone();
        let Some(short) = self.tracked_short() else { return rt };
        if rt.nodes.iter().any(|n| model::tracks(n, &short)) {
            return rt;
        }
        let kb = self.kb.get(&short).filter(|q| !q["title"].as_str().map(is_placeholder).unwrap_or(false));
        let game_name = self.display.iter().find(|(k, _)| *k == short).map(|(_, d)| d.clone()).unwrap_or_else(|| short.clone());
        let title = kb.and_then(|q| q["title"].as_str()).map(String::from).unwrap_or(game_name);
        let kind = kb.and_then(|q| q["kind"].as_str()).unwrap_or("side").to_string();
        let lv = kb.and_then(|q| q["level"].as_str()).filter(|l| l.chars().any(|c| c.is_ascii_digit())).unwrap_or("").to_string();
        if !rt.sections.iter().any(|s| s == "Tracked") {
            rt.sections.insert(0, "Tracked".into());
        }
        rt.nodes.push(model::Node {
            section: "Tracked".into(),
            id: format!("tracked_{short}"),
            title,
            lv,
            files: vec![short],
            conf: "high".into(),
            hard: vec![],
            by: vec![],
            note: "Tracked in your game. Not in the route, so it is listed from your save.".into(),
            kind,
            opt: false,
            when: vec![],
        });
        rt
    }

    fn eval(&self) -> Eval {
        model::evaluate(&self.effective_route(), &self.state, &self.ticks, &self.flags)
    }

    /// the journal quest file (short name) of the quest tracked in the game, if the tracker knows it
    fn tracked_short(&self) -> Option<String> {
        self.tracked_file.clone().or_else(|| self.tracked.as_deref().and_then(|g| save::quest_for_guid(&self.db, g)))
    }

    /// the route steps of the tracked quest that are still open (held-back and lost ones included, so they can be warned about)
    fn tracked_steps(&self, ev: &Eval, short: &str) -> Vec<usize> {
        (0..ev.steps.len()).filter(|&i| model::tracks(&ev.steps[i].n, short) && !matches!(ev.steps[i].status.as_str(), "Done" | "N/A")).collect()
    }

    /// DO NEXT order: the steps for the quest tracked in the game come first, wherever they are; the rest keep the route order
    fn todo_order(&self, ev: &Eval) -> Vec<usize> {
        let Some(short) = self.tracked_short() else { return ev.todo.clone() };
        let mine = self.tracked_steps(ev, &short);
        mine.iter().copied().chain(ev.todo.iter().copied().filter(|i| !mine.contains(i))).collect()
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

    fn start_text(&self, i: usize, ev: &Eval) -> String {
        let n = &ev.steps[i].n;
        if let Some(q) = self.kb_for(&n.files) {
            if let Some(s) = q["start"].as_str() {
                if !s.is_empty() {
                    return s.to_string();
                }
            }
        }
        self.guide_for(&n.id).and_then(|g| g["available_when"].as_str().map(String::from)).unwrap_or_default()
    }

    fn kb_for(&self, files: &[String]) -> Option<&Value> {
        for f in files {
            for x in f.split('|') {
                if let Some(q) = self.kb.get(x.split('#').next().unwrap_or(x)) {
                    return Some(q);
                }
            }
        }
        None
    }

    fn guide_for(&self, id: &str) -> Option<&Value> {
        self.guide.get(id).or_else(|| self.guide_alias.get(id).and_then(|a| self.guide.get(a)))
    }

    fn view(&self) -> Value {
        let rt = self.effective_route();
        let ev = model::evaluate(&rt, &self.state, &self.ticks, &self.flags);
        let age = self.save_mtime.and_then(|m| SystemTime::now().duration_since(m).ok()).map(|d| d.as_secs()).unwrap_or(0);
        let name = self.save_path.as_ref().and_then(|p| p.file_name()).and_then(|n| n.to_str()).unwrap_or("");
        let steps: Vec<Value> = (0..ev.steps.len()).map(|i| model::step_json(&rt, &ev, i, &self.start_text(i, &ev))).collect();
        let mut objs = serde_json::Map::new();
        for s in &ev.steps {
            if s.manual {
                continue;
            }
            let mut v: Vec<String> = Vec::new();
            for f in &s.n.files {
                if let Some(o) = self.objectives.get(f.split('#').next().unwrap_or(f)) {
                    v.extend(o.iter().cloned());
                }
            }
            v.truncate(4);
            objs.insert(s.n.id.clone(), json!(v));
        }
        let error = if !self.db_error.is_empty() { self.db_error.clone() } else { self.error.clone() };
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
            "todo": self.todo_order(&ev).iter().map(|&i| ev.steps[i].n.id.clone()).collect::<Vec<_>>(),
            "tracked": self.tracked_json(&ev),
            "holdoff": model::holdoff_json(&ev),
            "feed": self.feed.get("items").cloned().unwrap_or(json!([])),
            "alerts": model::alerts_json(&ev),
            "objectives": Value::Object(objs),
            "flags": self.route.flags.iter().map(|f| json!({"id": f.id, "label": f.label, "note": f.note, "value": self.flags.get(&f.id).cloned().unwrap_or_default()})).collect::<Vec<_>>(),
        })
    }

    fn save_progress(&self) {
        let p = self.app_dir.join("progress.json");
        let mut ticks: Vec<&String> = self.ticks.iter().collect();
        ticks.sort();
        let cur = json!({"ticks": ticks, "level": self.level, "flags": self.flags});
        let _ = std::fs::write(&p, serde_json::to_string(&cur).unwrap_or_default()); // only ever written in the tracker's own app folder
    }
}

fn short_title(t: &str) -> &str {
    model::short(t)
}

#[tauri::command]
fn get_view(st: State<Shared>) -> Value {
    st.0.lock().unwrap().view()
}

#[tauri::command]
fn get_detail(id: String, st: State<Shared>) -> Value {
    let g = st.0.lock().unwrap();
    let rt = g.effective_route();
    let ev = model::evaluate(&rt, &g.state, &g.ticks, &g.flags);
    let Some(&i) = ev.byid.get(&id) else { return Value::Null };
    let n = &ev.steps[i].n;
    let tracking = if n.files.is_empty() {
        "Not readable from the save: tick it yourself.".to_string()
    } else {
        let names: Vec<&str> = n.files.iter().take(4).map(|f| f.rsplit('#').next().unwrap_or(f)).collect();
        format!("Read automatically from your save ({}{}, match: {}).", names.join(", "), if n.files.len() > 4 { "..." } else { "" }, n.conf)
    };
    json!({
        "step": model::step_json(&rt, &ev, i, &g.start_text(i, &ev)),
        "kb": g.kb_for(&n.files).cloned().unwrap_or(Value::Null),
        "guide": g.guide_for(&n.id).cloned().unwrap_or(Value::Null),
        "tracking": tracking,
        "overridden": g.ticks.contains(&n.id) && !ev.steps[i].manual,
        "verdict": n.files.first().map(|f| {
            let sh = f.split('|').next().unwrap_or(f).split('#').next().unwrap_or(f).to_string();
            let v = model::check_quest(&rt, &ev, &sh, &g.state);
            model::verdict_json(&v, short_title(&n.title))
        }).unwrap_or(Value::Null),
    })
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
    let ev = model::evaluate(&rt, &g.state, &g.ticks, &g.flags);
    let v = model::check_quest(&rt, &ev, &short, &g.state);
    let display = g.display.iter().find(|(k, _)| *k == short).map(|(_, d)| d.clone()).unwrap_or_else(|| short.clone());
    model::verdict_json(&v, &display)
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
    if let Some(i) = args.iter().position(|a| a == "--dump") {
        let ev = inner.eval();
        let status: serde_json::Map<String, Value> = ev.steps.iter().map(|s| (s.n.id.clone(), json!(s.status))).collect();
        let dump = json!({
            "save": inner.save_path.as_ref().and_then(|p| p.file_name()).and_then(|n| n.to_str()).unwrap_or(""),
            "game_dir": inner.game_dir.as_ref().map(|p| p.display().to_string()),
            "quest_files": inner.db.quests.len(),
            "states": inner.state,
            "status": status,
            "todo": inner.todo_order(&ev).iter().map(|&i| ev.steps[i].n.id.clone()).collect::<Vec<_>>(),
            "tracked": inner.tracked_json(&ev),
            "objectives": inner.objectives,
            "alerts": ev.alerts.iter().map(|a| a.msg.clone()).collect::<Vec<_>>(),
            "dont_start": model::dont_start(&ev).iter().map(|h| h.name.clone()).collect::<Vec<_>>(),
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
        .invoke_handler(tauri::generate_handler![get_view, get_detail, search, check_quest, toggle_tick, set_level, set_flag, set_folder, pick_folder, set_pin, open_url])
        .run(tauri::generate_context!())
        .expect("error while running the tracker");
}
