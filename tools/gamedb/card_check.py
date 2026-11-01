"""Cross-check the Gwent card sources against the game database.

For every card in data/gwent_cards.json this derives the sources that the raw game data shows
(shop and container loot tables, quest rewards, quest-graph grants, player decks and leader
defaults) and compares them with the reviewed source. The reviewed source is read, never
trusted as input to the database side.

Inputs (read only): data/gwent_cards.json, tools/card_sources.json, db/w3db.sqlite (mode=ro).
Output: docs/CARD-SOURCES-CHECK.md. Nothing else is written.

    py -3.15 tools/gamedb/card_check.py
"""
from __future__ import annotations

import collections
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GAMEDB_OUT = Path(os.environ.get("W3_GAMEDB_OUT") or (ROOT / "db"))
DB = GAMEDB_OUT / "w3db.sqlite"
CARDS = ROOT / "data" / "gwent_cards.json"
SOURCES = ROOT / "tools" / "card_sources.json"
OUT = ROOT / "docs" / "CARD-SOURCES-CHECK.md"

TOKEN = re.compile(r"gwint_card_[A-Za-z0-9_]+", re.I)
# Graph classes that test an item or a condition; a mention there is not a grant.
TEST_CLASSES = {"CQCHasItem", "W3QuestCond_IsItemQuantityMet", "CQuestConditionBlock",
                "CQuestPauseConditionBlock"}
TEST_LOOT_FILE = "def_loot_test"
# Decks that every player uses, not a named opponent: faction, AI difficulty, tutorial, tournament.
GENERIC_DECK = re.compile(
    r"^(North|Nilf|scotial|nml|ske|tutorialDeck|(NK|Nilf|Scoia|NML|Skel)"
    r"(Easy|Normal|Hard|Prologue|Tournament\d?))$", re.I)
# Reviewed kinds whose evidence is a .ws script or a game mechanism the database does not parse.
SCRIPT_KINDS = {"random_merchant", "collection_grant", "native_script"}


def prefix(deck: str) -> str:
    return re.split(r"[#@]", deck, maxsplit=1)[0]


def loot_kind(name: str) -> str:
    n = (name or "").lower()
    return "vendor" if (n.startswith("_store__") or "store" in n or "shop" in n) else "container"


def cell(text) -> str:
    return str(text if text is not None else "").replace("|", "/").replace("\n", " ")


