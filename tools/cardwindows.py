"""Build and check the reviewed card-window matrix.

Every shipped card gets exactly one window classification:

* ``missable`` - a reviewed closing window with a route step and a mechanism. A Tier B
  (``tier: community``) row must name a source, a URL where available and a review date.
* ``one_time`` - a gamefile one-time source with a route step, but no reviewed failure branch.
  It is a window, not a hard ``LOST`` claim.
* ``none`` - a documented no-window reason: a persistent source, an automatic grant, a one-time
  source with no single route step, or an explicit unknown source.

The reviewed decisions live in ``data/card_window_review.json``. Everything else is derived from
the generated source rows in ``tools/card_sources.json``; the generated report is
``data/card_windows.json``. ``cards.py build`` attaches the same rows to every card so the app has
one payload, and this checker fails if the two files disagree or if any of the 224 cards is
unaccounted for.

  py cardwindows.py build     rebuild the report and re-attach it to gwent_cards.json
  py cardwindows.py check     fail on a missing card, a bad Tier B source, a category-only
                              no-window reason, or a bare window count
"""
import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import HERE, TRACKER

CARDS = TRACKER / "data" / "gwent_cards.json"
# Source rows are provenance, kept beside the builder; the shipped ledger keeps only the primary row.
SOURCES = HERE / "card_sources.json"
USE_SOURCES = None
_PROVENANCE = None
REVIEW = TRACKER / "data" / "card_window_review.json"
OUT = TRACKER / "data" / "card_windows.json"
ROUTE = TRACKER / "data" / "route.json"

PERSISTENT = {"vendor", "random_merchant", "deck_default", "collection_grant"}
# A deck list says a card can appear in a deck; it does not say the player owns it. These rows
# are evidence, never a persistent source, and a no-window row may not rest on them alone.
DECK_ONLY = {"deck_definition", "opponent_deck"}
ONE_TIME = {"phase_grant", "quest", "unique", "reward", "merchant_card", "native_script"}
SOURCE_PRIORITY = {
    "phase_grant": 0,
    "quest": 1,
    "reward": 2,
    "merchant_card": 3,
    "unique": 4,
    "native_script": 5,
}
TIER_RANK = {"gamefile": "A", "community": "B", "unknown": "C"}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PLACEHOLDERS = ("<", ">", "TODO", "TBD", "FIXTURE")

_FACTS = None


def _known_facts():
    """Every fact the game's own script index names, so reviewed gates cannot invent one."""
    global _FACTS
    if _FACTS is None:
        path = HERE / "fact_index.json"
        _FACTS = ({row.get("fact") for row in load_json(path) if isinstance(row, dict) and row.get("fact")}
                  if path.exists() else set())
    return _FACTS


class DuplicateKey(ValueError):
    pass


def _no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKey(f"duplicate object key {key!r}")
        out[key] = value
    return out


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=_no_duplicates)


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def route_titles():
    if not ROUTE.exists():
        return {}
    return {node["id"]: node.get("title", node["id"])
            for node in load_json(ROUTE).get("nodes", [])
            if isinstance(node, dict) and node.get("id")}


def load_review(path=REVIEW):
    review = load_json(path)
    if not isinstance(review, dict):
        raise SystemExit(f"{path}: must be a JSON object")
    if not isinstance(review.get("sources"), dict):
        raise SystemExit(f"{path}: sources must be an object")
    if not isinstance(review.get("cards"), dict):
        raise SystemExit(f"{path}: cards must be an object")
    return review


def _source(review, value):
    if isinstance(value, dict):
        source = dict(value)
    else:
        source = review["sources"].get(value)
        if not isinstance(source, dict):
            raise SystemExit(f"review names an unknown source {value!r}")
        source = dict(source)
    for key in ("name", "url", "reviewed"):
        if not isinstance(source.get(key), str) or not source[key].strip():
            raise SystemExit(f"review source is missing {key}: {source!r}")
    if not source["url"].startswith(("http://", "https://")):
        raise SystemExit(f"review source URL is not resolvable: {source['url']!r}")
    if not DATE.fullmatch(source["reviewed"]):
        raise SystemExit(f"review source date is not YYYY-MM-DD: {source['reviewed']!r}")
    return source


