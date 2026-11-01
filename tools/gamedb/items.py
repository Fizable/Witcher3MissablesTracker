"""Stage `items`: item definitions, loot tables, rewards and Gwent cards from the REDkit XML.

Inputs (read-only, under common.R4): every XML under gameplay/items, gameplay/items_plus,
gameplay/rewards and gameplay/gui_new/gwint, and every dlc/*/data/**/*.xml. Only files whose root
is <redxml> are mapped; the others (AIR application descriptors, flex config, attitudes, gameplay
resource lists) are registered in `files` and contribute no rows.

Mapped structures (verified against the files, see the survey printed in verbose mode):
  item definition   <definitions><items><item name category price localisation_key_name ...>
                    with a <tags> child (comma list) and other children such as <base_abilities>
  loot table        <loot_definitions><loot name ...><loot_entry name quantity_min ... chance/>
  reward            <reward name level experience gold ...><items><item name amount/></items>
  Gwent card        <card index title name description power picture faction_index> in
                    def_gwint_cards_final.xml and def_gwint_battle_king_cards.xml
  Gwent deck        <deck_collection name><deck difficulty leaderCard specialCard><card name/>

Files that do not parse as XML are repaired only when the original text fails; the stored bytes
are never changed. Two repairs are applied, both invalid XML in the game files:
  * '--' inside a comment (XML forbids it): a space is inserted between the dashes
  * the same attribute twice in one start tag: the second and later values are renamed
    name__dup2, name__dup3, ... so every value is kept in attrs_json. Which value the game
    reads is unverified: in def_loot_quests.xml the copies disagree (player_level_max="100"
    first, "0" second), and the game's parser behaviour for duplicates was not checked.
Files that still fail are registered with the parser error in files.error and contribute nothing.
Every mapped element keeps all its attributes in attrs_json, so nothing is lost; children that are
not otherwise mapped go to children_json.
"""
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