def load_db():
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    con.row_factory = None
    d = {}
    d["files"] = dict(con.execute("select file_id, path from files"))
    d["known"] = set()
    d["items"] = {r[0].lower() for r in con.execute(
        "select distinct name from items where lower(name) like 'gwint_card%'")}
    d["known"] |= d["items"]
    d["loot"] = collections.defaultdict(list)
    for loot, item, fid, qmin, qmax, chance in con.execute(
            "select loot_name, item_name, file_id, quantity_min, quantity_max, chance "
            "from loot_entries where lower(item_name) like 'gwint_card%'"):
        d["loot"][item.lower()].append((loot, fid, qmin, qmax, chance))
    d["known"] |= set(d["loot"])
    d["reward"] = collections.defaultdict(list)
    for rname, item, amount in con.execute(
            "select reward_name, item_name, amount from reward_items "
            "where lower(item_name) like 'gwint_card%'"):
        d["reward"][item.lower()].append((rname, amount))
    d["known"] |= set(d["reward"])

    d["reward_blocks"] = collections.defaultdict(list)
    d["graph"] = collections.defaultdict(list)     # token -> graph mentions
    d["minigame_decks"] = collections.Counter()
    for fid, idx, cls, props in con.execute(
            "select file_id, idx, class, props_json from graph_nodes "
            "where props_json like '%gwint_card_%' or class in ('CQuestRewardBlock', 'CGwintMinigame')"):
        try:
            p = json.loads(props or "{}")
        except json.JSONDecodeError:
            p = {}
        if cls == "CQuestRewardBlock":
            d["reward_blocks"][p.get("rewardName")].append((fid, idx))
            continue
        if cls == "CGwintMinigame":
            d["minigame_decks"][p.get("deckName")] += 1
            continue
        if cls in TEST_CLASSES:
            continue
        note = {"class": cls, "fid": fid, "idx": idx,
                "function": p.get("functionName") or "", "comment": p.get("comment") or ""}
        for tok in {t.lower() for t in TOKEN.findall(props or "")}:
            d["graph"][tok].append(note)
    d["known"] |= set(d["graph"])

    d["gcards"] = collections.defaultdict(list)
    for ci, fid, attrs in con.execute("select card_index, file_id, attrs_json from gwent_cards"):
        d["gcards"][ci].append(json.loads(attrs or "{}"))
    d["decks"] = {}
    for dn, fid, leader, attrs in con.execute(
            "select deck_name, file_id, leader_index, attrs_json from gwent_decks"):
        d["decks"][dn] = (leader, json.loads(attrs or "{}"))
    d["deck_cards"] = collections.defaultdict(set)
    unresolved_deck_rows = 0
    for dn, ci in con.execute("select deck_name, card_index from gwent_deck_cards"):
        if ci is None:
            unresolved_deck_rows += 1
            continue
        d["deck_cards"][ci].add(prefix(dn))
    d["unresolved_deck_rows"] = unresolved_deck_rows

    d["file_quest"] = dict(con.execute("select file_id, quest_guid from file_quest"))
    d["jq"] = {g: (stem, loc, typ) for g, stem, loc, typ in con.execute(
        "select guid, stem, title_loc_id, type from journal_quests")}
    d["strings"] = {}
    for loc, text in con.execute("select loc_id, text from strings"):
        d["strings"].setdefault(loc, text)
    d["named_players"] = {prefix(dn) for dn in d["decks"] if not GENERIC_DECK.match(prefix(dn))}
    con.close()
    return d


def quest_label(d, fid) -> str:
    guid = d["file_quest"].get(fid)
    if not guid:
        return "no file_quest row"
    stem, loc, typ = d["jq"].get(guid, (None, None, None))
    if not stem:
        return f"quest {guid[:8]}"
    title = d["strings"].get(loc) if loc is not None else None
    return f"{stem} ({title})" if title else stem


def candidates(d, card):
    """Return (rule, [lower-case item names]) for the first rule that the database knows."""
    n = card["internal_name"]
    attr = ""
    for a in d["gcards"].get(card["index"], []):
        if a.get("item"):
            attr = a["item"]
            break
    rules = []
    if attr:
        rules.append(("item_attr", [attr]))
    rules.append(("internal_name", ["gwint_card_" + n]))
    if n.lower().endswith("gog"):
        rules.append(("gog_name", ["gwint_card_gog_" + n[:-3].lower()]))
    if n.endswith("_copper") and card["id"].startswith("leader_"):
        # The copper leader is the deck default. Its gwint_card_<base>_* siblings are the collectible
        # leader cards, which have their own rows, so copper takes no item sources of its own.
        return "deck_default_only", []
    for how, names in rules:
        hits = sorted({x.lower() for x in names if x.lower() in d["known"]})
        if hits:
            return how, hits
    return None, []


GRANT_FUNCTIONS = ("AddItem", "GiveSpecific")


