//! Witcher 3 save reader. READ-ONLY: the save file is only ever opened for reading.
//! Port of the Python w3sav.py / w3journal.py (reverse-engineered format).

use serde_json::Value;
use std::collections::HashMap;
use std::path::Path;

fn u32le(b: &[u8], o: usize) -> Result<u32, String> {
    b.get(o..o + 4).map(|s| u32::from_le_bytes([s[0], s[1], s[2], s[3]])).ok_or_else(|| "save truncated".to_string())
}

fn u16le(b: &[u8], o: usize) -> Result<u16, String> {
    b.get(o..o + 2).map(|s| u16::from_le_bytes([s[0], s[1]])).ok_or_else(|| "save truncated".to_string())
}

/// Standard LZ4 block decoder (the save is chunks of LZ4 blocks).
fn lz4_block(src: &[u8], hint: usize) -> Result<Vec<u8>, String> {
    let mut out: Vec<u8> = Vec::with_capacity(hint);
    let mut i = 0usize;
    let n = src.len();
    while i < n {
        let t = src[i];
        i += 1;
        let mut ln = (t >> 4) as usize;
        if ln == 15 {
            loop {
                let b = *src.get(i).ok_or("lz4: truncated length")?;
                i += 1;
                ln += b as usize;
                if b != 255 {
                    break;
                }
            }
        }
        if i + ln > n {
            return Err("lz4: literal overruns block".into());
        }
        out.extend_from_slice(&src[i..i + ln]);
        i += ln;
        if i >= n {
            break;
        }
        if i + 2 > n {
            return Err("lz4: truncated offset".into());
        }
        let off = src[i] as usize | ((src[i + 1] as usize) << 8);
        i += 2;
        let mut ml = (t & 15) as usize;
        if ml == 15 {
            loop {
                let b = *src.get(i).ok_or("lz4: truncated match length")?;
                i += 1;
                ml += b as usize;
                if b != 255 {
                    break;
                }
            }
        }
        ml += 4;
        if off == 0 || off > out.len() {
            return Err("lz4: bad back-reference".into());
        }
        let start = out.len() - off;
        for k in 0..ml {
            let b = out[start + k];
            out.push(b);
        }
    }
    Ok(out)
}

/// Read a save and return the decompressed bytes.
pub fn load_raw(path: &Path) -> Result<Vec<u8>, String> {
    let d = std::fs::read(path).map_err(|e| format!("cannot read save: {e}"))?;
    if d.len() < 16 || &d[..8] != b"SNFHFZLC" {
        return Err("not a Witcher 3 save".into());
    }
    let n = u32le(&d, 8)? as usize;
    let mut pos = u32le(&d, 12)? as usize;
    let mut out: Vec<u8> = Vec::new();
    for k in 0..n {
        let comp = u32le(&d, 16 + 12 * k)? as usize;
        let unc = u32le(&d, 16 + 12 * k + 4)? as usize;
        let chunk = d.get(pos..pos + comp).ok_or("save truncated (chunk)")?;
        out.extend(lz4_block(chunk, unc)?);
        pos += comp;
    }
    Ok(out)
}

fn find(hay: &[u8], needle: &[u8], from: usize) -> Option<usize> {
    if needle.is_empty() || hay.len() < needle.len() || from > hay.len() - needle.len() {
        return None;
    }
    let first = needle[0];
    let mut i = from;
    let last = hay.len() - needle.len();
    while i <= last {
        if hay[i] == first && &hay[i..i + needle.len()] == needle {
            return Some(i);
        }
        i += 1;
    }
    None
}

pub fn name_table(r: &[u8]) -> Result<Vec<String>, String> {
    let h = find(r, b"NMMANU", 0).ok_or("name table not found")?;
    let count = u32le(r, h + 6)? as usize;
    let mut p = find(r, b"\x06Entity", 0).ok_or("name table start not found")?;
    let mut names = Vec::with_capacity(count);
    while names.len() < count {
        let l = *r.get(p).ok_or("name table truncated")? as usize;
        let s = r.get(p + 1..p + 1 + l).ok_or("name table truncated")?;
        names.push(s.iter().map(|&b| b as char).collect::<String>());
        p += 1 + l;
    }
    Ok(names)
}