import common  # noqa: E402  (sets sys.path for the shared helpers)

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    name           TEXT,
    file_id        INTEGER,
    category       TEXT,
    price          REAL,
    loc_name_key   TEXT,     -- localisation_key_name, trimmed (NULL when empty): a STRING_KEY in the strings table
    loc_desc_key   TEXT,     -- localisation_key_description, trimmed (NULL when empty)
    tags           TEXT,     -- the <tags> text as written (comma separated)
    attrs_json     TEXT,
    children_json  TEXT      -- other child elements; <tags> lives in tags and item_tags
);
CREATE TABLE IF NOT EXISTS item_tags (
    name TEXT,
    tag  TEXT
);
CREATE TABLE IF NOT EXISTS loot_tables (
    name       TEXT,
    file_id    INTEGER,
    attrs_json TEXT
);
CREATE TABLE IF NOT EXISTS loot_entries (
    loot_name    TEXT,
    item_name    TEXT,       -- the loot_entry name: an item definition name, or a gwint_card_* item
    quantity_min INTEGER,
    quantity_max INTEGER,
    chance       REAL,       -- as written (the value is copied, its meaning in the game is not checked here)
    attrs_json   TEXT,
    file_id      INTEGER     -- the XML it came from: base, ep1/bob, or the items_plus (next-gen) copy
);
CREATE TABLE IF NOT EXISTS rewards (
    name          TEXT,
    file_id       INTEGER,
    experience    INTEGER,
    gold          INTEGER,
    attrs_json    TEXT,
    children_json TEXT       -- children other than <items>, which lives in reward_items
);
CREATE TABLE IF NOT EXISTS reward_items (
    reward_name TEXT,
    item_name   TEXT,
    amount      INTEGER,
    attrs_json  TEXT
);
CREATE TABLE IF NOT EXISTS gwent_cards (
    card_index    INTEGER,
    file_id       INTEGER,
    title_key     TEXT,       -- title attribute: a STRING_KEY such as gwint_name_*
    desc_key      TEXT,       -- description attribute
    faction       TEXT,       -- faction_index, e.g. F_NEUTRAL
    power         INTEGER,
    card_type     TEXT,       -- the TYPE_* flags of the card, comma separated
    picture       TEXT,
    attrs_json    TEXT,       -- includes name, the card's script identifier
    children_json TEXT        -- type_flags, effect_flags, summonFlags, ...
);
CREATE TABLE IF NOT EXISTS gwent_decks (
    deck_name    TEXT,        -- '<collection>#<position>', suffixed with '@<file>' when the name repeats across files
    file_id      INTEGER,
    leader_index INTEGER,     -- card_index of leaderCard; NULL when unresolved or ambiguous
    attrs_json   TEXT
);
CREATE TABLE IF NOT EXISTS gwent_deck_cards (
    deck_name  TEXT,
    card_index INTEGER,       -- NULL when the card name does not resolve to exactly one definition
    copies     INTEGER
);
CREATE TABLE IF NOT EXISTS card_sources (
    card        TEXT,         -- the key of tools/card_sources.json, e.g. card_albrich
    kind        TEXT,
    detail_json TEXT          -- the whole reviewed source row
);
CREATE INDEX IF NOT EXISTS items_name ON items(name);
CREATE INDEX IF NOT EXISTS item_tags_tag ON item_tags(tag);
CREATE INDEX IF NOT EXISTS loot_entries_item ON loot_entries(item_name);
CREATE INDEX IF NOT EXISTS loot_entries_loot ON loot_entries(loot_name);
CREATE INDEX IF NOT EXISTS reward_items_item ON reward_items(item_name);
CREATE INDEX IF NOT EXISTS gwent_cards_index ON gwent_cards(card_index);
CREATE INDEX IF NOT EXISTS card_sources_card ON card_sources(card);
"""

INPUT_DIRS = ["gameplay/items", "gameplay/items_plus", "gameplay/rewards", "gameplay/gui_new/gwint"]
CARD_SOURCES = common.TOOLS / "card_sources.json"

# XML 1.0 forbids these code points; the game files contain none, but a stray one must not abort the file.
BAD_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
COMMENT = re.compile(r"<!--(.*?)-->", re.S)
START_TAG = re.compile(r"<([A-Za-z_][\w.:-]*)((?:\s+[\w.:-]+\s*=\s*(?:\"[^\"]*\"|'[^']*'))*)\s*(/?)>")
ATTR = re.compile(r"([\w.:-]+)\s*=\s*(\"[^\"]*\"|'[^']*')")


def _fix_comment(m):
    return "<!--" + re.sub(r"-(?=-)", "- ", m.group(1)) + "-->"


def _rename_dup_attrs(text):
    """(text, count): repeated attribute names in a start tag become name__dup2, name__dup3, ..."""
    renamed = [0]

    def fix(m):
        seen, parts = Counter(), []
        for a in ATTR.finditer(m.group(2)):
            seen[a.group(1)] += 1
            key = a.group(1) if seen[a.group(1)] == 1 else f"{a.group(1)}__dup{seen[a.group(1)]}"
            renamed[0] += seen[a.group(1)] > 1
            parts.append(f" {key}={a.group(2)}")
        return f"<{m.group(1)}{''.join(parts)}{m.group(3)}>"

    return START_TAG.sub(fix, text), renamed[0]


def parse_xml(raw):
    """(root, notes) for one file's bytes. Raises ET.ParseError when the repaired text still fails."""
    text = raw.decode("utf-8-sig", errors="replace")
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text, count=1)
    text = BAD_CHARS.sub("", text)
    try:
        return ET.fromstring(text), []
    except ET.ParseError as first:
        fixed = COMMENT.sub(_fix_comment, text)
        notes = []
        if fixed != text:
            notes.append("'--' inside comment spaced")
        fixed, renamed = _rename_dup_attrs(fixed)
        if renamed:
            notes.append(f"{renamed} duplicate attribute(s) renamed")
        try:
            root = ET.fromstring(fixed)
        except ET.ParseError:
            raise first
        return root, notes


def input_files():
    out = set()
    for d in INPUT_DIRS:
        folder = common.R4 / d
        if folder.is_dir():
            out.update(folder.rglob("*.xml"))
    for dlc_data in (common.R4 / "dlc").glob("*/data"):
        out.update(dlc_data.rglob("*.xml"))
    return sorted(out, key=lambda p: str(p).lower())


def to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def stripped(v):
    """Key columns hold the trimmed key (the strings stage trims STRING_KEY too); '' becomes NULL.
    The raw attribute value stays in attrs_json."""
    v = (v or "").strip()
    return v or None