def db_sources(d, card, names):
    """Database sources of one card, one record per distinct source."""
    out = collections.OrderedDict()
    mentions = collections.OrderedDict()

    def add(key, **kw):
        rec = out.setdefault(key, {"kind": key[0], "container": key[1], "files": set(),
                                   "quests": set(), "detail": set(), "fids": set()})
        for k, v in kw.items():
            if isinstance(v, (set, list)):
                rec[k].update(v)
            elif v is not None:
                rec[k].add(v)
        return rec

    test_loot = []
    removes = collections.OrderedDict()
    for name in names:
        for loot, fid, qmin, qmax, chance in d["loot"].get(name, []):
            path = d["files"].get(fid, "")
            if TEST_LOOT_FILE in path:
                test_loot.append((loot, path))
                continue
            kind = loot_kind(loot)
            add((kind, loot), files=[path], fids=[fid],
                detail=[f"{name} x{qmin}-{qmax} chance {chance}"])
        for rname, amount in d["reward"].get(name, []):
            blocks = d["reward_blocks"].get(rname, [])
            if not blocks:
                add(("reward_unplaced", rname), files=[], detail=[f"{name} in reward table, no reward block"])
            for fid, idx in blocks:
                add(("quest_reward", rname), files=[d["files"].get(fid, "")], fids=[fid],
                    quests=[quest_label(d, fid)], detail=[f"reward block in graph {fid}:{idx}"])
        for g in d["graph"].get(name, []):
            fn = g["function"]
            path = d["files"].get(g["fid"], "")
            quest = quest_label(d, g["fid"])
            if g["class"] == "CQuestScriptBlock" and fn.startswith("RemoveItem"):
                # A removal takes the card away; it is not a source.
                removes.setdefault(path, {"path": path, "quest": quest, "detail": set()})
                continue
            if g["class"] == "CQuestScriptBlock" and fn.startswith(GRANT_FUNCTIONS):
                add(("graph_ref", path), files=[path], fids=[g["fid"]], quests=[quest],
                    detail=[f"{fn}: {g['comment'] or name}"])
                continue
            # Fact writes and other blocks that name the item: shown, not counted as a source.
            mentions.setdefault(path, {"path": path, "quest": quest, "class": g["class"]})
    return out, test_loot, list(removes.values()), list(mentions.values())


def player_sources(d, card):
    """Named opponent decks that contain the card, and for leaders the deck they lead."""
    players = sorted(p for p in d["deck_cards"].get(card["index"], set()) if p in d["named_players"])
    leads = []
    if card["id"].startswith("leader_"):
        for dn, (leader, attrs) in d["decks"].items():
            if str(attrs.get("leaderCard", "")).lower() == card["internal_name"].lower():
                leads.append(prefix(dn))
    return players, sorted(set(leads))


def reviewed_matches(rkind, rcont, rfile, kind, cont) -> bool:
    """True when one database source is the reviewed source."""
    rc, cc = (rcont or "").lower(), (cont or "").lower()
    if rkind == "vendor":
        return kind == "vendor" and cc == rc
    if rkind in ("quest", "unique"):
        return kind == "container" and cc == rc
    if rkind == "reward":
        return kind in ("quest_reward", "reward_unplaced") and cc == rc
    if rkind in ("phase_grant", "merchant_card"):
        return kind == "graph_ref" and bool(rfile) and rfile.lower() == cc
    if rkind == "deck_default":
        return kind == "leader_deck"
    return False


def db_cell(r) -> str:
    """Counted sources, then the weak opponent-deck evidence in one short phrase."""
    parts = ["; ".join(fmt_source(rec) for _, _, rec in r["db"]) or "none"]
    for rm in r["removes"]:
        parts.append(f"removed by {rm['path']} / quest {rm['quest']} (not a source)")
    for mt in r["mentions"]:
        parts.append(f"named by a {mt['class']} in {mt['path']} / quest {mt['quest']} (not a grant)")
    if r["players"]:
        names = r["players"]
        shown = ", ".join(names[:6]) + (f" and {len(names) - 6} more" if len(names) > 6 else "")
        parts.append(f"opponent decks, weak and not a reward ({len(names)}): {shown}")
    return "; ".join(parts)


def file_tag(path: str) -> str:
    pack = "ep1" if path.startswith("dlc/ep1/") else "bob" if path.startswith("dlc/bob/") else "base"
    return f"{pack}/{'items_plus' if '/items_plus/' in path else 'items'}"


def fmt_source(rec) -> str:
    kind, cont = rec["kind"], rec["container"]
    if kind in ("vendor", "container"):
        tags = sorted({file_tag(f) for f in rec["files"] if f})
        bits = [f"{kind} {cont} [{', '.join(tags)}]"]
    elif kind == "graph_ref":
        bits = [f"graph {cont}"]
    elif kind == "player_deck":
        bits = [f"player deck {cont}"]
    else:
        bits = [f"{kind} {cont}"]
    if rec["quests"]:
        bits.append("quest " + "; ".join(sorted(rec["quests"])))
    return " | ".join(bits)


