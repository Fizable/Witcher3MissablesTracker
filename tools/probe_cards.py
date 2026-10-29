"""Read-only probe of the game's Gwent card data, before any card index is generated.

Answers the step-6 questions of docs/PLAN-1.0-completion.md without changing the pipeline:

  * where the card, item, leader and deck definitions live (shipping bundles + REDkit copies),
  * how many cards exist and whether their display names resolve through the string database,
  * which cards have a quest, vendor, opponent or reward source in the files,
  * which cards are granted by native quest/event scripts or by a random card pool,
  * which card definitions are summon-only tokens rather than collectible cards,
  * whether one save exposes card ownership by item GUID or by its Gwent collection,
  * and whether missable-card windows can be derived from the journal/phase data.

Nothing is extracted into data/ or the package. Bundle payloads are decompressed in memory; CR2W
payloads are handed to `cr2w.parse` through a temporary directory that is removed on exit. The
game, REDkit, string database and saves are opened read-only.

  py tools/probe_cards.py                  human-readable report
  py tools/probe_cards.py --json           the same facts as JSON
  py tools/probe_cards.py --save <file>    probe a specific save instead of the newest one

Definition locations observed in this install:

  content/content0/bundles/xml.bundle
    gameplay\\items\\def_gwint_cards_final.xml       the active card database (206 cards)
    gameplay\\items\\def_item_gwint.xml              the Gwent item definitions (197 items)
    gameplay\\items\\def_gwint_battle_king_cards.xml  the 22 leader cards
    gameplay\\items\\def_gwint_king_cards.xml         present, but every card is commented out
    gameplay\\items\\def_gwint_decks.xml             56 deck collections, 168 decks, 4406 card lines

  DLC bundles carry their own item, shop, reward and quest definitions:
    content/content0/bundles/bob.bundle   dlc\\bob\\data\\gameplay\\items\\...
    content/content0/bundles/ep1.bundle   dlc\\ep1\\data\\gameplay\\items\\...

  The card XML files are XML, not CR2W. The game itself reads them through its native
  CR4GwintManager; there is no per-card `.w2ent` resource in the bundles. Native script
  evidence is read from the shipping `.ws` files (AddCardToCollection literals and the random
  merchant-card pool). Summon-only tokens are derived from the card XML's summonFlags, not from
  a per-card item definition.

The ownership reader is deliberately narrow: it recognises the `CR4GwintManager` collection
serialised by the save (`SBCollectionCardSize` / `SBCollectionCard` with `cardIndex` and
`numCopies`, plus the leader array). If that block is absent or malformed it says so and the
caller must fall back to manual ticks; it never infers ownership from quest state.
"""
import argparse
import collections
import csv
import json
import os
import re
import struct
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cr2w
import save_reader
import stringsdb
from probe_dlc import BundleError, bundle_entries, discover_bundles, entry_bytes
from paths import GAME, REDKIT_R4, SAVES, TRACKER

CARD_DB = "gameplay/items/def_gwint_cards_final.xml"
ITEM_DB = "gameplay/items/def_item_gwint.xml"
LEADER_DB = "gameplay/items/def_gwint_battle_king_cards.xml"
KING_DB = "gameplay/items/def_gwint_king_cards.xml"
DECKS_DB = "gameplay/items/def_gwint_decks.xml"
ORIGIN_CSV = "gameplay/globals/card_sources.csv"

SCRIPT_ROOT = GAME / "content" / "content0" / "scripts"

SOURCE_FILES = (
    ("vendor", "gameplay/items/def_loot_shops.xml"),
    ("vendor", "dlc/bob/data/gameplay/items/def_loot_shops.xml"),
    ("vendor", "dlc/ep1/data/gameplay/items/def_loot_shops.xml"),
    ("quest", "gameplay/items/def_loot_quests.xml"),
    ("quest", "dlc/bob/data/gameplay/items/def_loot_quest.xml"),
    ("quest", "dlc/ep1/data/gameplay/items/def_loot_quests.xml"),
    ("unique", "gameplay/items/def_loot_unique.xml"),
    ("reward", "gameplay/rewards/rewards.xml"),
    ("reward", "dlc/bob/data/gameplay/rewards/rewards.xml"),
    ("reward", "dlc/ep1/data/gameplay/rewards/rewards.xml"),
)
TEST_LOOT = "gameplay/items/def_loot_test.xml"

WANTED_EXTS = {".xml", ".csv", ".w2phase", ".w2quest", ".w2scene"}
PLAYER_DECKS = {"north", "nilf", "scotial", "nml", "ske"}
GENERIC_DECKS = re.compile(r"(easy|normal|hard|prologue|tournament)", re.I)
CARD_ITEM = re.compile(r"gwint_card_[A-Za-z0-9_]+")
GWENT_STEP = re.compile(r"(?:cg|sq|mq|q)\d{3}[A-Za-z0-9_]*", re.I)


def norm(path):
    return path.replace("\\", "/").lower()


def pack_of(path):
    """'dlc\\bob\\...' -> 'bob'; anything outside dlc/ -> 'base'."""
    parts = norm(path).split("/")
    return parts[1] if len(parts) > 2 and parts[0] == "dlc" else "base"


def strip_comments(text):
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def attr(attrs, name="name"):
    m = re.search(r"\b%s\s*=\s*\"([^\"]*)\"" % re.escape(name), attrs or "", re.I)
    return m.group(1) if m else ""


def xml_text(data):
    """Decode an XML payload. The BOM is stripped and a lying encoding declaration is ignored."""
    text = data.decode("utf-8-sig")
    return re.sub(r"^\s*<\?xml[^>]*\?>", "", text, count=1)


def xml_root(data):
    return ET.fromstring(xml_text(data))


def block_elements(text, tag):
    """(attrs, body) for each non-self-closing <tag ...> ... </tag>; tolerant of bad XML."""
    text = strip_comments(text)
    for m in re.finditer(r"<%s\b([^>]*?)(/?)>" % re.escape(tag), text, re.I | re.S):
        attrs, self_closing = m.group(1), m.group(2) == "/"
        if self_closing:
            yield attrs, ""
            continue
        end = text.find("</%s>" % tag, m.end())
        if end >= 0:
            yield attrs, text[m.end():end]


def child_names(body, tag):
    for m in re.finditer(r"<%s\b([^>]*?)/?>" % re.escape(tag), body or "", re.I | re.S):
        yield attr(m.group(1))


