//! Witcher 3 save reader. READ-ONLY: the save file is only ever opened for reading.
//! Port of the Python w3sav.py / w3journal.py (reverse-engineered format).

use serde_json::Value;
use std::collections::{HashMap, HashSet};
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
    pub resource: Option<String>, // journal file path, e.g. gameplay\journal\quests\q201traveltoskellige.journal
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
                entries.push(JEntry { guid: None, status: String::new(), resource: None });
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
            if cur && name == "resource" {
                if let Some(v) = r.get(q..q + ln) {
                    entries.last_mut().unwrap().resource = Some(v.iter().map(|&b| b as char).collect());
                }
            }
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

/// CFactsDB entries from the save: fact name -> its recorded values (quest scripts gate on these with FactsDo/FactsQuerySum;
/// this is the ground truth for what one quest sets and another checks, independent of any journal entry status).
pub fn facts(r: &[u8]) -> Result<HashMap<String, Vec<u16>>, String> {
    let re = regex::bytes::Regex::new(r"(?s-u)([\x81-\xff])([A-Za-z0-9_.\-]+)\x00\x00(.)\x00").map_err(|e| e.to_string())?;
    let mut out = HashMap::new();
    for caps in re.captures_iter(r) {
        let len_byte = caps.get(1).unwrap().as_bytes()[0];
        let name = caps.get(2).unwrap().as_bytes();
        if name.len() != (len_byte - 0x80) as usize {
            continue;
        }
        let count = caps.get(3).unwrap().as_bytes()[0] as usize;
        let mut p = caps.get(0).unwrap().end();
        let mut vals = Vec::with_capacity(count);
        for _ in 0..count {
            match r.get(p..p + 2) {
                Some(b) => vals.push(u16::from_le_bytes([b[0], b[1]])),
                None => break,
            }
            p += 10; // value (u16) + time (f32) + expiry (f32)
        }
        out.insert(String::from_utf8_lossy(name).to_string(), vals);
    }
    Ok(out)
}

pub fn guid_str(g: &[u8; 16]) -> String {
    (0..4)
        .map(|k| format!("{:08X}", u32::from_le_bytes([g[4 * k], g[4 * k + 1], g[4 * k + 2], g[4 * k + 3]])))
        .collect::<Vec<_>>()
        .join("-")
}

/// The raw guid of the first `key` object in CWitcherJournalManager, read from its first field (`guid`).
/// JTrackedQuest and JHighlightedObjective share this layout.
fn journal_object_guid(r: &[u8], names: &[String], key: &str) -> Option<[u8; 16]> {
    let idx = |n: &str| names.iter().rposition(|x| x == n).map(|i| (i + 1) as u16);
    let (jt, guid, cguid) = (idx(key)?, idx("guid")?, idx("CGUID")?);
    let mut pat = b"BS".to_vec();
    pat.extend_from_slice(&jt.to_le_bytes());
    let mut from = 0;
    while let Some(p) = find(r, &pat, from) {
        // object header (4 bytes), then its first field: VL guid: CGUID
        let q = p + 4;
        if r.get(q..q + 2) == Some(&b"VL"[..]) && r.get(q + 2..q + 4) == Some(&guid.to_le_bytes()[..]) && r.get(q + 4..q + 6) == Some(&cguid.to_le_bytes()[..]) {
            return r.get(q + 6..q + 22)?.try_into().ok();
        }
        from = p + 1;
    }
    None
}

/// CWitcherJournalManager.JTrackedQuest.guid -> the quest the player is tracking in the game (None if the save has none)
pub fn tracked_guid(r: &[u8], names: &[String]) -> Option<String> {
    journal_object_guid(r, names, "JTrackedQuest").map(|g| guid_str(&g))
}

/// CWitcherJournalManager.JHighlightedObjective.guid -> the objective the player selected with V in the game.
/// An all-zero guid means nothing is highlighted, so it reads as None.
pub fn highlighted_guid(r: &[u8], names: &[String]) -> Option<String> {
    journal_object_guid(r, names, "JHighlightedObjective").filter(|g| *g != [0u8; 16]).map(|g| guid_str(&g))
}