def run():
    t0 = time.time()
    cards = json.loads(CARDS.read_text(encoding="utf-8"))["cards"]
    reviewed_rows = json.loads(SOURCES.read_text(encoding="utf-8"))
    d = load_db()

    results = []
    mapped_by = collections.Counter()
    unmapped = []
    for card in cards:
        rule, names = candidates(d, card)
        if rule:
            mapped_by[rule] += 1
        else:
            unmapped.append(card)
        srcs, test_loot, removes, mentions = db_sources(d, card, names)
        players, leads = player_sources(d, card)
        # Opponent decks are weak evidence (card_sources.json: "opponent evidence, not a proven
        # reward"), so they are reported per card but are not counted as sources for the classes.
        # Only the copper leader's faction default decks (generic, not a named opponent) are the
        # deck-default evidence. Any other deck that a leader appears in is opponent evidence.
        is_copper = card["internal_name"].endswith("_copper")
        for p in leads:
            if is_copper and GENERIC_DECK.match(p):
                srcs[("leader_deck", p)] = {"kind": "leader_deck", "container": p, "files": set(),
                                            "quests": set(), "detail": set(), "fids": set()}
            else:
                players = sorted(set(players) | {f"leader in {p}"})
        sbase = card.get("source") or {}
        rkind = sbase.get("kind")
        rcont = sbase.get("container") or ""
        rfile = sbase.get("file") or ""
        rtext = sbase.get("text") or ""
        db_list = [(rec["kind"], rec["container"], rec) for rec in srcs.values()]
        matched = [x for x in db_list if reviewed_matches(rkind, rcont, rfile, x[0], x[1])]
        others = [x for x in db_list if x not in matched]
        if not db_list:
            cls = "no_db_source"
        elif rkind == "unknown":
            cls = "db_more"
        elif matched:
            cls = "db_more" if others else "agree"
        else:
            cls = "reviewed_only"
        results.append({"card": card, "class": cls, "rule": rule, "names": names,
                        "db": db_list, "test_loot": test_loot, "matched": matched, "players": players,
                        "removes": removes, "mentions": mentions,
                        "rkind": rkind, "rcont": rcont, "rfile": rfile, "rtext": rtext})

    ids = [r["card"]["id"] for r in results]
    assert len(ids) == len(set(ids)) == 224, "card count or ids not unique"
    counts = collections.Counter(r["class"] for r in results)
    assert sum(counts.values()) == 224

    player_stats = player_cross_reference(d, reviewed_rows, results)
    write_report(results, counts, mapped_by, unmapped, d, player_stats, time.time() - t0)

    print(f"runtime_seconds {time.time() - t0:.1f}")
    print(f"cards {len(results)} mapped {len(results) - len(unmapped)} unmapped {len(unmapped)}")
    print("mapping rules", dict(mapped_by))
    print("class counts", dict(counts))
    for cls in ("agree", "db_more", "reviewed_only", "no_db_source"):
        rows = [r for r in results if r["class"] == cls][:5]
        for r in rows:
            c = r["card"]
            print(f"example {cls}: {c['id']} | reviewed {r['rkind']} {r['rcont']} | db "
                  + "; ".join(fmt_source(rec) for _, _, rec in r["db"])[:300])
    print("wrote", OUT)