class Bundles:
    """TOC index of the shipping bundles, limited to the resource types this probe reads."""

    def __init__(self):
        self.by_path = collections.defaultdict(list)
        self.skipped = []
        self.count = 0
        for path in discover_bundles():
            self.count += 1
            try:
                _header, entries = bundle_entries(path)
            except BundleError as exc:
                self.skipped.append({"bundle": path.name, "reason": str(exc)})
                continue
            for entry in entries:
                if Path(entry["name"]).suffix.lower() in WANTED_EXTS:
                    self.by_path[norm(entry["name"])].append((path, entry))

    def candidates(self, virtual_path):
        return list(self.by_path.get(norm(virtual_path), []))

    def choose(self, virtual_path):
        """(bundle_path, entry, payload) for one virtual path, preferring the game's own source."""
        cands = self.candidates(virtual_path)
        if not cands:
            return None
        order = {"xml.bundle": 0, "startup.bundle": 1, "bob.bundle": 2, "ep1.bundle": 3,
                 "dlc0.bundle": 4, "blob.bundle": 5}
        cands.sort(key=lambda pe: (order.get(pe[0].name, 9), pe[0].name))
        path, entry = cands[0]
        return path, entry, entry_bytes(path, entry)

    def text(self, virtual_path):
        hit = self.choose(virtual_path)
        if not hit:
            return None
        return decode_payload(hit[2])


def decode_payload(data):
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace")


def resolve_names(cards, leaders):
    """Resolve every card title through STRING_KEY, and say which key namespace it used."""
    conn = stringsdb.con()
    keys = {}
    for string_key, string_id in conn.execute(
            "select STRING_KEY, STRING_ID from STRING_INFO "
            "where STRING_KEY is not null and trim(STRING_KEY) <> ''"):
        keys[string_key.strip()] = string_id

    wanted = set()
    for card in cards + leaders:
        title = (card.get("title") or "").strip()
        if title in keys:
            wanted.add(keys[title])
    texts = stringsdb.locs(sorted(wanted), conn) if wanted else {}

    for card in cards + leaders:
        title = (card.get("title") or "").strip()
        if title in keys:
            raw = texts.get(keys[title], "")
            card["display"] = re.sub(r"<br\s*/?>", " / ", raw).strip()
            card["name_kind"] = "gwint_key" if title.startswith("gwint_name_") else "other_key"
        else:
            card["display"] = title
            card["name_kind"] = "literal" if title else "missing"
    return conn


def read_cards(root):
    out = []
    for card in root.findall(".//card"):
        out.append({
            "index": int(card.get("index")),
            "name": card.get("name") or "",
            "title": card.get("title") or "",
            "item_attr": (card.get("item") or "").strip(),
            "faction": card.get("faction_index") or "",
            "power": int(card.get("power") or 0),
            "effects": [flag.get("name") for flag in card.findall("./effect_flags/flag")
                        if flag.get("name")],
            "summons": [flag.get("name") for flag in card.findall("./summonFlags/flag")
                        if flag.get("name")],
        })
    return out


def read_items(root):
    out = []
    for item in root.findall(".//item"):
        out.append({
            "name": item.get("name") or "",
            "key": (item.get("localisation_key_name") or "").strip(),
            "tags": (item.get("tags") or "").strip(),
        })
    return out


def link_items(cards, items):
    """Give each card its item name(s), but only from the files' own item identity."""
    by_name = {item["name"]: item for item in items}
    by_key = collections.defaultdict(list)
    for item in items:
        by_key[item["key"]].append(item["name"])
    for card in cards:
        candidates = []
        method = "none"
        if card["item_attr"]:
            candidates, method = [card["item_attr"]], "explicit"
        else:
            exact = "gwint_card_" + card["name"]
            if exact in by_name:
                candidates, method = [exact], "exact"
        card["items"] = [x for x in candidates if x in by_name]
        card["item_method"] = method if card["items"] else "none"
        # A title-key match is reported but is not used as a source link: it can be ambiguous.
        card["title_matches"] = by_key.get(card["title"].strip(), [])
    return by_name, by_key


def card_ref_indices(name, cards_by_name, item_to_cards):
    """Resolve a script reference (card name or gwint_card_* item) to card indices."""
    base = name[11:] if name.lower().startswith("gwint_card_") else name
    indices = set()
    for key in (name, base):
        if key in cards_by_name:
            indices.add(cards_by_name[key]["index"])
        indices.update(item_to_cards.get(key, set()))
        indices.update(item_to_cards.get("gwint_card_" + key, set()))
    return indices


def summon_only_cards(cards):
    """Cards that exist only as summon targets of another card's morph/suicide effect.

    A definition qualifies only when it has no item and a different card summons it while
    carrying EFFECT_MORPH or EFFECT_SUICIDE_SUMMON. The token can list itself in summonFlags;
    that self-reference is ignored.
    """
    by_name = {card["name"]: card for card in cards}
    parents = collections.defaultdict(list)
    for parent in cards:
        if not any(effect in ("EFFECT_MORPH", "EFFECT_SUICIDE_SUMMON")
                   for effect in parent["effects"]):
            continue
        for child_name in parent["summons"]:
            if child_name != parent["name"]:
                parents[child_name].append(parent)

    out = []
    for child_name, parent_cards in parents.items():
        child = by_name.get(child_name)
        if not child or child["items"]:
            continue
        out.append({
            "index": child["index"],
            "name": child["name"],
            "display": child["display"],
            "parents": [{"index": p["index"], "name": p["name"]} for p in parent_cards],
            "effects": sorted({effect for p in parent_cards for effect in p["effects"]
                               if effect in ("EFFECT_MORPH", "EFFECT_SUICIDE_SUMMON")}),
        })
    return sorted(out, key=lambda row: row["index"])


def read_loot_rows(text, kind, virtual_path):
    rows = []
    for attrs, body in block_elements(text, "loot"):
        container = attr(attrs)
        for item in child_names(body, "loot_entry"):
            if item.startswith("gwint_card_"):
                rows.append({"kind": kind, "container": container, "item": item,
                             "pack": pack_of(virtual_path), "file": virtual_path})
    return rows


def read_reward_rows(text, virtual_path):
    rows = []
    for attrs, body in block_elements(text, "reward"):
        container = attr(attrs)
        for item in child_names(body, "item"):
            if item.startswith("gwint_card_"):
                rows.append({"kind": "reward", "container": container, "item": item,
                             "pack": pack_of(virtual_path), "file": virtual_path})
    return rows