pub struct JEntry {
    pub guid: Option<[u8; 16]>,
    pub status: String,
}

fn vint(r: &[u8], q: &mut usize) -> Result<usize, String> {
    let b = *r.get(*q).ok_or("string length truncated")?;
    *q += 1;
    let mut ln = (b & 0x3f) as usize;
    if b & 0x40 != 0 {
        let mut sh = 6;
        loop {
            let c = *r.get(*q).ok_or("string length truncated")?;
            *q += 1;
            ln |= ((c & 0x7f) as usize) << sh;
            sh += 7;
            if c & 0x80 == 0 {
                break;
            }
        }
    }
    Ok(ln)
}

fn type_size(t: &str) -> Option<usize> {
    Some(match t {
        "Bool" | "Uint8" | "Int8" => 1,
        "Uint16" | "Int16" => 2,
        "Uint32" | "Int32" | "Float" => 4,
        "Uint64" | "Int64" | "Double" => 8,
        "CGUID" => 16,
        _ => return None,
    })
}

/// CJournalManager.JActiveEntries -> one entry per journal item (guid + status)
pub fn journal(r: &[u8], names: &[String]) -> Result<Vec<JEntry>, String> {
    // last occurrence wins, like the Python dict comprehension
    let mut ix: HashMap<&str, u16> = HashMap::new();
    for (i, n) in names.iter().enumerate() {
        ix.insert(n.as_str(), (i + 1) as u16);
    }
    let get = |n: &str| ix.get(n).copied().ok_or_else(|| format!("name '{n}' missing"));
    let nm = |i: u16| -> &str { names.get(i as usize - 1).map(|s| s.as_str()).unwrap_or("") };
    let jm = get("CJournalManager")?;
    let ses = get("SJournalEntryStatus")?;
    let mut pat = b"BS".to_vec();
    pat.extend_from_slice(&jm.to_le_bytes());
    let mut q = find(r, &pat, 0).ok_or("journal not found")? + 4;
    let mut entries: Vec<JEntry> = Vec::new();
    let mut cur = false;
    loop {
        let t = r.get(q..q + 2).ok_or("journal truncated")?;
        if t == b"BS" {
            let i = u16le(r, q + 2)?;
            if i == ses {
                entries.push(JEntry { guid: None, status: String::new() });
                cur = true;
            } else if nm(i) == "CWitcherJournalManager" {
                break;
            }
            q += 4;
            continue;
        }
        if t != b"VL" {
            return Err(format!("unexpected token at {q}"));
        }
        let name = nm(u16le(r, q + 2)?).to_string();
        let tn = nm(u16le(r, q + 4)?).to_string();
        q += 6;
        if let Some(sz) = type_size(&tn) {
            let v = r.get(q..q + sz).ok_or("journal truncated")?;
            if cur && name == "guid" && sz == 16 {
                let mut g = [0u8; 16];
                g.copy_from_slice(v);
                entries.last_mut().unwrap().guid = Some(g);
            }
            q += sz;
        } else if tn == "String" {
            let ln = vint(r, &mut q)?;
            q += ln;
        } else if tn == "CName" || tn.starts_with('E') {
            let v = nm(u16le(r, q)?).to_string();
            if cur && name == "status" {
                entries.last_mut().unwrap().status = v;
            }
            q += 2;
        } else {
            return Err(format!("unknown journal type {tn} ({name})"));
        }
    }
    Ok(entries)
}

pub fn guid_str(g: &[u8; 16]) -> String {
    (0..4)
        .map(|k| format!("{:08X}", u32::from_le_bytes([g[4 * k], g[4 * k + 1], g[4 * k + 2], g[4 * k + 3]])))
        .collect::<Vec<_>>()
        .join("-")
}

