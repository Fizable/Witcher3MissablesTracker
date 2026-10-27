//! Minimal CR2W reader for the game's own quest journal files, so the quest index can be built from
//! the entry that really is the quest instead of whatever name happens to come first.
//!
//! A journal file (`gameplay\journal\quests\<name>.journal`) is CR2W. Its quest-level entry is the
//! `CJournalQuest` export; every objective, map pin and description is a separate export with its own
//! guid. `bundles.rs` used to take the first "name GUID" string it could find, which for 46 of 441
//! quests is a map pin ("Crach Mappin") or a description entry - so Lord of Undvik and The King is Dead
//! never registered in a save at all.
//!
//! This reads only the two fields needed: the quest entry's `guid`, and its `baseName`.

pub struct JournalQuest {
    pub guid: String,           // dashed, the same form the quest index and route data use
    pub name: Option<String>,
}

fn u16at(b: &[u8], o: usize) -> Option<u16> {
    b.get(o..o + 2).map(|s| u16::from_le_bytes([s[0], s[1]]))
}

fn u32at(b: &[u8], o: usize) -> Option<u32> {
    b.get(o..o + 4).map(|s| u32::from_le_bytes([s[0], s[1], s[2], s[3]]))
}

/// CGUID bytes -> "B5130AE1-468A2171-0B7BD3B0-3FBE5499" (same order as the save reader).
fn guid_str(g: &[u8]) -> String {
    (0..4)
        .map(|k| format!("{:08X}", u32::from_le_bytes([g[4 * k], g[4 * k + 1], g[4 * k + 2], g[4 * k + 3]])))
        .collect::<Vec<_>>()
        .join("-")
}

fn read_string(sub: &[u8]) -> Option<String> {
    if sub.is_empty() {
        return None;
    }
    let (start, len) = if sub[0] & 0x80 != 0 {
        (1usize, (sub[0] & 0x7f) as usize)
    } else {
        (0usize, sub.iter().position(|&c| c == 0).unwrap_or(sub.len()))
    };
    sub.get(start..start + len).map(|s| s.iter().map(|&c| c as char).collect())
}

/// `props` -> the properties of one export, as (name, type name, raw value bytes).
fn props<'a>(payload: &'a [u8], names: &[String]) -> Vec<(String, String, &'a [u8])> {
    let mut out = Vec::new();
    if payload.is_empty() {
        return out;
    }
    let lead = payload[0] as i8;
    let mut pos = 1usize;
    if lead == -128 {
        return out;
    } else if lead == 1 {
        pos += 4;
    } else if lead != 0 {
        return out;
    }
    while pos + 8 <= payload.len() {
        let name_id = u16at(payload, pos).unwrap_or(0) as usize;
        if name_id == 0 {
            break;
        }
        let type_id = u16at(payload, pos + 2).unwrap_or(0) as usize;
        let size = u32at(payload, pos + 4).unwrap_or(0) as usize;
        pos += 8;
        if size < 4 || pos + size - 4 > payload.len() {
            break;
        }
        let name = names.get(name_id).cloned().unwrap_or_default();
        let tname = names.get(type_id).cloned().unwrap_or_default();
        out.push((name, tname, &payload[pos..pos + size - 4]));
        pos += size - 4;
    }
    out
}