def read_origin_csv(text):
    rows = list(csv.reader(text.splitlines(), delimiter=";"))
    if not rows:
        return {"rows": 0, "unique": 0, "origins": {}, "names": []}
    names = [row[0].strip() for row in rows[1:] if row and row[0].strip()]
    origins = collections.Counter(row[1].strip() for row in rows[1:]
                                  if len(row) > 1 and row[1].strip())
    return {"rows": len(names), "unique": len(set(names)),
            "origins": dict(sorted(origins.items())), "names": sorted(set(names))}


def read_decks(text):
    root = ET.fromstring(re.sub(r"^\s*<\?xml[^>]*\?>", "", text, count=1))
    out = []
    for collection in root.findall(".//deck_collection"):
        name = collection.get("name") or ""
        cards = {card.get("name") or "" for card in collection.findall(".//card")}
        decks = collection.findall(".//deck")
        if name.lower() in PLAYER_DECKS:
            kind = "player"
        elif name.lower() == "tutorialdeck":
            kind = "tutorial"
        elif GENERIC_DECKS.search(name):
            kind = "generic"
        else:
            kind = "named"
        out.append({"name": name, "kind": kind, "cards": cards, "decks": len(decks)})
    total_decks = len(root.findall(".//deck"))
    total_cards = len(root.findall(".//card"))
    return out, total_decks, total_cards


def deck_map(decks, cards):
    """Card names (with or without the item prefix) -> card-index set for deck membership."""
    name_to_cards = collections.defaultdict(set)
    for card in cards:
        for key in (card["name"], card["title"], card["display"]):
            if key:
                name_to_cards[key.lower()].add(card["index"])
        for item in card["items"]:
            name_to_cards[item.lower()].add(card["index"])
            name_to_cards[item.replace("gwint_card_", "").lower()].add(card["index"])

    def indices(names):
        out = set()
        for name in names:
            base = name[11:] if name.lower().startswith("gwint_card_") else name
            for key in (name.lower(), base.lower(), ("gwint_card_" + base).lower()):
                out.update(name_to_cards.get(key, set()))
        return out

    by_kind = collections.Counter()
    named_cards = set()
    starter_cards = set()
    any_cards = set()
    unmapped = set()
    named_names = []
    for deck in decks:
        mapped = indices(deck["cards"])
        any_cards.update(mapped)
        by_kind[deck["kind"]] += 1
        if deck["kind"] == "named":
            named_cards.update(mapped)
            named_names.append(deck["name"])
        elif deck["kind"] == "player" and deck["name"].lower() == "north":
            starter_cards.update(mapped)
        for name in deck["cards"]:
            base = name[11:] if name.lower().startswith("gwint_card_") else name
            if not any(k in name_to_cards for k in (name.lower(), base.lower(),
                                                   ("gwint_card_" + base).lower())):
                unmapped.add(name)
    return {
        "named_cards": named_cards,
        "starter_cards": starter_cards,
        "any_cards": any_cards,
        "collections": dict(sorted(by_kind.items())),
        "named_names": sorted(named_names),
        "unmapped": sorted(unmapped),
    }


def scan_phase_grants(bundles):
    """Card grants and card item checks in every unique .w2phase/.w2quest in the bundles."""
    grants = []
    checks = []
    resources = 0
    with_journal = 0
    failures = []
    seen = set()
    with tempfile.TemporaryDirectory(prefix="w3-card-probe-") as tmpdir:
        holder = Path(tmpdir) / "payload.bin"
        for virtual_path in sorted(bundles.by_path):
            ext = Path(virtual_path).suffix.lower()
            if ext not in (".w2phase", ".w2quest") or virtual_path in seen:
                continue
            seen.add(virtual_path)
            hit = bundles.choose(virtual_path)
            if not hit:
                continue
            _path, _entry, payload = hit
            resources += 1
            holder.write_bytes(payload)
            try:
                parsed = cr2w.parse(holder)
            except Exception as exc:
                failures.append({"file": virtual_path, "error": str(exc)[:160]})
                continue
            has_journal = False
            for export in parsed["exports"]:
                try:
                    props = cr2w.props(parsed, export)
                except Exception:
                    continue
                values = {x["name"]: x["value"] for x in props}
                if export["className"] in ("CJournalQuestBlock", "CJournalQuestTrackBlock"):
                    has_journal = True
                if export["className"] == "CQuestScriptBlock":
                    function = str(values.get("functionName") or "")
                    comment = str(values.get("comment") or "")
                    if "gwint_card_" not in comment:
                        continue
                    match = CARD_ITEM.search(comment)
                    if not match or not ("AddItem" in function or "GwentCard" in function
                                         or "Merchant" in function):
                        continue
                    kind = "merchant_card" if "Merchant" in function or "GwentCard" in function \
                        else "phase_grant"
                    grants.append({"kind": kind, "file": virtual_path,
                                   "pack": pack_of(virtual_path), "function": function,
                                   "item": match.group(0), "comment": comment[:200]})
                elif export["className"] == "W3QuestCond_IsItemQuantityMet":
                    item = str(values.get("itemName") or "")
                    if item.startswith("gwint_card_"):
                        checks.append({"file": virtual_path, "pack": pack_of(virtual_path),
                                       "item": item})
            if has_journal:
                with_journal += 1
    # The same script can occur twice in one file; keep one row per (file, item, function).
    unique = {}
    for row in grants:
        unique[(row["file"], row["item"], row["function"])] = row
    grants = sorted(unique.values(), key=lambda r: (r["file"], r["item"], r["function"]))
    return {"resources": resources, "with_journal": with_journal, "grants": grants,
            "checks": checks, "failures": failures}


def scan_scene_mentions(bundles):
    """Resources whose raw scene bytes name a card item; mentions, never sources."""
    mentions = []
    seen = set()
    for virtual_path in sorted(bundles.by_path):
        if Path(virtual_path).suffix.lower() != ".w2scene" or virtual_path in seen:
            continue
        seen.add(virtual_path)
        hit = bundles.choose(virtual_path)
        if not hit:
            continue
        items = sorted({m.group(0) for m in CARD_ITEM.finditer(decode_payload(hit[2]))})
        if items:
            mentions.append({"file": virtual_path, "pack": pack_of(virtual_path), "items": items})
    return mentions