fn map_status(s: &str) -> &'static str {
    match s {
        "JS_Success" => "Done",
        "JS_Active" => "Active",
        "JS_Failed" => "Failed",
        _ => "Inactive",
    }
}

/// All quest journal files the game ships (from quest_db.json): short name, readable first name, entry (name, guid) pairs.
pub struct QuestDb {
    pub quests: Vec<(String, Vec<(String, String)>)>, // short, ids
    pub display: Vec<(String, String)>,                // short, readable name (before route overrides)
}

pub fn load_db(v: &Value) -> QuestDb {
    let mut quests = Vec::new();
    let mut display = Vec::new();
    if let Some(m) = v.as_object() {
        for (key, val) in m {
            let file = key.rsplit('\\').next().unwrap_or(key);
            let short = file.strip_suffix(".journal").unwrap_or(file).to_string();
            let ids: Vec<(String, String)> = val
                .get("ids")
                .and_then(|x| x.as_array())
                .map(|a| {
                    a.iter()
                        .filter_map(|p| {
                            let p = p.as_array()?;
                            Some((p.first()?.as_str()?.to_string(), p.get(1)?.as_str()?.to_string()))
                        })
                        .collect()
                })
                .unwrap_or_default();
            // first entry name that reads like a quest title (skip 'Descriptions', 'Quest Start', 'Start Desc', ...)
            let nm = ids
                .iter()
                .map(|(n, _)| n.clone())
                .find(|n| {
                    let l = n.trim().to_lowercase();
                    !["descriptions", "objectives", "description", "intro"].contains(&l.as_str())
                        && !l.contains("desc")
                        && !l.starts_with("quest ")
                        && !l.starts_with("start")
                        && !l.starts_with("end ")
                })
                .unwrap_or_else(|| short.clone());
            display.push((short.clone(), nm));
            quests.push((short, ids));
        }
    }
    QuestDb { quests, display }
}

const NOISE: [&str; 8] = ["mappin", "map pin", "desc", "objectives", "test ", "begining", "beginning", "new description"];

pub struct SaveState {
    pub state: HashMap<String, String>,
    pub objectives: HashMap<String, Vec<String>>,
}

/// quest file (short) -> Done/Active/Failed/Inactive/Not started, plus 'file#objective' keys and readable active objectives.
pub fn quest_states(path: &Path, db: &QuestDb) -> Result<SaveState, String> {
    let raw = load_raw(path)?;
    let names = name_table(&raw)?;
    let entries = journal(&raw, &names)?;
    let mut by_guid: HashMap<String, &'static str> = HashMap::new();
    for e in &entries {
        if let Some(g) = &e.guid {
            by_guid.insert(guid_str(g), map_status(&e.status));
        }
    }
    let mut state: HashMap<String, String> = HashMap::new();
    let mut objectives: HashMap<String, Vec<String>> = HashMap::new();
    for (short, ids) in &db.quests {
        let first = ids.first().and_then(|(_, g)| by_guid.get(g)).copied().unwrap_or("Not started");
        state.insert(short.clone(), first.to_string());
        for (name, g) in ids.iter().skip(1) {
            let nl = name.trim().to_lowercase();
            let upper = name.chars().next().map(|c| c.is_uppercase()).unwrap_or(false);
            if by_guid.get(g) == Some(&"Active") && nl.contains(' ') && upper && !NOISE.iter().any(|x| nl.contains(x)) && !nl.starts_with("q1") {
                let o = objectives.entry(short.clone()).or_default();
                let t = name.trim().to_string();
                if !o.contains(&t) {
                    o.push(t);
                }
            }
        }
        for (name, g) in ids.iter().skip(1) {
            let k = format!("{}#{}", short, name.trim());
            if let Some(&s) = by_guid.get(g) {
                if !state.contains_key(&k) || s == "Done" {
                    state.insert(k, s.to_string());
                }
            }
        }
    }
    Ok(SaveState { state, objectives })
}