def player_cross_reference(d, reviewed_rows, results):
    stats = collections.Counter()
    missing = []
    for r in results:
        cid = r["card"]["id"]
        for row in reviewed_rows.get(cid, []) if isinstance(reviewed_rows, dict) else []:
            if row.get("kind") != "opponent_deck":
                continue
            stats["reviewed_player_rows"] += 1
            # A reviewed row can name several players, comma separated.
            for p in [x.strip() for x in (row.get("container") or "").split(",") if x.strip()]:
                stats["reviewed_player_names"] += 1
                if p in d["named_players"]:
                    stats["player_in_db_decks"] += 1
                    if p in d["deck_cards"].get(r["card"]["index"], set()):
                        stats["card_in_that_player_deck"] += 1
                    else:
                        stats["card_not_in_that_player_deck"] += 1
                else:
                    stats["player_not_in_db_decks"] += 1
                    missing.append((cid, p))
    stats["minigame_nodes"] = sum(d["minigame_decks"].values())
    stats["minigame_distinct_decks"] = len(d["minigame_decks"])
    stats["named_players_in_db"] = len(d["named_players"])
    named_in_reviewed = set()
    for row in (reviewed_rows.values() if isinstance(reviewed_rows, dict) else []):
        for x in row:
            if x.get("kind") == "opponent_deck":
                named_in_reviewed |= {y.strip() for y in (x.get("container") or "").split(",")}
    stats["db_players_unreviewed"] = len(d["named_players"] - named_in_reviewed)
    stats["unresolved_deck_rows"] = d["unresolved_deck_rows"]
    return {"stats": stats, "missing": missing}