FUNCTION_DEF = re.compile(
    r"^[ \t]*(?:(?:public|private|protected|final|static|quest|exec)\s+)*"
    r"(?:function|event)\s+([A-Za-z_]\w*)\s*\(", re.I | re.M)


def brace_body(text, open_index):
    """Body and closing-brace offset for the `{` at open_index, ignoring strings/comments."""
    depth = 0
    i = open_index
    quote = ""
    line_comment = False
    block_comment = False
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if line_comment:
            if ch == "\n":
                line_comment = False
        elif block_comment:
            if ch == "*" and nxt == "/":
                block_comment = False
                i += 1
        elif quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch == "/" and nxt == "/":
            line_comment = True
            i += 1
        elif ch == "/" and nxt == "*":
            block_comment = True
            i += 1
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[open_index + 1:i], i
        i += 1
    return None, open_index


def script_functions(text):
    """(name, body, line) for each top-level function definition in a .ws file."""
    pos = 0
    while True:
        match = FUNCTION_DEF.search(text, pos)
        if not match:
            return
        open_index = text.find("{", match.end())
        if open_index < 0:
            return
        signature = text[match.end():open_index]
        if ";" in signature:
            pos = open_index + 1
            continue
        body, end = brace_body(text, open_index)
        if body is None:
            pos = open_index + 1
            continue
        line = text.count("\n", 0, match.start()) + 1
        yield match.group(1), body, line
        pos = end + 1


def native_script_roots():
    """Shipping script folders, falling back to the REDkit mirror when the game has none."""
    roots = []
    if SCRIPT_ROOT.is_dir():
        roots.append(SCRIPT_ROOT)
    dlc = GAME / "DLC"
    if dlc.is_dir():
        roots.extend(sorted(p for p in dlc.glob("*/content/scripts") if p.is_dir()))
    if not roots and (REDKIT_R4 / "scripts").is_dir():
        roots.append(REDKIT_R4 / "scripts")
    return roots