def _evidence(row):
    out = []
    for key, kind in (("file", "file"), ("function", "function"), ("line", "line"),
                      ("container", "container")):
        value = row.get(key)
        if value not in (None, ""):
            out.append({"kind": kind, "value": str(value)})
    return out


def sources_for(card):
    """The card's provenance rows: the freshly built map, then the shipped ledger, then tools/."""
    global _PROVENANCE
    if USE_SOURCES is not None:
        return USE_SOURCES.get(card.get("id")) or []
    rows = card.get("sources")
    if isinstance(rows, list) and rows:
        return rows
    if _PROVENANCE is None:
        _PROVENANCE = load_json(SOURCES) if SOURCES.exists() else {}
    return _PROVENANCE.get(card.get("id")) or []


def _source_kinds(card):
    return {row.get("kind") for row in sources_for(card) if isinstance(row, dict)}


def _step_row(card):
    rows = [row for row in sources_for(card)
            if isinstance(row, dict) and row.get("kind") in ONE_TIME and row.get("step")]
    if not rows:
        return None
    return sorted(rows, key=lambda row: (SOURCE_PRIORITY.get(row.get("kind"), 99),
                                         str(row.get("step")), str(row.get("file", ""))))[0]


def _source_refs(card):
    """The concrete source rows this no-window decision was checked against."""
    refs = []
    for row in sources_for(card):
        if not isinstance(row, dict) or not row.get("kind"):
            continue
        ref = {"kind": str(row["kind"])}
        for key in ("text", "file", "function", "container", "step", "confidence"):
            value = row.get(key)
            if value not in (None, ""):
                ref[key] = str(value)
        if len(ref) > 1:
            refs.append(ref)
    if not refs:
        source = card.get("source") if isinstance(card.get("source"), dict) else {}
        if source.get("kind"):
            ref = {"kind": str(source["kind"])}
            for key in ("text", "file", "function", "container", "step"):
                value = source.get(key)
                if value not in (None, ""):
                    ref[key] = str(value)
            refs.append(ref)
    if not refs:
        refs.append({"kind": "unknown", "text": "no concrete source row exists"})
    return refs


def _representative(refs):
    for ref in refs:
        if ref.get("kind") != "opponent_deck" and any(
                ref.get(key) for key in ("text", "file", "function", "container", "step")):
            return ref
    return refs[0]


def _ref_label(ref):
    label = ref.get("text") or ref.get("function") or ref.get("container") or ref.get("kind", "source")
    if ref.get("file"):
        label += f" ({ref['file']})"
    return label


def _no_window_reason(card):
    refs = _source_refs(card)
    kinds = sorted(k for k in _source_kinds(card) if k)
    sample = _ref_label(_representative(refs))
    count = len(refs)
    if "unknown" in kinds:
        return (f"Checked {count} source row(s), including {sample}; no concrete source row "
                "exists, so no journal phase or failure can be attached.")
    if set(kinds) <= DECK_ONLY:
        return (f"Checked {count} source row(s), including {sample}; a deck definition or opponent "
                "deck is not ownership, and no collection grant, phase grant or journal failure "
                "closes this card.")
    if set(kinds) & PERSISTENT:
        return (f"Checked {count} source row(s), including {sample}; the source remains "
                "available after every route step, and no phase grant or journal failure "
                "closes this card.")
    functions = {row.get("function") for row in sources_for(card)
                 if isinstance(row, dict) and row.get("kind") == "native_script"}
    if functions & {"UnlockSkelligeGwentDeck", "OnGwintSetupNewgame"}:
        return (f"Checked {count} source row(s), including {sample}; the collection is filled "
                "automatically when the deck is unlocked, so no journal phase or failure "
                "closes it.")
    if "merchant_card" in kinds:
        return (f"Checked {count} source row(s), including {sample}; the merchant stock "
                "remains available, so no journal phase or failure closes it.")
    return (f"Checked {count} source row(s), including {sample}; the grant has no single "
            "reviewed route step, and no journal failure or phase condition closes it.")