def write_report(results, counts, mapped_by, unmapped, d, player_stats, runtime):
    L = []
    w = L.append
    total = len(results)
    windowed = [r for r in results if (r["card"].get("window") or {}).get("kind") != "none"]
    w("# Gwent card sources: database cross-check")
    w("")
    w("Status: audit only, generated by `tools/gamedb/card_check.py`. Nothing in `data/` or `tools/` "
      "is changed by this report. The proposed changes at the end are for the reviewer to accept or "
      "reject.")
    w("")
    w("## What was compared")
    w("")
    w("Each of the 224 cards in `data/gwent_cards.json` (202 main collectible cards, 22 leaders; the "
      "4 summon-only tokens are excluded there and here) was matched to the game database "
      "`db/w3db.sqlite` (opened read-only). The database sources are derived from the raw game data "
      "without using the reviewed `source` field. They are then compared with that reviewed source.")
    w("")
    w("Database sources counted for a card:")
    w("")
    w("- `vendor`: a `loot_entries` row for the card item in a loot table whose name starts with "
      "`_store__` or contains `store` or `shop`.")
    w("- `container`: any other loot table that holds the card item (quest card lockers, unique "
      "chests and so on).")
    w("- `quest_reward`: a `reward_items` row for the card item, and a `CQuestRewardBlock` in a quest "
      "graph that names that reward. `reward_unplaced` is a reward that no graph block uses.")
    w("- `graph_ref`: a non-test quest-graph node (for example a `CQuestScriptBlock` grant) whose "
      "properties or comment name the card item. Test and condition classes (`CQCHasItem`, "
      "`W3QuestCond_IsItemQuantityMet`, `CQuestConditionBlock`, `CQuestPauseConditionBlock`) are "
      "not sources.")
    w("- Opponent decks are not sources. A named opponent's deck that holds the card (deck name prefix "
      "before `#` in `gwent_deck_cards`) is reported per card as weak evidence, as `card_sources.json` "
      "itself labels it (\"opponent evidence, not a proven reward\"). Faction, AI difficulty, tutorial "
      "and tournament decks are generic and are not listed.")
    w("- `leader_deck`: for a copper leader only, the generic faction default deck whose `leaderCard` is "
      "that leader (the reviewed `deck_default`). A leader's appearance in a named opponent's deck is "
      "opponent evidence, like a player deck.")
    w("")
    w("Loot tables from the test file `def_loot_test.xml` are excluded from the sources and listed "
      "in the notes.")
    w("")
    w("## How cards were mapped to items")
    w("")
    w("The database has no card index on items. Each card's item name is found by trying these rules "
      "in order and taking the first that exists in the database (`items`, `loot_entries`, "
      "`reward_items` or a quest-graph literal):")
    w("")
    w("1. `item_attr`: the `item` attribute of the card's `gwent_cards` row, matched by `card_index` "
      "to the card's `index` in `data/gwent_cards.json`.")
    w("2. `internal_name`: `gwint_card_` plus the card's `internal_name`.")
    w("3. `gog_name`: for `...GOG` internal names, `gwint_card_gog_` plus the base name.")
    w("4. `deck_default_only`: the copper leader of each faction is the deck default. Its `gwint_card_<base>_*` "
      "siblings are the collectible leader cards, which have their own rows, so the copper leader takes "
      "only its deck-default evidence and no item sources.")
    w("")
    w("Mapping counts:")
    w("")
    w("| rule | cards |")
    w("|---|---:|")
    for rule in ("item_attr", "internal_name", "gog_name"):
        w(f"| {rule} | {mapped_by.get(rule, 0)} |")
    w(f"| deck_default_only (copper leaders, no item sources by design) | {mapped_by.get('deck_default_only', 0)} |")
    w(f"| not mapped (no item name in the database) | {len(unmapped)} |")
    w("")
    if unmapped:
        w("Cards with no item name in the database are listed in the Not resolved section. For them the "
          "database can still show a deck or a graph mention, but no shop, container or reward.")
        w("")
    w("## Counts per class")
    w("")
    w("| class | cards |")
    w("|---|---:|")
    for cls in ("agree", "db_more", "reviewed_only", "no_db_source"):
        w(f"| {cls} | {counts.get(cls, 0)} |")
    w(f"| total | {total} |")
    w("")
    w("Classes: `agree` means the reviewed source is among the database sources and nothing else is "
      "found. `db_more` means the reviewed source is confirmed (or the reviewed source is `unknown`) and "
      "the database shows more counted sources. `reviewed_only` means the reviewed "
      "source is not found in the database. `no_db_source` means the database finds nothing for the "
      "card at all.")
    w("")
    w("Opponent decks never move a card between classes; see the Gwent players section.")
    w("")
    w("Note on `unknown` reviewed sources: they are classed `db_more` when the database finds a source, "
      "because the database then supplies the source the review lacks. Their classification is a judgement "
      "and is marked in the table.")
    w("")
    w(f"Window kinds in `data/gwent_cards.json`: {len(windowed)} cards have a window other than `none` "
      f"({sum(1 for r in windowed if r['card']['window']['kind'] == 'one_time')} one_time and "
      f"{sum(1 for r in windowed if r['card']['window']['kind'] == 'missable')} missable). The brief "
      "asked for 18; the file has 18 one-time plus 14 missable, so all 32 are listed.")
    w("")

    def table(cls, title):
        rows = [r for r in results if r["class"] == cls]
        w(f"## {title} ({len(rows)})")
        w("")
        w("| card id | name | reviewed source | database sources | rule |")
        w("|---|---|---|---|---|")
        for r in rows:
            c = r["card"]
            rev = f"{r['rkind']}: {r['rtext']}" + (f" [{r['rcont']}]" if r["rcont"] else "")
            if r["rkind"] == "unknown":
                rev = "unknown (no concrete grant in the reviewed evidence)"
            dbs = db_cell(r)
            w(f"| `{c['id']}` | {cell(c['name'])} | {cell(rev)} | {cell(dbs)} | {r['rule'] or 'none'} |")
        w("")

    table("agree", "agree")
    table("db_more", "db_more")
    table("reviewed_only", "reviewed_only")
    table("no_db_source", "no_db_source")

    w("## Gwent players")
    w("")
    st = player_stats["stats"]
    w("The reviewed opponent-deck rows in `tools/card_sources.json` were checked against the database "
      "decks (`gwent_decks` deck names, prefix before `#`).")
    w("")
    w(f"- reviewed opponent-deck rows: {st['reviewed_player_rows']}, naming {st['reviewed_player_names']} "
      "player entries (some rows list several players)")
    w(f"- player entries found among database decks: {st['player_in_db_decks']}, of which the card is in "
      f"that player's deck: {st['card_in_that_player_deck']}, not in it: {st['card_not_in_that_player_deck']}")
    w(f"- player entries not found among database decks: {st['player_not_in_db_decks']}")
    w(f"- named player decks in the database: {st['named_players_in_db']}")
    w(f"- named player decks in the database that no reviewed row names: {st['db_players_unreviewed']}")
    w(f"- `CGwintMinigame` nodes: {st['minigame_nodes']} with {st['minigame_distinct_decks']} distinct "
      "deck names; these name AI difficulty decks, not players.")
    w(f"- `gwent_deck_cards` rows with no card index (name does not resolve): {st['unresolved_deck_rows']}")
    w("")
    if player_stats["missing"]:
        names = collections.Counter(p for _, p in player_stats["missing"])
        w("Player entries in the reviewed rows that the database does not list as a deck "
          "(entry: number of cards that name it):")
        w("")
        w(", ".join(f"{cell(p)} ({k})" for p, k in sorted(names.items())))
        w("")

    w("## One-time and missable cards (window.kind is not none)")
    w("")
    w("The card id is left out of this table on purpose so that every id appears once in the "
      "report. The `index` column identifies the card.")
    w("")
    w("| index | name | window | tier | step / event | reviewed source | database sources |")
    w("|---|---|---|---|---|---|---|")
    for r in sorted(windowed, key=lambda r: (r["card"]["window"]["kind"], r["card"]["index"])):
        c = r["card"]
        win = c["window"]
        ev = " / ".join(x for x in (win.get("step_title") or win.get("step"), win.get("event")) if x)
        dbs = db_cell(r)
        w(f"| {c['index']} | {cell(c['name'])} | {win['kind']} | {win.get('tier', '')} | {cell(ev)} | "
          f"{cell(r['rkind'])}: {cell(r['rcont'] or r['rtext'])} | {cell(dbs)} |")
    w("")

    w("## Proposed changes (for the reviewer; nothing applied)")
    w("")
    w("Only cards where a change is proposed are listed. Cards in `agree` and `no_db_source` need no "
      "change (the `no_db_source` cards are covered by the Not resolved section). Cards are named by "
      "their `index` and name, because the card id already appears in the class tables.")
    w("")
    n = 0
    for r in results:
        c = r["card"]
        cls = r["class"]
        ref = f"#{c['index']} {c['name']}"
        if cls == "reviewed_only":
            dbs = "; ".join(fmt_source(rec) for _, _, rec in r["db"])
            if r["rkind"] in SCRIPT_KINDS:
                action = (f"the reviewed {r['rkind']} source is a script the database does not parse; "
                          f"the database shows a concrete source to set in its place or add: {dbs}")
            else:
                action = f"reviewed {r['rkind']} source is not in the database; choose between it and: {dbs}"
        elif cls == "db_more":
            matched_recs = [m[2] for m in r["matched"]]
            others = [rec for _, _, rec in r["db"] if rec not in matched_recs]
            if r["rkind"] == "unknown":
                action = "reviewed source is unknown; set it to the database source(s): " +                     "; ".join(fmt_source(rec) for rec in others)
            else:
                action = "add the extra counted source(s): " + "; ".join(fmt_source(rec) for rec in others)
        else:
            continue
        n += 1
        w(f"{n}. {ref} ({cls}): {action}.")
    w("")

    w("## Not resolved")
    w("")
    if unmapped:
        w("Cards with no item name found in the database (no shop, container or reward could be searched "
          "for them; a REDkit check of the item name is the next step):")
        w("")
        for card in unmapped:
            w(f"- #{card['index']} {card['name']} (internal name `{card['internal_name']}`)")
        w("")
    tl = collections.Counter()
    for r in results:
        for loot, path in r["test_loot"]:
            tl[(loot, path)] += 1
    if tl:
        w("Test loot tables excluded from the sources (card-to-row matches):")
        w("")
        for (loot, path), k in tl.items():
            w(f"- `{loot}` in `{path}` ({k} card-to-row matches)")
        w("")
    w("Scripts (`.ws`) are not parsed by the database. Reviewed sources that point at a script "
      "(random merchant, collection grant, native script) can therefore be classed `reviewed_only` "
      "without the source being wrong.")
    w("")
    w(f"Runtime of the check: {runtime:.1f} seconds.")
    w("")

    text = "\n".join(L) + "\n"
    seen = collections.Counter(re.findall(r"`((?:card|leader)_[A-Za-z0-9_]+)`", text))
    for r in results:
        if seen[r["card"]["id"]] != 1:
            raise SystemExit(f"card id {r['card']['id']} appears {seen[r['card']['id']]} times in the report")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    sys.exit(run())