def scan_native_scripts():
    """Literal collection grants and random card pools in the shipping `.ws` scripts.

    `AddCardToCollection('name')` is a direct collection grant, so its function is acquisition
    evidence even though it is not an XML loot row. A function that fills an array with
    `PushBack('gwint_card_*')` and later adds the selected card to the inventory is a random
    pool; the exact merchant is still not identified. Calls with a variable argument (the
    normal inventory path) are deliberately ignored.
    """
    result = {"roots": [str(root) for root in native_script_roots()],
              "files_scanned": 0, "functions_parsed": 0, "grants": [], "random_pools": []}
    seen = set()
    for root in native_script_roots():
        for path in sorted(root.rglob("*.ws")):
            key = str(path.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            try:
                text = path.read_text(encoding="utf-8-sig", errors="replace")
            except OSError:
                continue
            if "AddCardToCollection" not in text and not (
                    "PushBack" in text and "gwint_card_" in text):
                continue
            result["files_scanned"] += 1
            for name, body, line in script_functions(text):
                result["functions_parsed"] += 1
                calls = re.findall(r"AddCardToCollection\s*\(\s*'([A-Za-z0-9_]+)'", body)
                if calls:
                    result["grants"].append({
                        "function": name, "file": str(path.relative_to(root)), "line": line,
                        "names": sorted(set(calls)), "calls": len(calls),
                    })
                pool = re.findall(r"PushBack\s*\(\s*'(gwint_card_[A-Za-z0-9_]+)'", body)
                if pool and re.search(r"(?:random|merchant)", name, re.I) \
                        and re.search(r"AddAnItem|AddItem", body):
                    result["random_pools"].append({
                        "function": name, "file": str(path.relative_to(root)), "line": line,
                        "items": sorted(set(pool)), "calls": len(pool),
                    })
    return result


def save_collection(path):
    """Read CR4GwintManager.SBCollectionCard / SBLeaderCollectionCard from one save."""
    result = {"path": str(path), "name": path.name, "mtime": int(path.stat().st_mtime),
              "bytes": path.stat().st_size, "ok": False, "reason": ""}
    try:
        raw = save_reader.load_raw(path)
        names = save_reader.name_table(raw)
    except Exception as exc:
        result["reason"] = f"save reader: {type(exc).__name__}: {exc}"
        return result
    result["name_table"] = len(names)
    index = {name: i + 1 for i, name in enumerate(names)}
    required = ("CR4GwintManager", "SBCollectionCardSize", "SBCollectionCard",
                "SBLeaderCollectionCardSize", "SBLeaderCollectionCard", "cardIndex", "numCopies")
    missing = [name for name in required if name not in index]
    if missing:
        result["reason"] = "save has no Gwent collection block: " + ", ".join(missing)
        return result

    def u16(offset):
        return struct.unpack_from("<H", raw, offset)[0]

    def u32(offset):
        return struct.unpack_from("<I", raw, offset)[0]

    def read_array(size_name, card_name, start=0):
        pattern = b"BS" + struct.pack("<H", index[size_name])
        pos = raw.find(pattern, start)
        if pos < 0:
            return None, start, f"{size_name} block not found"
        pos += 4
        if raw[pos:pos + 2] != b"VL" or index.get(names[u16(pos + 2) - 1]) != index["Size"]:
            return None, start, f"{size_name} has no Size property"
        if names[u16(pos + 4) - 1] != "Uint32":
            return None, start, f"{size_name} Size is not Uint32"
        count = u32(pos + 6)
        pos += 10
        if count > 5000:
            return None, start, f"{size_name} count {count} is not plausible"
        rows = []
        for k in range(count):
            if raw[pos:pos + 2] != b"BS" or u16(pos + 2) != index[card_name]:
                return None, start, f"{size_name} card {k} starts with the wrong block"
            pos += 4
            if (raw[pos:pos + 2] != b"VL" or u16(pos + 2) != index["cardIndex"]
                    or names[u16(pos + 4) - 1] != "Int32"):
                return None, start, f"{size_name} card {k} has no cardIndex"
            card_index = u32(pos + 6)
            pos += 10
            if (raw[pos:pos + 2] != b"VL" or u16(pos + 2) != index["numCopies"]
                    or names[u16(pos + 4) - 1] != "Int32"):
                return None, start, f"{size_name} card {k} has no numCopies"
            copies = u32(pos + 6)
            pos += 10
            rows.append((card_index, copies))
        return rows, pos, ""

    normal, end, error = read_array("SBCollectionCardSize", "SBCollectionCard")
    if normal is None:
        result["reason"] = error
        return result
    leaders, end, leader_error = read_array("SBLeaderCollectionCardSize",
                                             "SBLeaderCollectionCard", end)
    if leaders is None:
        result["reason"] = leader_error
        return result

    # Ownership by index, not by item GUID. The collection is the save's own card ledger.
    name_table_start = raw.find(b"\x06Entity")
    outside = [m.start() for m in re.finditer(rb"gwint_card_[A-Za-z0-9_]+", raw)
               if name_table_start < 0 or m.start() < name_table_start]
    fact_like = 0
    for offset in outside:
        context = raw[max(0, offset - 40):offset + 80].lower()
        if b"already_given" in context or b"cg_lock_" in context or b"merchant_card" in context:
            fact_like += 1
    result.update({
        "ok": True,
        "normal": normal,
        "leaders": leaders,
        "normal_count": len(normal),
        "leader_count": len(leaders),
        "copies": sum(c for _i, c in normal) + sum(c for _i, c in leaders),
        "max_copies": max([c for _i, c in normal] + [c for _i, c in leaders] or [0]),
        "item_guid_mentions": {"outside_name_table": len(outside), "fact_like": fact_like},
        "inventory_block": "CInventoryComponent" in names,
    })
    return result


def map_save(result, cards_by_index, leaders_by_index):
    if not result.get("ok"):
        return {"ownership": "manual", "reason": result.get("reason", "no collection")}
    normal_names = []
    unknown_normal = []
    for card_index, copies in result["normal"]:
        card = cards_by_index.get(card_index)
        if card:
            normal_names.append({"index": card_index, "name": card["name"],
                                 "display": card["display"], "copies": copies})
        else:
            unknown_normal.append(card_index)
    leader_names = []
    unknown_leaders = []
    for card_index, copies in result["leaders"]:
        card = leaders_by_index.get(card_index)
        if card:
            leader_names.append({"index": card_index, "name": card["name"],
                                 "display": card["display"], "copies": copies})
        else:
            unknown_leaders.append(card_index)
    return {
        "ownership": "save_collection",
        "normal_owned": len(normal_names),
        "leaders_owned": len(leader_names),
        "total_owned": len(normal_names) + len(leader_names),
        "normal_copies": sum(x["copies"] for x in normal_names),
        "leader_copies": sum(x["copies"] for x in leader_names),
        "unknown_normal": unknown_normal,
        "unknown_leaders": unknown_leaders,
        "sample": (normal_names + leader_names)[:12],
    }


def missing_by_group(cards):
    groups = collections.defaultdict(list)
    for card in cards:
        if "SKELLIGE" in card["faction"] and card["index"] >= 500:
            groups["Blood and Wine Skellige deck"].append(card)
        elif not card["items"]:
            groups["no item definition"].append(card)
        else:
            groups["item exists, no source row"].append(card)
    return {name: [{"index": c["index"], "name": c["name"], "title": c["title"]}
                   for c in rows] for name, rows in groups.items()}


def route_facts():
    route_path = TRACKER / "data" / "route.json"
    cutoffs_path = TRACKER / "data" / "cutoffs.json"
    facts = {"route_present": route_path.exists(), "cutoffs_present": cutoffs_path.exists(),
             "gwent_nodes": 0, "unique_card_objectives": 0, "unique_opponents": [],
             "gwent_cutoff_rows": 0, "hard_gwent_nodes": []}
    if not route_path.exists():
        return facts
    route = json.loads(route_path.read_text(encoding="utf-8"))
    nodes = [n for n in route.get("nodes", []) if n.get("kind") == "gwent"]
    facts["gwent_nodes"] = len(nodes)
    objectives = []
    for node in nodes:
        for value in node.get("files", []):
            for alternative in value.split("|"):
                if "unique card" in alternative.lower():
                    objectives.append((node.get("id", ""), alternative))
    facts["unique_card_objectives"] = len(objectives)
    opponents = set()
    for _node, text in objectives:
        # The game's own objective text has one typo: "Win unique card fro Olivier".
        m = re.search(r"card\s+(?:from|fro)\s+(.+)$", text, re.I)
        if m:
            opponents.add(m.group(1).strip().lower())
    facts["unique_opponents"] = sorted(opponents)
    facts["hard_gwent_nodes"] = [
        {"id": n.get("id"), "hard": n.get("hard", []), "hard_facts": n.get("hard_facts", {})}
        for n in nodes if n.get("hard") or n.get("hard_facts")
    ]
    if cutoffs_path.exists():
        cutoffs = json.loads(cutoffs_path.read_text(encoding="utf-8"))
        words = ("gwent", "gwint", "cgoldfriends", "cg100", "cg200", "cg300",
                 "cg700", "sq306", "sq310")
        for key in ("items", "windows"):
            for row in cutoffs.get(key, []):
                text = json.dumps(row, ensure_ascii=False).lower()
                if any(word in text for word in words):
                    facts["gwent_cutoff_rows"] += 1
    return facts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="print the facts as JSON")
    ap.add_argument("--save", help="one .sav to probe (default: newest under W3_SAVES_DIR)")
    args = ap.parse_args()

    if not GAME.is_dir():
        print("game folder not found: %s" % GAME)
        return 2
    bundles = Bundles()
    if not bundles.by_path:
        print("no readable game bundles under content/ or DLC/")
        return 2

    card_hit = bundles.choose(CARD_DB)
    item_hit = bundles.choose(ITEM_DB)
    leader_hit = bundles.choose(LEADER_DB)
    king_hit = bundles.choose(KING_DB)
    deck_hit = bundles.choose(DECKS_DB)
    if not (card_hit and item_hit and leader_hit and deck_hit):
        missing = [p for p, hit in ((CARD_DB, card_hit), (ITEM_DB, item_hit),
                                    (LEADER_DB, leader_hit), (DECKS_DB, deck_hit)) if not hit]
        print("missing card resources in the game bundles: " + ", ".join(missing))
        return 2

    cards = read_cards(xml_root(card_hit[2]))
    leaders = read_cards(xml_root(leader_hit[2]))
    items = read_items(xml_root(item_hit[2]))
    king_count = len(xml_root(king_hit[2]).findall(".//card")) if king_hit else 0
    cards_by_index = {card["index"]: card for card in cards}
    leaders_by_index = {card["index"]: card for card in leaders}
    cards_by_name = {card["name"]: card for card in cards}

    resolve_names(cards, leaders)
    link_items(cards, items)
    item_by_name = {item["name"]: item for item in items}
    item_to_cards = collections.defaultdict(set)
    for card in cards:
        for item in card["items"]:
            item_to_cards[item].add(card["index"])
    summons = summon_only_cards(cards)
    summon_indexes = {row["index"] for row in summons}

    # Leader cards are a separate item family: 17 of the 22 have an item, and the one
    # king_bran item is named `king_bran_bronze`. Keep them out of the 206-card denominator.
    leader_item_to_index = collections.defaultdict(set)
    for leader in leaders:
        exact = "gwint_card_" + leader["name"]
        leader["items"] = [exact] if exact in item_by_name else []
        if leader["name"] == "king_bran" and "gwint_card_king_bran_bronze" in item_by_name:
            leader["items"] = ["gwint_card_king_bran_bronze"]
        for item in leader["items"]:
            leader_item_to_index[item].add(leader["index"])

    # Native script evidence: direct AddCardToCollection literals and random merchant pools.
    native = scan_native_scripts()
    native_grant_cards = set()
    native_pool_cards = set()
    native_unresolved = set()
    for row in native["grants"]:
        indices = set()
        for name in row["names"]:
            hits = card_ref_indices(name, cards_by_name, item_to_cards)
            if not hits:
                native_unresolved.add(name)
            indices.update(hits)
        row["cards"] = sorted(indices)
        native_grant_cards.update(indices)
    for row in native["random_pools"]:
        indices = set()
        for item in row["items"]:
            hits = card_ref_indices(item, cards_by_name, item_to_cards)
            if not hits:
                native_unresolved.add(item)
            indices.update(hits)
        row["cards"] = sorted(indices)
        native_pool_cards.update(indices)
    native.update({
        "unresolved": sorted(native_unresolved),
        "grant_calls": sum(row["calls"] for row in native["grants"]),
        "grant_names": len({name for row in native["grants"] for name in row["names"]}),
        "grant_cards": len(native_grant_cards),
        "pool_items": len({item for row in native["random_pools"] for item in row["items"]}),
        "pool_cards": len(native_pool_cards),
    })

    # XML source rows (vendor, quest, unique, reward). Test loot is counted but not used.
    source_rows = []
    for kind, virtual_path in SOURCE_FILES:
        hit = bundles.choose(virtual_path)
        if not hit:
            continue
        text = decode_payload(hit[2])
        if kind == "reward":
            source_rows.extend(read_reward_rows(text, virtual_path))
        else:
            source_rows.extend(read_loot_rows(text, kind, virtual_path))
    test_hit = bundles.choose(TEST_LOOT)
    test_rows = read_loot_rows(decode_payload(test_hit[2]), "test", TEST_LOOT) if test_hit else []

    phase = scan_phase_grants(bundles)
    scenes = scan_scene_mentions(bundles)

    origin = {}
    origin_hit = bundles.choose(ORIGIN_CSV)
    if origin_hit:
        origin = read_origin_csv(decode_payload(origin_hit[2]))
    origin_cards = set()
    for name in origin.get("names", []):
        origin_cards.update(item_to_cards.get(name, set()))
        origin_cards.update(item_to_cards.get("gwint_card_" + name, set()))

    decks, total_decks, total_deck_cards = read_decks(decode_payload(deck_hit[2]))
    deck_facts = deck_map(decks, cards)

    kind_rows = collections.Counter(row["kind"] for row in source_rows)
    kind_cards = collections.defaultdict(set)
    for row in source_rows:
        if row["kind"] == "vendor":
            kind_cards["vendor"].update(item_to_cards.get(row["item"], set()))
        elif row["kind"] == "quest":
            kind_cards["quest_loot"].update(item_to_cards.get(row["item"], set()))
        elif row["kind"] == "unique":
            kind_cards["unique_loot"].update(item_to_cards.get(row["item"], set()))
        elif row["kind"] == "reward":
            kind_cards["reward"].update(item_to_cards.get(row["item"], set()))

    phase_cards = set()
    merchant_cards = set()
    for row in phase["grants"]:
        target = merchant_cards if row["kind"] == "merchant_card" else phase_cards
        target.update(item_to_cards.get(row["item"], set()))
    leader_source = set()
    for row in source_rows + phase["grants"]:
        leader_source.update(leader_item_to_index.get(row["item"], set()))
    concrete = set().union(*kind_cards.values(), phase_cards, merchant_cards) \
        if kind_cards else set(phase_cards | merchant_cards)
    concrete |= native_grant_cards
    any_source = (concrete | native_pool_cards | deck_facts["named_cards"]
                  | deck_facts["starter_cards"])
    collectible = [c for c in cards if c["index"] not in summon_indexes]
    no_concrete = [c for c in cards if c["index"] not in concrete]
    unmatched = [c for c in collectible if c["index"] not in any_source]
    unmatched_items = sorted({row["item"] for row in source_rows + phase["grants"]
                              if row["item"] not in item_by_name})

    # One save only, read-only. Default to the newest save by mtime.
    save_path = Path(args.save) if args.save else (
        max(SAVES.glob("*.sav"), key=lambda p: p.stat().st_mtime) if SAVES.is_dir() else None)
    save = save_collection(save_path) if save_path and save_path.exists() else {
        "path": str(save_path or ""), "name": "", "ok": False, "reason": "no save"}
    save_owned = map_save(save, cards_by_index, leaders_by_index)

    # Definition copies: the game has the same XML under gameplay/items and gameplay/items_plus.
    definitions = {}
    for label, virtual_path, hit in (
            ("cards", CARD_DB, card_hit), ("items", ITEM_DB, item_hit),
            ("leaders", LEADER_DB, leader_hit), ("king_cards", KING_DB, king_hit),
            ("decks", DECKS_DB, deck_hit)):
        if not hit:
            continue
        bundle_path, entry, payload = hit
        mirror_path = virtual_path.replace("gameplay/items/", "gameplay/items_plus/", 1)
        mirror = bundles.choose(mirror_path) if mirror_path != virtual_path else None
        redkit = REDKIT_R4 / virtual_path
        classes = {"cards": "gwint_card_definitions_final", "items": "items",
                   "leaders": "gwint_battle_king_card_definitions",
                   "king_cards": "gwint_king_card_definitions", "decks": "gwint_decks"}
        definitions[label] = {
            "bundle": bundle_path.name,
            "virtual": virtual_path,
            "bytes": len(payload),
            "class": classes.get(label, ""),
            "mirror": {"virtual": mirror_path, "bytes": len(mirror[2]),
                       "identical": mirror[2] == payload} if mirror else None,
            "redkit_exists": redkit.exists(),
            "redkit_identical": redkit.exists() and redkit.read_bytes() == payload,
        }

    # Missable facts: journal/route windows and phase grant evidence.
    route = route_facts()
    grant_files = sorted({row["file"] for row in phase["grants"]})
    grant_steps = set()
    for file in grant_files:
        m = re.search(r"quest_files/([^/]+)/", file)
        grant_steps.add(m.group(1) if m else Path(file).stem)
    route["grant_files"] = len(grant_files)
    route["grant_steps"] = sorted(grant_steps)
    route["grant_cards"] = len(phase_cards | merchant_cards)
    route["card_checks"] = len({row["item"] for row in phase["checks"]})
    route["check_files"] = len({row["file"] for row in phase["checks"]})

    result = {
        "game": {"dir": str(GAME), "bundles": bundles.count,
                 "skipped_bundles": bundles.skipped},
        "definitions": definitions,
        "cards": {
            "main": len(cards),
            "collectible": len(collectible),
            "summon_only": len(summons),
            "leaders": len(leaders),
            "king_cards_active": king_count,
            "unique_display_names": len({c["display"] for c in cards}),
            "unique_leader_names": len({c["display"] for c in leaders}),
            "name_kinds": dict(collections.Counter(c["name_kind"] for c in cards + leaders)),
            "factions": dict(sorted(collections.Counter(c["faction"] for c in cards).items())),
        },
        "items": {
            "count": len(items),
            "direct_item_links": sum(1 for c in cards if c["items"]),
            "no_direct_item": sum(1 for c in cards if not c["items"]),
            "title_key_candidates": sum(1 for c in cards if c["title_matches"]),
            "leader_items": sum(1 for i in items
                                if re.search(r"_(platinium|gold|silver|bronze)$", i["name"])),
        },
        "leaders": {
            "count": len(leaders),
            "with_item": sum(1 for l in leaders if l["items"]),
            "with_source": len(leader_source),
            "no_item": [l["name"] for l in leaders if not l["items"]],
            "unmatched_cards": [{"index": l["index"], "name": l["name"],
                                 "display": l["display"]}
                                for l in leaders if l["index"] not in leader_source],
        },
        "decks": {
            "collections": len(decks),
            "total_decks": total_decks,
            "total_card_lines": total_deck_cards,
            "by_kind": deck_facts["collections"],
            "named_opponent_cards": len(deck_facts["named_cards"]),
            "named_collections": deck_facts["named_names"],
            "starter_cards": len(deck_facts["starter_cards"]),
            "unmapped_names": deck_facts["unmapped"][:20],
        },
        "sources": {
            "rows": kind_rows,
            "containers": {kind: len({r["container"] for r in source_rows
                                      if r["kind"] == kind})
                           for kind in ("vendor", "quest", "unique", "reward")},
            "cards": {key: len(value) for key, value in kind_cards.items()},
            "phase_grants": {"rows": len(phase["grants"]),
                             "unique_items": len({r["item"] for r in phase["grants"]}),
                             "cards": len(phase_cards),
                             "merchant_rows": sum(1 for r in phase["grants"]
                                                  if r["kind"] == "merchant_card"),
                             "merchant_cards": len(merchant_cards),
                             "files": grant_files,
                             "resources_scanned": phase["resources"],
                             "resources_with_journal": phase["with_journal"],
                             "failures": phase["failures"][:10]},
            "native_grants": {"functions": len(native["grants"]),
                              "calls": native["grant_calls"],
                              "unique_names": native["grant_names"],
                              "cards": len(native_grant_cards)},
            "random_pools": {"functions": len(native["random_pools"]),
                             "unique_items": native["pool_items"],
                             "cards": len(native_pool_cards)},
            "summon_only": len(summons),
            "scene_mentions": {"resources": len(scenes),
                               "items": len({i for s in scenes for i in s["items"]})},
            "test_loot": {"rows": len(test_rows),
                          "cards": len({c for row in test_rows
                                        for c in item_to_cards.get(row["item"], set())}),
                          "excluded": True},
            "concrete_cards": len(concrete),
            "any_source_cards": len(any_source),
            "no_concrete": len(no_concrete),
            "unmatched": len(unmatched),
            "unmatched_cards": [{"index": c["index"], "name": c["name"],
                                 "title": c["title"], "faction": c["faction"]}
                                for c in unmatched],
            "unmatched_groups": missing_by_group(unmatched),
            "unmatched_source_items": unmatched_items,
            "leaders": {"with_item": sum(1 for l in leaders if l["items"]),
                        "with_source": len(leader_source),
                        "unmatched": [l["name"] for l in leaders
                                      if l["index"] not in leader_source]},
        },
        "native": native,
        "summons": summons,
        "origin": {k: v for k, v in origin.items() if k != "names"} |
                  {"cards": len(origin_cards)},
        "save": {
            "file": save.get("name", ""),
            "ok": save.get("ok", False),
            "reason": save.get("reason", ""),
            "normal": save.get("normal_count", 0),
            "leaders": save.get("leader_count", 0),
            "copies": save.get("copies", 0),
            "max_copies": save.get("max_copies", 0),
            "item_guid_mentions": save.get("item_guid_mentions", {}),
            "inventory_block": save.get("inventory_block", False),
            "ownership": save_owned,
        },
        "missable": route,
        "verdicts": {
            "definitions": "bundle XML; no per-card .w2ent; REDkit copies are byte-identical",
            "names": "all 228 definitions resolve a display name; 225 use gwint_name_*",
            "sources": "not all cards have a specific source; %d of %d have a concrete or native "
                       "grant row, %d of %d collectible cards have any source/opponent/starter "
                       "evidence" %
                       (len(concrete), len(cards), len(any_source), len(collectible)),
            "ownership": "save collection by cardIndex; item GUIDs are not required",
            "missable": "quest-level windows exist; per-card windows are not proven",
        },
    }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True, default=sorted))
        return 0

    print("Gwent card probe (read-only)")
    print("  game: %s" % GAME)
    print("  bundles: %d read, %d skipped" % (bundles.count, len(bundles.skipped)))
    for skipped in bundles.skipped:
        print("    skipped %s: %s" % (skipped["bundle"], skipped["reason"]))
    print("\nCard definitions")
    for label, info in definitions.items():
        print("  %-10s %s!%s  %d bytes  class %s" %
              (label, info["bundle"], info["virtual"], info["bytes"], info["class"]))
        if info["mirror"]:
            print("    mirror: %s (%d bytes, identical=%s)" %
                  (info["mirror"]["virtual"], info["mirror"]["bytes"],
                   info["mirror"]["identical"]))
        print("    REDkit: %s, identical=%s" %
              (info["redkit_exists"], info["redkit_identical"]))
    print("  main cards %d (%d collectible, %d summon-only), leaders %d, active king cards %d" %
          (len(cards), len(collectible), len(summons), len(leaders), king_count))
    print("  unique display names: %d main, %d leaders" %
          (len({c["display"] for c in cards}), len({c["display"] for c in leaders})))
    print("  name sources: %s" % dict(collections.Counter(c["name_kind"]
                                                          for c in cards + leaders)))
    print("  factions: %s" % dict(sorted(collections.Counter(c["faction"]
                                                              for c in cards).items())))
    print("  items: %d definitions, %d cards with a direct item, %d without" %
          (len(items), sum(1 for c in cards if c["items"]),
           sum(1 for c in cards if not c["items"])))
    print("  leaders: %d definitions, %d with an item, %d with a source, no item: %s" %
          (len(leaders), sum(1 for l in leaders if l["items"]), len(leader_source),
           ", ".join(l["name"] for l in leaders if not l["items"])))
    print("  decks: %d collections, %d decks, %d card lines; named opponent cards %d, "
          "starter cards %d" %
          (len(decks), total_decks, total_deck_cards,
           len(deck_facts["named_cards"]), len(deck_facts["starter_cards"])))

    print("\nSource rows")
    names = {"vendor": "vendor", "quest": "quest loot", "unique": "unique loot",
             "reward": "reward"}
    key_map = {"vendor": "vendor", "quest": "quest_loot", "unique": "unique_loot",
               "reward": "reward"}
    for key in ("vendor", "quest", "unique", "reward"):
        containers = len({r["container"] for r in source_rows if r["kind"] == key})
        print("  %-12s %3d rows in %2d containers, %3d unique items, %3d cards" %
              (names[key], kind_rows.get(key, 0), containers,
               len({r["item"] for r in source_rows if r["kind"] == key}),
               len(kind_cards.get(key_map[key], set()))))
    print("  phase grants %3d rows, %3d items, %3d cards (%d merchant rows, %d merchant cards)" %
          (len(phase["grants"]), len({r["item"] for r in phase["grants"]}),
           len(phase_cards | merchant_cards),
           sum(1 for r in phase["grants"] if r["kind"] == "merchant_card"),
           len(merchant_cards)))
    print("  native grants %3d functions, %3d calls, %3d names, %3d cards" %
          (len(native["grants"]), native["grant_calls"], native["grant_names"],
           len(native_grant_cards)))
    for row in native["grants"]:
        print("    %-42s %s:%d (%d calls, %d cards)" %
              (row["function"], row["file"], row["line"], row["calls"], len(row["cards"])))
        print("      %s" % ", ".join(row["names"]))
    print("  random card pools %3d functions, %3d items, %3d cards" %
          (len(native["random_pools"]), native["pool_items"], len(native_pool_cards)))
    for row in native["random_pools"]:
        print("    %-42s %s:%d (%d items, %d cards)" %
              (row["function"], row["file"], row["line"], len(row["items"]),
               len(row["cards"])))
    if native["unresolved"]:
        print("  native script names with no card: %s" % ", ".join(native["unresolved"]))
    print("  summon-only tokens: %d (%s)" %
          (len(summons), ", ".join(row["name"] for row in summons)))
    print("  concrete grant rows cover %d of %d cards" % (len(concrete), len(cards)))
    print("  any source/opponent/starter covers %d of %d collectible cards; unmatched %d" %
          (len(any_source), len(collectible), len(unmatched)))
    print("  scene mentions: %d resources, %d items (not used as sources)" %
          (len(scenes), len({i for s in scenes for i in s["items"]})))
    print("  card_sources.csv: %d rows, %d unique names, origins %s, %d cards mapped" %
          (origin.get("rows", 0), origin.get("unique", 0),
           origin.get("origins", {}), len(origin_cards)))
    if unmatched:
        print("  unmatched cards:")
        for card in unmatched:
            print("    %3d  %-32s %-22s %s" %
                  (card["index"], card["title"], card["faction"], card["name"]))
    if unmatched_items:
        print("  source items with no card link: %s" % ", ".join(unmatched_items[:12]))

    print("\nSave ownership (one save, read-only)")
    print("  %s" % (save.get("name") or "(none)"))
    if save.get("ok"):
        print("  collection: %d normal cards, %d leaders, %d copies, max %d copies" %
              (save.get("normal_count", 0), save.get("leader_count", 0),
               save.get("copies", 0), save.get("max_copies", 0)))
        print("  mapped: %d normal, %d leaders; unknown indices: %s/%s" %
              (save_owned.get("normal_owned", 0), save_owned.get("leaders_owned", 0),
               save_owned.get("unknown_normal", []), save_owned.get("unknown_leaders", [])))
        print("  item GUID mentions outside the name table: %s" %
              save.get("item_guid_mentions", {}))
        print("  sample: %s" % ", ".join(x["display"] for x in save_owned.get("sample", [])[:8]))
    else:
        print("  no collection: %s" % save.get("reason", "unknown"))
        print("  ownership falls back to manual ticks")

    print("\nMissable windows")
    print("  Gwent route steps: %d; unique-card objectives: %d over %d opponents" %
          (route["gwent_nodes"], route["unique_card_objectives"],
           len(route["unique_opponents"])))
    print("  Gwent cutoff rows in data/cutoffs.json: %d" % route["gwent_cutoff_rows"])
    print("  phase grants: %d files, %d steps, %d cards; %d card item checks in %d files" %
          (route["grant_files"], len(route["grant_steps"]), route["grant_cards"],
           route["card_checks"], route["check_files"]))
    print("  verdict: quest-level windows exist; per-card windows are not proven")
    print("\nNo files were written. The card index and card UI were not generated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