def json_or_none(obj):
    return json.dumps(obj, ensure_ascii=False) if obj else None


def xml_json(el):
    node = {"tag": el.tag, "attrs": dict(el.attrib)}
    text = (el.text or "").strip()
    if text:
        node["text"] = text
    kids = [xml_json(c) for c in el]
    if kids:
        node["children"] = kids
    return node


def attrs_json(el):
    return json.dumps(dict(el.attrib), ensure_ascii=False)


def build(con, verbose=True):
    files = input_files()
    survey = Counter()        # root tag -> number of files
    skipped, repaired, failed = [], [], []
    unmapped_children = Counter()
    name_map = defaultdict(set)   # gwent card 'name' -> {card_index}
    decks = []                    # resolved after every file has been read


    for path in files:
        rel = common.rel(path)
        raw = path.read_bytes()
        try:
            root, notes = parse_xml(raw)
        except ET.ParseError as exc:
            common.file_id(con, rel, "xml", len(raw), None, f"XML parse failed: {exc}")
            failed.append((rel, str(exc)))
            continue
        survey[root.tag] += 1
        fid = common.file_id(con, rel, "xml", len(raw), None, None)
        if root.tag != "redxml":
            skipped.append((rel, root.tag))
            continue
        if notes:
            repaired.append((rel, notes))

        parents = {c: p for p in root.iter() for c in p}
        item_rows, tag_rows, loot_rows, entry_rows = [], [], [], []
        reward_rows, reward_item_rows, card_rows, deck_rows = [], [], [], []

        for el in root.iter():
            parent = parents.get(el)
            grand = parents.get(parent) if parent is not None else None
            tag = el.tag

            if tag == "item" and parent is not None and parent.tag == "items" \
                    and grand is not None and grand.tag == "definitions":
                tags_el = el.find("tags")
                tags_text = (tags_el.text or "").strip() if tags_el is not None else ""
                name = el.get("name", "")
                for t in tags_text.split(","):
                    if t.strip():
                        tag_rows.append((name, t.strip()))
                kids = [xml_json(c) for c in el if c.tag != "tags"]
                item_rows.append((name, fid, el.get("category"), to_float(el.get("price")),
                                  stripped(el.get("localisation_key_name")),
                                  stripped(el.get("localisation_key_description")),
                                  tags_text or None, attrs_json(el), json_or_none(kids)))

            elif tag == "loot":
                name = el.get("name", "")
                loot_rows.append((name, fid, attrs_json(el)))
                for c in el:
                    if c.tag != "loot_entry":
                        unmapped_children[("loot", c.tag)] += 1
                        continue
                    entry_rows.append((name, c.get("name"), to_int(c.get("quantity_min")),
                                       to_int(c.get("quantity_max")), to_float(c.get("chance")),
                                       attrs_json(c), fid))

            elif tag == "reward":
                name = el.get("name", "")
                kids = []
                for c in el:
                    if c.tag != "items":
                        kids.append(xml_json(c))
                        continue
                    for it in c:
                        if it.tag != "item":
                            unmapped_children[("items", it.tag)] += 1
                            continue
                        reward_item_rows.append((name, it.get("name"), to_int(it.get("amount")), attrs_json(it)))
                reward_rows.append((name, fid, to_int(el.get("experience")), to_int(el.get("gold")),
                                    attrs_json(el), json_or_none(kids)))

            elif tag == "card" and el.get("index") is not None:
                flags = [f.get("name") for f in el.findall("./type_flags/flag") if f.get("name")]
                if el.get("name"):
                    name_map[el.get("name")].add(to_int(el.get("index")))
                kids = [xml_json(c) for c in el]
                card_rows.append((to_int(el.get("index")), fid, el.get("title"), el.get("description"),
                                  el.get("faction_index"), to_int(el.get("power")),
                                  ",".join(flags) or None, el.get("picture"),
                                  attrs_json(el), json_or_none(kids)))

            elif tag == "deck" and parent is not None:
                coll = parent.get("name", "") if parent.tag == "deck_collection" else parent.tag
                pos = [d for d in parent if d.tag == "deck"].index(el) + 1
                for c in el:
                    if c.tag != "card":
                        unmapped_children[("deck", c.tag)] += 1
                cards = [c.get("name") or "" for c in el.findall("card")]
                decks.append({"fid": fid, "rel": rel, "base": f"{coll}#{pos}", "leader": el.get("leaderCard"),
                              "attrs": attrs_json(el), "cards": cards})

        con.executemany("INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?)", item_rows)
        con.executemany("INSERT INTO item_tags VALUES (?,?)", tag_rows)
        con.executemany("INSERT INTO loot_tables VALUES (?,?,?)", loot_rows)
        con.executemany("INSERT INTO loot_entries VALUES (?,?,?,?,?,?,?)", entry_rows)
        con.executemany("INSERT INTO rewards VALUES (?,?,?,?,?,?)", reward_rows)
        con.executemany("INSERT INTO reward_items VALUES (?,?,?,?)", reward_item_rows)
        con.executemany("INSERT INTO gwent_cards VALUES (?,?,?,?,?,?,?,?,?,?)", card_rows)

    # Gwent decks: resolve names now that every card definition is known.
    def resolve(name):
        if not name:
            return None, "empty"
        keys = [name]
        if name.startswith("gwint_card_"):
            keys.append(name[len("gwint_card_"):])
        for key in keys:
            hits = name_map.get(key)
            if hits:
                return (next(iter(hits)), "ok") if len(hits) == 1 else (None, "ambiguous")
        return None, "unresolved"

    base_count = Counter(d["base"] for d in decks)
    unresolved, ambiguous = Counter(), Counter()
    deck_rows, deck_card_rows = [], []
    for d in decks:
        deck_name = d["base"] if base_count[d["base"]] == 1 else f"{d['base']}@{d['rel']}"
        leader_idx, _ = resolve(d["leader"])
        per_card = Counter()
        bad_names = []
        for cname in d["cards"]:
            idx, status = resolve(cname)
            if status == "unresolved":
                unresolved[cname] += 1
            elif status == "ambiguous":
                ambiguous[cname] += 1
            if status != "ok":
                bad_names.append(cname)   # gwent_deck_cards has no name column: keep the name here
            per_card[idx] += 1
        attrs = d["attrs"]
        if bad_names:
            attrs = json.dumps({**json.loads(attrs), "unresolved_card_names": bad_names}, ensure_ascii=False)
        deck_rows.append((deck_name, d["fid"], leader_idx, attrs))
        for idx, copies in per_card.items():
            deck_card_rows.append((deck_name, idx, copies))
    con.executemany("INSERT INTO gwent_decks VALUES (?,?,?,?)", deck_rows)
    con.executemany("INSERT INTO gwent_deck_cards VALUES (?,?,?)", deck_card_rows)

    # Reviewed provenance from tools/card_sources.json: one row per source, original object kept.
    sources = json.loads(CARD_SOURCES.read_text(encoding="utf-8-sig"))
    source_rows = [(card, row.get("kind"), json.dumps(row, ensure_ascii=False, sort_keys=True))
                   for card, rows in sources.items() for row in rows]
    con.executemany("INSERT INTO card_sources VALUES (?,?,?)", source_rows)

    if verbose:
        mapped = survey["redxml"]
        print(f"  survey: {len(files)} xml files; roots " +
              ", ".join(f"{k}={v}" for k, v in survey.most_common()))
        print(f"  {mapped} redxml files mapped; {len(skipped)} other-root files registered without rows; "
              f"{len(repaired)} repaired on read; {len(failed)} failed")
        for rel, tag in skipped:
            print(f"    skipped (root <{tag}>): {rel}")
        for rel, notes in repaired:
            print(f"    repaired ({', '.join(notes)}): {rel}")
        for rel, err in failed:
            print(f"    FAILED: {rel}: {err}")
        if unmapped_children:
            print("  child elements kept only where they cannot be mapped: " +
                  ", ".join(f"<{p}>/<{c}>={n}" for (p, c), n in unmapped_children.most_common()))
        if unresolved:
            print(f"  deck cards with no definition: {sum(unresolved.values())} refs, names "
                  f"{sorted(unresolved)[:20]}")
        if ambiguous:
            print(f"  deck cards with more than one definition (index NULL): {sorted(ambiguous)}")
        for table in ("items", "item_tags", "loot_tables", "loot_entries", "rewards", "reward_items",
                      "gwent_cards", "gwent_decks", "gwent_deck_cards", "card_sources"):
            n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table}: {n}")