def _reviewed_window(card_id, row, review, titles):
    tier = row.get("tier")
    if tier not in TIER_RANK:
        raise SystemExit(f"{card_id}: review tier must be gamefile, community or unknown")
    kind = row.get("kind")
    if kind not in ("missable", "one_time", "none"):
        raise SystemExit(f"{card_id}: review kind must be missable, one_time or none")
    window = {
        "kind": kind,
        "tier": tier,
        "tier_rank": TIER_RANK[tier],
        "reviewed": review.get("reviewed"),
    }
    if kind == "missable":
        for key in ("step", "event", "mechanism"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise SystemExit(f"{card_id}: a missable row needs {key}")
        window.update({
            "step": row["step"],
            "step_title": titles.get(row["step"], row["step"]),
            "event": row["event"],
            "mechanism": row["mechanism"],
        })
        if tier == "community":
            window["source"] = _source(review, row.get("source"))
        elif tier != "gamefile":
            raise SystemExit(f"{card_id}: a missable row is either gamefile or community")
    elif kind == "one_time":
        for key in ("step", "event", "mechanism"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise SystemExit(f"{card_id}: a one_time row needs {key}")
        window.update({
            "step": row["step"],
            "step_title": titles.get(row["step"], row["step"]),
            "event": row["event"],
            "mechanism": row["mechanism"],
        })
    else:
        reason = row.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise SystemExit(f"{card_id}: a none row needs a reason")
        window["reason"] = reason
    evidence = row.get("evidence")
    if evidence is None:
        evidence = []
    if not isinstance(evidence, list):
        raise SystemExit(f"{card_id}: evidence must be a list")
    for item in evidence:
        if not isinstance(item, dict) or not item.get("kind") or item.get("value") in (None, ""):
            raise SystemExit(f"{card_id}: evidence rows need kind and value")
    window["evidence"] = evidence
    if kind in ("missable", "one_time"):
        # Every window names the step that opens it. Without one it is ledger-only; the checker
        # refuses a band claim that cannot say when the player can act on it.
        opens = row.get("opens")
        window["opens"] = dict(opens) if isinstance(opens, dict) else {"step": row["step"]}
        if row.get("fallback") is not None:
            window["fallback"] = row["fallback"]
    return window


def _auto_window(card, titles):
    kinds = _source_kinds(card)
    if "unknown" in kinds:
        return {
            "kind": "none",
            "tier": "unknown",
            "tier_rank": "C",
            "reason": _no_window_reason(card),
            "evidence": [{"kind": "file", "value": card["source"].get("file", "")}],
        }
    if kinds & PERSISTENT:
        files = sorted({row.get("file") for row in sources_for(card)
                        if isinstance(row, dict) and row.get("kind") in PERSISTENT
                        and row.get("file")})
        return {
            "kind": "none",
            "tier": "gamefile",
            "tier_rank": "A",
            "reason": _no_window_reason(card),
            "evidence": [{"kind": "file", "value": value} for value in files],
        }
    row = _step_row(card)
    if row:
        return {
            "kind": "one_time",
            "tier": "gamefile",
            "tier_rank": "A",
            "step": row["step"],
            "step_title": titles.get(row["step"], row["step"]),
            "event": "The one-time source passes",
            "mechanism": row.get("text", "One-time gamefile source."),
            "evidence": _evidence(row),
            "opens": {"step": row["step"]},
        }
    return {
        "kind": "none",
        "tier": "gamefile",
        "tier_rank": "A",
        "reason": _no_window_reason(card),
        "evidence": [{"kind": "file", "value": Path(row.get("file", "")).name}
                     for row in sources_for(card)
                     if isinstance(row, dict) and row.get("file")],
    }


def build_windows(doc, review=None, titles=None):
    review = review or load_review()
    titles = titles if titles is not None else route_titles()
    cards = doc.get("cards") if isinstance(doc, dict) else None
    if not isinstance(cards, list):
        raise SystemExit("gwent_cards.json has no cards list")
    ids = {card.get("id") for card in cards if isinstance(card, dict)}
    unknown = sorted(set(review["cards"]) - ids)
    if unknown:
        raise SystemExit("review names cards that are not in gwent_cards.json: " + ", ".join(unknown))
    windows = {}
    for card in cards:
        if not isinstance(card, dict) or not card.get("id"):
            raise SystemExit("gwent_cards.json has a malformed card row")
        cid = card["id"]
        if cid in review["cards"]:
            windows[cid] = _reviewed_window(cid, review["cards"][cid], review, titles)
        else:
            windows[cid] = _auto_window(card, titles)
        if windows[cid].get("kind") == "none":
            windows[cid]["sources_checked"] = _source_refs(card)
    return windows


def summarize(windows):
    kinds = collections.Counter(row["kind"] for row in windows.values())
    tiers = collections.Counter(row["tier_rank"] for row in windows.values())
    return {
        "total": len(windows),
        "missable": kinds.get("missable", 0),
        "missable_tier_a": sum(1 for row in windows.values()
                               if row["kind"] == "missable" and row["tier_rank"] == "A"),
        "missable_tier_b": sum(1 for row in windows.values()
                               if row["kind"] == "missable" and row["tier_rank"] == "B"),
        "one_time": kinds.get("one_time", 0),
        "none": kinds.get("none", 0),
        "tier_a": tiers.get("A", 0),
        "tier_b": tiers.get("B", 0),
        "tier_c": tiers.get("C", 0),
        "community": sum(1 for row in windows.values() if row.get("tier") == "community"),
    }


def attach(doc, review=None, titles=None):
    windows = build_windows(doc, review, titles)
    for card in doc.get("cards") or []:
        card["window"] = windows[card["id"]]
    counts = summarize(windows)
    old = doc.get("counts") if isinstance(doc.get("counts"), dict) else {}
    old.update({
        "missable": counts["missable"],
        "windows": counts,
        "unknown_source": sum(1 for card in doc.get("cards") or []
                              if card.get("source", {}).get("kind") == "unknown"),
    })
    doc["counts"] = old
    doc["missable_windows"] = {
        "proven": False,
        "reviewed": True,
        "tier_a": counts["tier_a"],
        "tier_b": counts["tier_b"],
        "tier_c": counts["tier_c"],
        "missable": counts["missable"],
        "one_time": counts["one_time"],
        "none": counts["none"],
        "note": ("No Tier A card-level deadline is proven. %d Tier B community-reviewed windows "
                 "are labelled in the UI; every other card has a one-time or documented "
                 "no-window reason." % counts["tier_b"]),
    }
    return doc


def report_doc(doc, review=None, titles=None):
    windows = build_windows(doc, review, titles)
    by_id = {card["id"]: card for card in doc["cards"]}
    rows = []
    for cid in sorted(windows):
        card = by_id[cid]
        row = {
            "id": cid,
            "name": card.get("name"),
            "pack": card.get("pack"),
            "collection": card.get("collection"),
            "source_kind": (card.get("source") or {}).get("kind"),
            "source_text": (card.get("source") or {}).get("text"),
        }
        row.update(windows[cid])
        rows.append(row)
    return {
        "version": 1,
        "classification": "static-window-classification",
        "ownership": {
            "in_artifact": False,
            "source": "CR4GwintManager.SBCollectionCard / SBLeaderCollectionCard",
            "runtime_payload": "get_cards / --cards",
            "note": ("This report classifies windows only. Per-save ownership is added at "
                     "runtime and is never inferred here."),
        },
        "reviewed": (review or load_review()).get("reviewed"),
        "note": ("Generated by tools/cardwindows.py. One row per shipped card: a reviewed "
                 "missable/one-time window or a documented no-window reason with its checked "
                 "sources. Tier B rows carry a named source, URL and review date and are "
                 "visibly labelled in the UI."),
        "counts": dict(summarize(windows), unknown_source=sum(
            1 for card in doc.get("cards") or []
            if (card.get("source") or {}).get("kind") == "unknown")),
        "cards": rows,
    }


def _validate_window(card, window, route_ids, errors):
    cid = card.get("id", "?")
    if not isinstance(window, dict):
        errors.append(f"{cid}: window is not an object")
        return
    kind = window.get("kind")
    tier = window.get("tier")
    rank = window.get("tier_rank")
    if kind not in ("missable", "one_time", "none"):
        errors.append(f"{cid}: window.kind is {kind!r}")
    if tier not in TIER_RANK:
        errors.append(f"{cid}: window.tier is {tier!r}")
    if rank != TIER_RANK.get(tier):
        errors.append(f"{cid}: window.tier_rank does not match tier")
    if kind in ("missable", "one_time"):
        step = window.get("step")
        if not isinstance(step, str) or step not in route_ids:
            errors.append(f"{cid}: window step {step!r} is not a route node")
        for key in ("event", "mechanism"):
            if not isinstance(window.get(key), str) or not window[key].strip():
                errors.append(f"{cid}: window needs {key}")
        if not isinstance(window.get("evidence"), list) or not window["evidence"]:
            errors.append(f"{cid}: window needs evidence")
        opens = window.get("opens")
        if not isinstance(opens, dict):
            errors.append(f"{cid}: a window needs opens (a step that opens it)")
        else:
            gate = opens.get("step")
            if not isinstance(gate, str) or gate not in route_ids:
                errors.append(f"{cid}: opens.step {gate!r} is not a route node")
            requires = opens.get("requires", [])
            if not isinstance(requires, list):
                errors.append(f"{cid}: opens.requires must be a list")
            else:
                for cond in requires:
                    if not isinstance(cond, dict) or cond.get("kind") not in ("fact", "item", "step"):
                        errors.append(f"{cid}: an opens condition needs kind fact, item or step")
                        continue
                    value = cond.get("value")
                    if not isinstance(value, str) or not value.strip():
                        errors.append(f"{cid}: an opens condition needs a value")
                    elif cond["kind"] == "fact" and value not in _known_facts():
                        errors.append(f"{cid}: opens condition {value!r} is not a real fact")
                    elif cond["kind"] == "step" and value not in route_ids:
                        errors.append(f"{cid}: opens condition step {value!r} is not a route node")
        fallback = window.get("fallback")
        if fallback is not None:
            if not isinstance(fallback, list) or not fallback:
                errors.append(f"{cid}: fallback must be a non-empty list when present")
            else:
                for row in fallback:
                    if not isinstance(row, dict) or not row.get("kind") or row.get("value") in (None, ""):
                        errors.append(f"{cid}: fallback rows need kind and value")
    if kind == "missable" and tier == "community":
        source = window.get("source")
        if not isinstance(source, dict):
            errors.append(f"{cid}: a community window needs a source")
        else:
            for key in ("name", "url", "reviewed"):
                if not isinstance(source.get(key), str) or not source[key].strip():
                    errors.append(f"{cid}: community source needs {key}")
            if not str(source.get("url", "")).startswith(("http://", "https://")):
                errors.append(f"{cid}: community source URL is not http(s)")
            if not DATE.fullmatch(str(source.get("reviewed", ""))):
                errors.append(f"{cid}: community source review date is not YYYY-MM-DD")
    if kind == "none":
        # A phase or quest grant with a route step is a one-time source. Hiding it under a
        # no-window row is the Dijkstra bug: the ledger would say the card never closes while a
        # real quest phase hands it out.
        step_sources = [row for row in sources_for(card)
                        if isinstance(row, dict) and row.get("kind") in ONE_TIME and row.get("step")]
        if step_sources:
            errors.append(f"{cid}: a no-window row hides a one-time source "
                          f"({step_sources[0].get('kind')} in {step_sources[0].get('step')})")
        kinds = _source_kinds(card)
        if tier != "unknown" and kinds and kinds <= DECK_ONLY:
            errors.append(f"{cid}: a deck definition is not a persistent source; use the "
                          "unknown-source row unless a collection grant exists")
        reason = window.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"{cid}: a no-window row needs a reason")
        refs = window.get("sources_checked")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{cid}: a no-window row needs sources_checked")
        else:
            values = []
            for ref in refs:
                if not isinstance(ref, dict) or not ref.get("kind"):
                    errors.append(f"{cid}: sources_checked rows need a kind")
                    continue
                concrete = [ref.get(key) for key in ("text", "file", "function", "container", "step")
                            if ref.get(key)]
                if not concrete:
                    errors.append(f"{cid}: sources_checked row {ref.get('kind')!r} has no source detail")
                values.extend(str(value).lower() for value in concrete)
            if isinstance(reason, str) and reason.strip() and values:
                if not any(value in reason.lower() for value in values):
                    errors.append(f"{cid}: a no-window reason must name a specific checked "
                                  "source, not only a category")
        if tier == "unknown" and (card.get("source") or {}).get("kind") != "unknown":
            errors.append(f"{cid}: only an unknown source may use the Tier C no-window row")
        if tier == "gamefile" and (card.get("source") or {}).get("kind") == "unknown":
            errors.append(f"{cid}: an unknown source was labelled gamefile")
    for value in window.values():
        if isinstance(value, str) and any(token in value for token in PLACEHOLDERS):
            errors.append(f"{cid}: window contains a placeholder")
            break


def validate(doc, report, review, route_ids):
    errors, warnings = [], []
    if not isinstance(doc, dict) or not isinstance(doc.get("cards"), list):
        return ["gwent_cards.json has no cards list"], warnings
    if not isinstance(report, dict) or not isinstance(report.get("cards"), list):
        return ["card_windows.json has no cards list"], warnings
    if report.get("classification") != "static-window-classification":
        errors.append("card_windows.json must declare classification: static-window-classification")
    ownership = report.get("ownership")
    if not isinstance(ownership, dict) or ownership.get("in_artifact") is not False:
        errors.append("card_windows.json must declare ownership.in_artifact: false")
    elif not ownership.get("source"):
        errors.append("card_windows.json must name the runtime ownership source")
    cards = doc["cards"]
    rows = report["cards"]
    if len(cards) != 224:
        errors.append(f"gwent_cards.json has {len(cards)} cards, expected the 224 baseline")
    ids = [card.get("id") for card in cards if isinstance(card, dict)]
    if len(ids) != len(set(ids)):
        errors.append("gwent_cards.json has duplicate card ids")
    report_ids = [row.get("id") for row in rows if isinstance(row, dict)]
    if len(report_ids) != len(set(report_ids)):
        errors.append("card_windows.json has duplicate card ids")
    missing = sorted(set(ids) - set(report_ids))
    extra = sorted(set(report_ids) - set(ids))
    if missing:
        errors.append("cards missing a window row: " + ", ".join(missing))
    if extra:
        errors.append("window rows for cards that are not shipped: " + ", ".join(extra))
    by_id = {row.get("id"): row for row in rows if isinstance(row, dict)}
    windows = {}
    for card in cards:
        if not isinstance(card, dict):
            errors.append("gwent_cards.json has a malformed card")
            continue
        cid = card.get("id")
        window = card.get("window")
        if not isinstance(window, dict):
            errors.append(f"{cid}: card has no window classification")
            continue
        _validate_window(card, window, route_ids, errors)
        windows[cid] = window
        report_row = by_id.get(cid)
        if report_row is None:
            continue
        reported = {key: value for key, value in report_row.items()
                    if key not in ("id", "name", "pack", "collection", "source_kind", "source_text")}
        if reported != window:
            errors.append(f"{cid}: gwent_cards.json and card_windows.json disagree")
    counts = report.get("counts") if isinstance(report.get("counts"), dict) else {}
    expected = summarize(windows)
    for key, value in expected.items():
        if counts.get(key) != value:
            errors.append(f"report counts.{key} is {counts.get(key)!r}, expected {value}")
    if counts.get("missable", 0) <= 0:
        errors.append("no reviewed missable window: a bare zero is not completion")
    if counts.get("total") != 224:
        errors.append(f"window denominator is {counts.get('total')}, expected 224")
    packs = collections.Counter(card.get("pack") for card in cards)
    if packs.get("base") != 196 or packs.get("bob") != 28 or packs.get("ep1", 0) != 0:
        errors.append(f"pack split is {dict(packs)}, expected base 196, bob 28, ep1 0")
    if sum(1 for card in cards if card.get("collection") == "leader") != 22:
        errors.append("leader split is not 22")
    for cid, window in windows.items():
        if window.get("tier") == "community":
            source = window.get("source") or {}
            if not source.get("url") or not DATE.fullmatch(str(source.get("reviewed", ""))):
                errors.append(f"{cid}: Tier B row is not visibly sourced and dated")
    reviewed = doc.get("missable_windows") if isinstance(doc.get("missable_windows"), dict) else {}
    if reviewed.get("reviewed") is not True:
        errors.append("gwent_cards.json missable_windows.reviewed is not true")
    if reviewed.get("tier_b") != expected["tier_b"]:
        errors.append("gwent_cards.json missable_windows.tier_b does not match the window rows")
    expected_unknown = sum(1 for card in cards
                           if isinstance(card, dict)
                           and (card.get("source") or {}).get("kind") == "unknown")
    if doc.get("counts", {}).get("unknown_source") != expected_unknown:
        errors.append("gwent_cards.json unknown_source count does not match its source rows")
    if doc.get("counts", {}).get("missable") != expected["missable"]:
        errors.append("gwent_cards.json counts.missable does not match the window rows")
    return errors, warnings


def command_build(args):
    doc = load_json(args.file or CARDS)
    review = load_review(args.review)
    titles = route_titles()
    doc = attach(doc, review, titles)
    write_json(args.file or CARDS, doc)
    report = report_doc(doc, review, titles)
    write_json(args.out or OUT, report)
    counts = report["counts"]
    print(f"wrote {Path(args.file or CARDS).relative_to(TRACKER)} and "
          f"{Path(args.out or OUT).relative_to(TRACKER)}")
    print(f"  {counts['total']} cards: {counts['missable']} missable "
          f"({counts['missable_tier_b']} Tier B, {counts['missable_tier_a']} Tier A), "
          f"{counts['one_time']} one-time Tier A, {counts['none']} no-window "
          f"({counts['tier_c']} Tier C)")
    return 0


def command_check(args):
    errors, warnings = [], []
    doc = load_json(args.file or CARDS)
    report = load_json(args.out or OUT)
    review = load_review(args.review)
    route_ids = set(route_titles())
    errors.extend(validate(doc, report, review, route_ids)[0])
    for warning in warnings:
        print("warning: " + warning)
    for error in errors:
        print("error: " + error)
    if errors:
        print(f"{len(errors)} problem(s); the card-window matrix is not shippable")
        return 1
    counts = report["counts"]
    print(f"card windows ok: {counts['total']} cards = "
          f"{counts['missable']} missable ({counts['missable_tier_b']} community/Tier B, "
          f"{counts['missable_tier_a']} gamefile/Tier A), "
          f"{counts['one_time']} one-time, {counts['none']} documented no-window, "
          f"{counts['tier_c']} unknown-source rows")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="rebuild card_windows.json and attach windows to cards")
    build.add_argument("--file", type=Path, default=CARDS)
    build.add_argument("--review", type=Path, default=REVIEW)
    build.add_argument("--out", type=Path, default=OUT)
    build.set_defaults(func=command_build)
    check = sub.add_parser("check", help="validate every shipped card's window")
    check.add_argument("--file", type=Path, default=CARDS)
    check.add_argument("--review", type=Path, default=REVIEW)
    check.add_argument("--out", type=Path, default=OUT)
    check.set_defaults(func=command_check)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