/// The quest-level entry of a journal file, or None when the file cannot be read.
pub fn parse(data: &[u8]) -> Option<JournalQuest> {
    if data.len() < 160 || &data[..4] != b"CR2W" {
        return None;
    }
    // ten tables (offset, size, crc) start at 40; the string table follows them
    let strings_size = u32at(data, 40 + 4)? as usize; // table 0's count is its byte size
    let mut pos = 160usize;
    if strings_size == 0 || strings_size > data.len() - pos {
        return None;
    }
    let raw_strings = data.get(pos..pos + strings_size)?;
    pos += strings_size;

    // table i is (offset, count, crc): the count sits at +4, not +8
    let table = |i: usize| -> Option<(u32, u32)> {
        Some((u32at(data, 40 + 12 * i)?, u32at(data, 40 + 12 * i + 4)?))
    };

    // every remaining table starts with a count/byte-size that has to fit the file, or a corrupt or
    // unexpected journal must not make us allocate on a garbage length (seen as a 100 GB request)
    let room = |pos: usize, per: usize| -> Option<usize> {
        if per == 0 || pos >= data.len() {
            return None;
        }
        Some((data.len() - pos) / per)
    };

    let (_, names_count) = table(1)?;
    let names_count = (names_count as usize).min(room(pos, 8)?);
    let mut names = Vec::with_capacity(names_count);
    for _ in 0..names_count {
        let idx = u32at(data, pos)? as usize;
        pos += 8;
        if idx >= raw_strings.len() {
            return None;
        }
        // strings are a NUL-separated blob; index is a byte offset into it
        let end = raw_strings[idx..].iter().position(|&c| c == 0).map(|e| idx + e).unwrap_or(raw_strings.len());
        names.push(raw_strings.get(idx..end).map(|s| s.iter().map(|&c| c as char).collect::<String>()).unwrap_or_default());
    }

    let (_, imports_count) = table(2)?;
    pos += (imports_count as usize).min(room(pos, 8).unwrap_or(0)) * 8;
    let (_, props_count) = table(3)?;
    pos += (props_count as usize).min(room(pos, 16).unwrap_or(0)) * 16;

    let (_, exports_count) = table(4)?;
    let exports_count = (exports_count as usize).min(room(pos, 24)?);
    for i in 0..exports_count {
        let e = pos + 24 * i;
        let class = u16at(data, e)? as usize;
        let data_size = u32at(data, e + 8)? as usize;
        let data_off = u32at(data, e + 12)? as usize;
        if names.get(class).map(|s| s.as_str()) != Some("CJournalQuest") {
            continue;
        }
        let payload = data.get(data_off..data_off.checked_add(data_size)?)?;
        let mut guid: Option<Vec<u8>> = None;
        let mut name: Option<String> = None;
        for (pname, ptype, value) in props(payload, &names) {
            if pname == "guid" && ptype == "CGUID" && value.len() >= 16 {
                guid = Some(value[..16].to_vec());
            } else if pname == "baseName" && ptype == "String" {
                name = read_string(value);
            }
        }
        if let Some(g) = guid {
            return Some(JournalQuest { guid: guid_str(&g), name });
        }
    }
    None
}

#[cfg(test)]
mod tests {
    /// End-to-end: build the quest index from whatever game install W3_GAME_DIR points at and check
    /// that a few quests are read from their own journal entry. The expected guids come from the
    /// quest's own CJournalQuest export in the REDkit journal files.
    #[test]
    fn the_quest_index_reads_each_quests_own_entry() {
        let Ok(dir) = std::env::var("W3_GAME_DIR") else {
            eprintln!("W3_GAME_DIR not set; skipping the quest index test");
            return;
        };
        let game = std::path::PathBuf::from(dir);
        assert!(crate::bundles::is_game_dir(&game), "W3_GAME_DIR is not a Witcher 3 install");
        let db = crate::save::load_db(&crate::bundles::build_quest_db(&game).expect("quest index"));
        let want = [
            ("giant", "8F37175C-4DFFD952-3F6BC896-95E94AAB"),
            ("pirate", "FB952C6E-46B165C3-C41A748A-802EC470"),
            ("q206berserkers", "B5130AE1-468A2171-0B7BD3B0-3FBE5499"),
            ("q208heroesmead", "9540A12A-49AA6796-7BC8E7BE-848030A4"),
            ("q201traveltoskellige", "550442BD-43AF7D49-9E0A09B5-54BCCDCC"),
            ("q304dandelion", "85131BEE-4AF999EC-AD9B0586-FA06CE11"),
            ("q101agent", "3D77BF9D-4F453FF0-66AA658F-A6353227"),
            ("q309novigradundercontrol", "364A7C69-447A6558-3BCED280-6A244406"),
        ];
        for (short, guid) in want {
            let ids = db
                .quests
                .iter()
                .find(|(s, _)| s == short)
                .map(|(_, i)| i)
                .unwrap_or_else(|| panic!("{short} missing from the quest index"));
            assert_eq!(ids[0].1, guid, "{short} is read from the wrong journal entry");
        }
    }
}
