//! Finds the player's Witcher 3 install and builds the quest-journal index from THEIR game files (nothing from the game is shipped).
//! Reads bundle headers only; never writes to the game folder.

use regex::bytes::Regex;
use serde_json::{json, Map, Value};
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

pub fn is_game_dir(p: &Path) -> bool {
    p.join("content").join("content0").join("bundles").is_dir()
}

fn steam_libraries() -> Vec<PathBuf> {
    let mut roots: Vec<PathBuf> = Vec::new();
    // Steam install folder from the registry (read-only query, no console window)
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        if let Ok(out) = std::process::Command::new("reg").args(["query", "HKCU\\Software\\Valve\\Steam", "/v", "SteamPath"]).creation_flags(0x0800_0000).output() {
            let t = String::from_utf8_lossy(&out.stdout).to_string();
            if let Some(line) = t.lines().find(|l| l.contains("SteamPath")) {
                if let Some(idx) = line.find("REG_SZ") {
                    roots.push(PathBuf::from(line[idx + 6..].trim()));
                }
            }
        }
    }
    for p in ["C:\\Program Files (x86)\\Steam", "C:\\Program Files\\Steam"] {
        roots.push(PathBuf::from(p));
    }
    let mut libs = roots.clone();
    for r in &roots {
        if let Ok(t) = std::fs::read_to_string(r.join("steamapps").join("libraryfolders.vdf")) {
            for line in t.lines() {
                let l = line.trim();
                if l.starts_with("\"path\"") {
                    let parts: Vec<&str> = l.split('"').collect();
                    if parts.len() >= 4 {
                        libs.push(PathBuf::from(parts[3].replace("\\\\", "\\")));
                    }
                }
            }
        }
    }
    libs
}

/// Look for the game: explicit setting, next to the exe, Steam libraries, GOG and Epic default folders.
pub fn find_game_dir(configured: Option<&str>) -> Option<PathBuf> {
    let mut cands: Vec<PathBuf> = Vec::new();
    if let Some(c) = configured {
        cands.push(PathBuf::from(c));
    }
    if let Ok(e) = std::env::var("W3_GAME_DIR") {
        cands.push(PathBuf::from(e));
    }
    if let Ok(exe) = std::env::current_exe() {
        for anc in exe.ancestors().skip(1).take(6) {
            cands.push(anc.to_path_buf());
        }
    }
    for lib in steam_libraries() {
        for name in ["The Witcher 3", "The Witcher 3 Wild Hunt"] {
            cands.push(lib.join("steamapps").join("common").join(name));
        }
    }
    for p in [
        "C:\\GOG Games\\The Witcher 3 Wild Hunt GOTY",
        "C:\\Program Files (x86)\\GOG Galaxy\\Games\\The Witcher 3 Wild Hunt GOTY",
        "C:\\Program Files\\Epic Games\\TheWitcher3",
    ] {
        cands.push(PathBuf::from(p));
    }
    cands.into_iter().find(|p| is_game_dir(p))
}

/// Changes when the game is patched, so the cached index is rebuilt.
pub fn game_stamp(game: &Path) -> String {
    let exe = game.join("bin").join("x64_dx12").join("witcher3.exe");
    match std::fs::metadata(&exe) {
        Ok(m) => format!("{}:{}", m.len(), m.modified().ok().and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok()).map(|d| d.as_secs()).unwrap_or(0)),
        Err(_) => "unknown".into(),
    }
}

fn collect_bundles(dir: &Path, out: &mut Vec<PathBuf>, depth: usize) {
    if depth > 8 {
        return;
    }
    let Ok(rd) = std::fs::read_dir(dir) else { return };
    for e in rd.flatten() {
        let p = e.path();
        if p.is_dir() {
            collect_bundles(&p, out, depth + 1);
        } else if p.extension().map(|x| x == "bundle").unwrap_or(false) {
            out.push(p);
        }
    }
}

fn u32at(b: &[u8], o: usize) -> Option<u32> {
    b.get(o..o + 4).map(|s| u32::from_le_bytes([s[0], s[1], s[2], s[3]]))
}

fn latin1(b: &[u8]) -> String {
    b.iter().map(|&c| c as char).collect()
}

/// quest journal files -> [[entry name, guid], ...], read from the player's own game files.
pub fn build_quest_db(game: &Path) -> Result<Value, String> {
    let path_re = Regex::new(r"(?i-u)(?:[a-z0-9_ ]+\\)*journal\\quests\\[^\x00]+?\.journal").map_err(|e| e.to_string())?;
    let ident_re = Regex::new(r"(?-u)([^\x00]+?) ([0-9A-F]{8}-[0-9A-F]{8}-[0-9A-F]{8}-[0-9A-F]{8})\x00").map_err(|e| e.to_string())?;
    let mut bundles = Vec::new();
    collect_bundles(&game.join("content"), &mut bundles, 0);
    collect_bundles(&game.join("dlc"), &mut bundles, 0);
    bundles.sort();
    let mut db = Map::new();
    for b in &bundles {
        let Ok(mut f) = std::fs::File::open(b) else { continue };
        let mut head = [0u8; 32];
        if f.read_exact(&mut head).is_err() || &head[..8] != b"POTATO70" {
            continue;
        }
        let hs = u32at(&head, 16).unwrap_or(0) as usize;
        if hs == 0 || hs > 256 * 1024 * 1024 {
            continue;
        }
        let mut tbl = vec![0u8; hs];
        if f.read_exact(&mut tbl).is_err() {
            continue;
        }
        let fname = b.file_name().and_then(|n| n.to_str()).unwrap_or("").to_string();
        for m in path_re.find_iter(&tbl) {
            let st = m.start();
            let o = st + 0x100 + 16;
            let (Some(off), Some(size), Some(zsize), Some(comp)) = (u32at(&tbl, o), u32at(&tbl, o + 8), u32at(&tbl, o + 12), u32at(&tbl, o + 20)) else { continue };
            let n = if comp != 0 { zsize } else { size } as usize;
            if n == 0 || n > 64 * 1024 * 1024 || f.seek(SeekFrom::Start(off as u64)).is_err() {
                continue;
            }
            let mut raw = vec![0u8; n];
            if f.read_exact(&mut raw).is_err() {
                continue;
            }
            let data = if comp == 1 {
                let mut out = Vec::with_capacity(size as usize);
                if flate2::read::ZlibDecoder::new(&raw[..]).read_to_end(&mut out).is_err() {
                    continue;
                }
                out
            } else {
                raw
            };
            if data.len() < 4 || &data[..4] != b"CR2W" {
                continue;
            }
            let ids: Vec<Value> = ident_re.captures_iter(&data).map(|c| json!([latin1(&c[1]), latin1(&c[2])])).collect();
            let key = latin1(m.as_bytes()).to_lowercase();
            db.insert(key, json!({"file": fname, "ids": ids}));
        }
    }
    if db.is_empty() {
        return Err("no quest journals found in the game files".into());
    }
    Ok(Value::Object(db))
}