/// A raw guid as 32 hex digits (the form derived.json and the game's own files use, in file byte order)
/// -> the dashed form `guid_str` gives and the quest index stores. None if the text is not 32 hex digits.
pub fn guid_from_hex(s: &str) -> Option<String> {
    let s = s.trim();
    if s.len() != 32 || !s.is_ascii() {
        return None;
    }
    let mut g = [0u8; 16];
    for (i, b) in g.iter_mut().enumerate() {
        *b = u8::from_str_radix(&s[2 * i..2 * i + 2], 16).ok()?;
    }
    Some(guid_str(&g))
}

/// the quest file (short name) a journal guid belongs to: its top-level guid first, then any of its entries
pub fn quest_for_guid(db: &QuestDb, g: &str) -> Option<String> {
    let top = db.quests.iter().find(|(_, ids)| ids.first().map(|(_, x)| x == g).unwrap_or(false));
    top.or_else(|| db.quests.iter().find(|(_, ids)| ids.iter().any(|(_, x)| x == g))).map(|(s, _)| s.clone())
}

fn map_status(s: &str) -> &'static str {
    match s {
        "JS_Success" => "Done",
        "JS_Active" => "Active",
        "JS_Failed" => "Failed",
        _ => "Inactive",
    }
}

/// how far an entry is; used to pick between entries of one journal file
fn rank(s: &str) -> u8 {
    match s {
        "Done" => 3,
        "Active" => 2,
        "Failed" => 1,
        _ => 0,
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
    // active objective GUIDs, keyed by journal short name: the app maps them to the game's text
    pub objective_guids: HashMap<String, Vec<String>>,
    // the save's own objective labels, kept for the debug dump only
    pub objectives: HashMap<String, Vec<String>>,
    pub tracked: Option<String>,      // guid of the quest the player is tracking in the game
    pub tracked_file: Option<String>, // journal file (short) of that guid, from the save's own journal entry
    pub highlighted: Option<String>,  // guid of the objective the player selected with V (dashed, as `tracked`)
    /// Names of the game's facts this save has set (a value of 1 or more). Some route prerequisites
    /// are not "the other quest is finished" but "its story has reached the point that opens this",
    /// and the game's own condition for that is a fact (see data/prereqs_review.json).
    pub facts: HashSet<String>,
}

/// 'gameplay\journal\quests\q201traveltoskellige.journal' -> 'q201traveltoskellige'
fn journal_short(resource: &str) -> String {
    let f = resource.rsplit('\\').next().unwrap_or(resource);
    f.strip_suffix(".journal").unwrap_or(f).to_string()
}

/// quest file (short) -> Done/Active/Failed/Inactive/Not started, plus 'file#objective' keys and readable active objectives.
/// The save's Gwent ledger, keyed by the game's own card index. A missing block is an error, not
/// an empty collection: the caller must report every card as `unknown` rather than `not owned`.
#[derive(Default)]
pub struct CardCollection {
    pub normal: HashMap<i64, i64>,
    pub leaders: HashMap<i64, i64>,
}

fn card_array(
    raw: &[u8],
    names: &[String],
    index: &HashMap<&str, u16>,
    size_name: &str,
    card_name: &str,
    start: usize,
) -> Result<(HashMap<i64, i64>, usize), String> {
    let size_idx = *index.get(size_name).ok_or_else(|| format!("save has no {size_name}"))?;
    let card_idx = *index.get(card_name).ok_or_else(|| format!("save has no {card_name}"))?;
    let card_index_idx = *index.get("cardIndex").ok_or("save has no cardIndex")?;
    let copies_idx = *index.get("numCopies").ok_or("save has no numCopies")?;
    let size_type_idx = *index.get("Size").ok_or("save has no Size")?;

    let mut pattern = b"BS".to_vec();
    pattern.extend_from_slice(&size_idx.to_le_bytes());
    let pos = find(raw, &pattern, start).ok_or_else(|| format!("{size_name} block not found"))?;
    let mut q = pos + 4;
    if raw.get(q..q + 2) != Some(&b"VL"[..])
        || u16le(raw, q + 2)? != size_type_idx
        || names.get(u16le(raw, q + 4)? as usize - 1).map(|s| s.as_str()) != Some("Uint32")
    {
        return Err(format!("{size_name} has no Uint32 Size"));
    }
    let count = u32le(raw, q + 6)? as usize;
    q += 10;
    if count > 5000 {
        return Err(format!("{size_name} count {count} is not plausible"));
    }
    let mut out = HashMap::new();
    for k in 0..count {
        if raw.get(q..q + 2) != Some(&b"BS"[..]) || u16le(raw, q + 2)? != card_idx {
            return Err(format!("{size_name} card {k} starts with the wrong block"));
        }
        q += 4;
        if raw.get(q..q + 2) != Some(&b"VL"[..]) || u16le(raw, q + 2)? != card_index_idx
            || names.get(u16le(raw, q + 4)? as usize - 1).map(|s| s.as_str()) != Some("Int32")
        {
            return Err(format!("{size_name} card {k} has no cardIndex"));
        }
        let card_index = u32le(raw, q + 6)? as i32 as i64;
        q += 10;
        if raw.get(q..q + 2) != Some(&b"VL"[..]) || u16le(raw, q + 2)? != copies_idx
            || names.get(u16le(raw, q + 4)? as usize - 1).map(|s| s.as_str()) != Some("Int32")
        {
            return Err(format!("{size_name} card {k} has no numCopies"));
        }
        let copies = u32le(raw, q + 6)? as i32 as i64;
        q += 10;
        if copies > 0 {
            out.insert(card_index, copies);
        }
    }
    Ok((out, q))
}

pub fn card_collection(path: &Path) -> Result<CardCollection, String> {
    let raw = load_raw(path)?;
    let names = name_table(&raw)?;
    let mut index: HashMap<&str, u16> = HashMap::new();
    for (i, name) in names.iter().enumerate() {
        index.insert(name.as_str(), (i + 1) as u16);
    }
    for needed in ["CR4GwintManager", "SBCollectionCardSize", "SBCollectionCard",
                   "SBLeaderCollectionCardSize", "SBLeaderCollectionCard", "cardIndex", "numCopies"] {
        if !index.contains_key(needed) {
            return Err(format!("save has no Gwent collection block: missing {needed}"));
        }
    }
    let (normal, end) = card_array(&raw, &names, &index, "SBCollectionCardSize", "SBCollectionCard", 0)?;
    let (leaders, _) = card_array(&raw, &names, &index, "SBLeaderCollectionCardSize", "SBLeaderCollectionCard", end)?;
    Ok(CardCollection { normal, leaders })
}

pub fn quest_states(path: &Path, db: &QuestDb) -> Result<SaveState, String> {
    let raw = load_raw(path)?;
    let names = name_table(&raw)?;
    let tracked = tracked_guid(&raw, &names);
    let highlighted = highlighted_guid(&raw, &names);
    let entries = journal(&raw, &names)?;
    // the save's journal entry with the tracked guid names the file; the quest index does not list every entry guid
    let tracked_file = tracked.as_deref().and_then(|g| {
        entries.iter().find(|e| e.guid.as_ref().map(guid_str).as_deref() == Some(g)).and_then(|e| e.resource.as_deref()).map(journal_short)
    });
    let mut by_guid: HashMap<String, &'static str> = HashMap::new();
    for e in &entries {
        if let Some(g) = &e.guid {
            by_guid.insert(guid_str(g), map_status(&e.status));
        }
    }
    let mut state: HashMap<String, String> = HashMap::new();
    let mut objective_guids: HashMap<String, Vec<String>> = HashMap::new();
    let mut objectives: HashMap<String, Vec<String>> = HashMap::new();
    for (short, ids) in &db.quests {
        let own = ids.first().and_then(|(_, g)| by_guid.get(g)).copied().unwrap_or("Not started");
        // The quest's own entry decides whenever the game moves it. For a handful of quests the game
        // leaves that entry absent or Inactive and moves a description entry instead (Novigrad, Under
        // Control; the four Brothers In Arms; Destination: Skellige's siblings). Checked against 517
        // saves: reading only the quest's own entry would lose registration for 8 of them, so fall back
        // to the most advanced entry of the same file rather than calling the quest not started.
        let st = if rank(own) == 0 {
            ids.iter()
                .skip(1)
                .filter_map(|(_, g)| by_guid.get(g))
                .copied()
                .max_by_key(|s| rank(s))
                .filter(|s| rank(s) > 0)
                .unwrap_or(own)
        } else {
            own
        };
        state.insert(short.clone(), st.to_string());
        for (name, g) in ids.iter().skip(1) {
            let nl = name.trim().to_lowercase();
            let upper = name.chars().next().map(|c| c.is_uppercase()).unwrap_or(false);
            if by_guid.get(g) == Some(&"Active") && nl.contains(' ') && upper && !NOISE.iter().any(|x| nl.contains(x)) && !nl.starts_with("q1") {
                let o = objectives.entry(short.clone()).or_default();
                let t = name.trim().to_string();
                if !o.contains(&t) {
                    o.push(t);
                }
                // the name above is often an internal label ("SQ202 At Larvik"); the GUID is what
                // lets the UI show the game's own objective sentence instead
                let q = objective_guids.entry(short.clone()).or_default();
                if !q.contains(g) {
                    q.push(g.clone());
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
    // the tracked quest's own save entry is the authority for its file: the file's first id is not always the quest
    // (q304dandelion starts with a 'Rosa' entry that completes mid-quest while the quest stays open)
    if let (Some(f), Some(g)) = (&tracked_file, &tracked) {
        if let Some(&s) = by_guid.get(g) {
            state.insert(f.clone(), s.to_string());
        }
    }
    let facts: HashSet<String> = facts(&raw)?
        .into_iter()
        .filter(|(_name, vals)| vals.iter().any(|v| *v > 0))
        .map(|(name, _vals)| name)
        .collect();
    Ok(SaveState { state, objective_guids, objectives, tracked, tracked_file, highlighted, facts })
}

#[cfg(test)]
mod guid_tests {
    use super::*;

    #[test]
    fn hex_from_derived_matches_the_dashed_form_the_save_and_index_use() {
        // derived.json (raw hex, file byte order) and the quest index / save (dashed, u32 little-endian
        // printed as hex) name the same objective; this pair was checked against the cached quest index
        assert_eq!(guid_from_hex("daba22a8fc21204eaedce0d2c5161c9f").as_deref(), Some("A822BADA-4E2021FC-D2E0DCAE-9F1C16C5"));
        // the index's own dashed guid, read back to raw bytes, gives the same hex again
        let raw: String = "CB9A683E-401D6D11-8D174DA7-9A673C01".split('-')
            .flat_map(|p| u32::from_str_radix(p, 16).unwrap().to_le_bytes())
            .map(|b| format!("{b:02x}"))
            .collect();
        assert_eq!(guid_from_hex(&raw).as_deref(), Some("CB9A683E-401D6D11-8D174DA7-9A673C01"));
        // upper case input is the same guid; anything that is not 32 hex digits is not a guid
        assert_eq!(guid_from_hex("DABA22A8FC21204EAEDCE0D2C5161C9F").as_deref(), Some("A822BADA-4E2021FC-D2E0DCAE-9F1C16C5"));
        assert_eq!(guid_from_hex("daba22a8"), None);
        assert_eq!(guid_from_hex("zaba22a8fc21204eaedce0d2c5161c9f"), None);
    }
}
