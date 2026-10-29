"""Check `data/endings.json` against the route, the branch graph and the game's strings.

`endings.json` is reviewed data: the reviewer decides which outcomes are goals, the game files
decide the facts and the exact scene line. This checker is the only thing that makes the reviewed
file safe to ship. It never rewrites the file; a failure means the target is not ready, and
`guidance_status: "not_guided_yet"` is the honest alternative.

The checks are the ones in `docs/TARGET-SCHEMA.md` section 2.7:

  schema        version, required keys, types, target/preset ids, labels, review dates
  guidance      a guided target has requirements and rows; a pending target has neither
  branch graph  every source resolves to a branch, step, scene, locId and fact it claims
  exact text    the instruction is the string database's text for its locId, NFC and trimmed
  presets       target ids resolve, arrays are non-empty and unique
  release       `presets.recommended`, no `fixture_` ids, no placeholder tokens

It reads `data/branches.json`, `data/route.json`, `tools/quest_index.json`, the string database
through `tools/stringsdb.py`, and optionally `data/exclusive.json` and `data/coverage.json`.
`--release` adds the release-only rules. A missing default `endings.json` is valid before the first
target is reviewed (and listed as a warning); `--release` fails.

  py endings.py check
  py endings.py check --release
  py endings.py check --endings path/to/endings.json --branches path/to/branches.json

The checker is read-only. `tools/test_endings.py` drives it against the valid and negative fixtures
in `tools/fixtures/endings/`.
"""
import argparse
import itertools
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stringsdb
from paths import HERE, STRING_DB, TRACKER

PACKS = ("base", "ep1", "bob", "other_dlc", "gwent")
TARGET_KEYS = {"label", "pack", "spoiler", "reviewed", "review_note", "outcome",
               "requires", "guidance_status", "guidance_reason", "guidance"}
REQUIRE_KEYS = {"fact", "value", "source"}
GUIDANCE_KEYS = {"step", "branch", "instruction", "source"}
SOURCE_REQUIRE_KEYS = {"kind", "step", "branch", "file", "locid"}
SOURCE_GUIDANCE_KEYS = {"kind", "file", "locid"}
PRESET_KEYS = {"label", "targets", "reviewed", "note"}
ID = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PLACEHOLDERS = ("<", ">", "TODO", "TBD", "FIXTURE")


class DuplicateKey(ValueError):
    """A JSON object repeated a key; `json.load` would otherwise keep only the last one."""


def _no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKey(f"duplicate object key {key!r}")
        out[key] = value
    return out


def load_json(path):
    """Read strict JSON: duplicate object keys are an error, not a silent overwrite."""
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_no_duplicates)


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def is_text(value):
    return isinstance(value, str)


def normalize_text(value):
    return unicodedata.normalize("NFC", value).strip()


def valid_date(value):
    if not is_text(value) or not DATE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def default_quest_index():
    """The spec names data/quest_index.json; this toolchain writes tools/quest_index.json."""
    spec_path = TRACKER / "data" / "quest_index.json"
    return spec_path if spec_path.exists() else HERE / "quest_index.json"


class Strings:
    """The English text of a locId, from the game's own string database."""

    def __init__(self, path):
        self.conn = stringsdb.con(path)
        # Fail here, with a clear message, rather than at the first locId lookup.
        try:
            self.conn.execute("select 1 from STRINGS limit 1").fetchone()
        except Exception:
            self.conn.close()
            raise
        self.cache = {}

    def text(self, locid):
        if locid not in self.cache:
            try:
                value = stringsdb.loc(locid, self.conn)
                self.cache[locid] = value if is_text(value) else ""
            except Exception:
                self.cache[locid] = ""
        return self.cache[locid]

    def close(self):
        self.conn.close()


class Checker:
    def __init__(self, endings_path, branches_path, route_path, quest_index_path,
                 exclusive_path, coverage_path, string_db_path, release=False,
                 allow_missing_endings=False, outcomes_path=None):
        self.endings_path = Path(endings_path)
        self.branches_path = Path(branches_path)
        self.route_path = Path(route_path)
        self.quest_index_path = Path(quest_index_path)
        self.exclusive_path = Path(exclusive_path)
        self.coverage_path = Path(coverage_path)
        self.string_db_path = Path(string_db_path)
        self.release = release
        self.allow_missing_endings = allow_missing_endings
        self.outcomes_path = Path(outcomes_path) if outcomes_path else TRACKER / "data" / "outcomes.json"
        self.outcomes = {}
        self.target_outcomes = {}

        self.errors = []
        self.warnings = []
        self.route_ids = {}
        self.route_index = {}
        self.route_loaded = False
        self.branches = {}
        self.quests_by_step = {}
        self.strings = None
        self.target_edges = set()
        self.outcome_edges = set()
        self.coverage_packs = None
        self.target_ids = set()
        self.target_labels = []
        self.target_packs = {}
        self.preset_labels = []
        self.counts = {"targets": 0, "guided": 0, "pending": 0, "presets": 0}

    @property
    def ok(self):
        return not self.errors

    def close(self):
        if self.strings is not None:
            self.strings.close()

    def err(self, path, message, where="endings.json"):
        self.errors.append(f"{where}: {path}: {message}")

    def warn(self, path, message, where="endings.json"):
        self.warnings.append(f"{where}: {path}: {message}")

    # ---------------------------------------------------------------- inputs

    def load_endings(self):
        if not self.endings_path.exists():
            if self.allow_missing_endings and not self.release:
                self.warn("file", f"not found ({self.endings_path}); no targets are reviewed yet")
                return None
            self.err("file", f"not found ({self.endings_path})")
            return None
        try:
            doc = load_json(self.endings_path)
        except DuplicateKey as exc:
            self.err("file", str(exc))
            return None
        except (OSError, ValueError) as exc:
            self.err("file", f"invalid JSON: {exc}")
            return None
        if not isinstance(doc, dict):
            self.err("file", "must be a JSON object")
            return None
        return doc

    def load_route(self):
        if not self.route_path.exists():
            return
        try:
            doc = load_json(self.route_path)
        except (OSError, ValueError) as exc:
            self.err("file", f"cannot read {self.route_path}: {exc}", where="route.json")
            return
        nodes = doc.get("nodes") if isinstance(doc, dict) else None
        if not isinstance(nodes, list):
            self.err("nodes", "must be a list", where="route.json")
            return
        for i, node in enumerate(nodes):
            if not isinstance(node, dict) or not is_text(node.get("id")):
                self.err(f"nodes[{i}]", "must be an object with a string id", where="route.json")
                continue
            step = node["id"]
            if step in self.route_ids:
                self.err(f"nodes[{i}].id", f"duplicate route step {step!r}", where="route.json")
                continue
            self.route_ids[step] = node
            self.route_index[step] = i
        self.route_loaded = True

    def load_outcomes(self, required):
        """Read the outcome ids/status/pack so an outcome-backed target cannot drift from its
        reviewed terminal row. The full outcome evidence is checked by tools/outcomecheck.py."""
        if not self.outcomes_path.exists():
            if required:
                self.err("file", f"not found ({self.outcomes_path}); outcome-backed targets need it",
                         where="outcomes.json")
            return
        try:
            doc = load_json(self.outcomes_path)
        except (OSError, ValueError) as exc:
            self.err("file", f"cannot read {self.outcomes_path}: {exc}", where="outcomes.json")
            return
        rows = doc.get("outcomes") if isinstance(doc, dict) else None
        if not isinstance(rows, dict):
            self.err("outcomes", "must be an object", where="outcomes.json")
            return
        for oid, outcome in rows.items():
            if isinstance(outcome, dict):
                self.outcomes[oid] = outcome

    def load_branches(self, required):
        if not self.branches_path.exists():
            if required:
                self.err("file", f"not found ({self.branches_path}); a guided target needs branch sources",
                         where="branches.json")
            return
        try:
            doc = load_json(self.branches_path)
        except (OSError, ValueError) as exc:
            self.err("file", f"cannot read {self.branches_path}: {exc}", where="branches.json")
            return
        if not isinstance(doc, dict):
            self.err("file", "must be a JSON object", where="branches.json")
            return
        if "version" in doc and doc.get("version") != 1:
            self.err("version", "must be 1 when present", where="branches.json")
        groups = doc.get("branches")
        if not isinstance(groups, dict):
            self.err("branches", "must be an object keyed by step", where="branches.json")
            return
        for key, entry in groups.items():
            if not isinstance(entry, dict):
                self.err(f"branches.{key}", "must be an object", where="branches.json")
                continue
            choices = entry.get("choices")
            if choices is None:
                # tolerate the one-choice shorthand, but prefer the documented shape
                choices = [entry] if "id" in entry else []
            if not isinstance(choices, list):
                self.err(f"branches.{key}.choices", "must be a list", where="branches.json")
                continue
            for i, choice in enumerate(choices):
                path = f"branches.{key}.choices[{i}]"
                if not isinstance(choice, dict):
                    self.err(path, "must be an object", where="branches.json")
                    continue
                bid = choice.get("id")
                if not is_text(bid) or not bid:
                    self.err(path + ".id", "must be a non-empty string", where="branches.json")
                    continue
                step = choice.get("step") or entry.get("step") or key
                scene = choice.get("scene") or entry.get("scene") or ""
                locid = choice.get("choice_locid", entry.get("choice_locid"))
                sets = choice.get("sets", entry.get("sets", []))
                if not is_text(step) or not step:
                    self.err(path + ".step", "must be a non-empty string", where="branches.json")
                    step = ""
                if not is_text(scene) or not scene:
                    self.err(path + ".scene", "must be a non-empty string", where="branches.json")
                    scene = ""
                if not is_int(locid) or locid <= 0:
                    self.err(path + ".choice_locid", "must be a positive integer", where="branches.json")
                    locid = 0
                if not isinstance(sets, list) or any(not is_text(x) or not x for x in sets):
                    self.err(path + ".sets", "must be a list of non-empty strings", where="branches.json")
                    sets = []
                if bid in self.branches:
                    self.err(path + ".id", f"duplicate branch id {bid!r}", where="branches.json")
                    continue
                self.branches[bid] = {
                    "id": bid, "step": step, "scene": scene,
                    "choice_locid": locid, "sets": set(sets), "path": path,
                }

    def load_quest_index(self):
        if not self.quest_index_path.exists():
            return
        try:
            doc = load_json(self.quest_index_path)
        except (OSError, ValueError) as exc:
            self.err("file", f"cannot read {self.quest_index_path}: {exc}", where="quest_index.json")
            return
        quests = doc.get("quests") if isinstance(doc, dict) else None
        if not isinstance(quests, dict):
            self.err("quests", "must be an object", where="quest_index.json")
            return
        for stem, quest in quests.items():
            if not isinstance(quest, dict):
                continue
            names = quest.get("bundle_names") or [stem]
            for name in names if isinstance(names, list) else [stem]:
                if is_text(name) and name:
                    self.quests_by_step[name] = quest

    def load_strings(self):
        if not self.string_db_path.exists():
            self.err("file", f"not found ({self.string_db_path}); exact instructions cannot be checked")
            return
        try:
            self.strings = Strings(self.string_db_path)
        except Exception as exc:
            self.err("file", f"cannot open {self.string_db_path}: {exc}")

    def load_exclusive(self):
        if not self.exclusive_path.exists():
            return
        try:
            doc = load_json(self.exclusive_path)
        except (OSError, ValueError) as exc:
            self.err("file", f"cannot read {self.exclusive_path}: {exc}", where="exclusive.json")
            return
        edges = doc.get("edges") if isinstance(doc, dict) else None
        if not isinstance(edges, list):
            self.err("edges", "must be a list", where="exclusive.json")
            return
        for i, edge in enumerate(edges):
            if not isinstance(edge, dict):
                self.err(f"edges[{i}]", "must be an object", where="exclusive.json")
                continue
            kind = edge.get("kind")
            if kind not in ("target", "outcome"):
                continue
            a, b = edge.get("a"), edge.get("b")
            if not is_text(a) or not is_text(b) or not a or not b:
                self.err(f"edges[{i}]", "an edge needs string a and b", where="exclusive.json")
                continue
            a = a[len("target:"):] if kind == "target" and a.startswith("target:") else a
            b = b[len("target:"):] if kind == "target" and b.startswith("target:") else b
            a = a[len("outcome:"):] if kind == "outcome" and a.startswith("outcome:") else a
            b = b[len("outcome:"):] if kind == "outcome" and b.startswith("outcome:") else b
            if a != b:
                (self.target_edges if kind == "target" else self.outcome_edges).add(frozenset((a, b)))

    def load_coverage(self):
        if not self.coverage_path.exists():
            return
        try:
            doc = load_json(self.coverage_path)
        except (OSError, ValueError) as exc:
            self.err("file", f"cannot read {self.coverage_path}: {exc}", where="coverage.json")
            return
        packs = doc.get("packs") if isinstance(doc, dict) else None
        if not isinstance(packs, dict):
            self.err("packs", "must be an object", where="coverage.json")
            return
        self.coverage_packs = packs

    # ---------------------------------------------------------------- checks

    def scan_placeholders(self, value, path=""):
        if isinstance(value, str):
            for token in PLACEHOLDERS:
                if token in value:
                    self.err(path or "value", f"contains placeholder token {token!r}")
        elif isinstance(value, dict):
            for key, item in value.items():
                self.scan_placeholders(item, f"{path}.{key}" if path else str(key))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                self.scan_placeholders(item, f"{path}[{i}]")

    def check_source(self, source, path, branch=None, guidance=False):
        """Validate a source object.

        `requires[].source` names a branch and a step; `guidance[].source` only names the file and
        locId, and the row's own branch is supplied by the caller. `guidance=True` selects the
        smaller key set even when the row's branch did not resolve.
        """
        if not isinstance(source, dict):
            self.err(path, "must be an object")
            return None
        allowed = SOURCE_GUIDANCE_KEYS if guidance else SOURCE_REQUIRE_KEYS
        for key in sorted(set(source) - allowed):
            self.err(path, f"unknown key {key!r}")
        for key in sorted(allowed - set(source)):
            self.err(path, f"missing required key {key!r}")
        if source.get("kind") != "scene_choice":
            self.err(path + ".kind", "must be 'scene_choice'")
        file = source.get("file")
        if not is_text(file) or not file:
            self.err(path + ".file", "must be a non-empty string")
            file = ""
        locid = source.get("locid")
        if not is_int(locid) or locid <= 0:
            self.err(path + ".locid", "must be a positive integer")
            locid = 0

        step = source.get("step")
        if not guidance:
            if not is_text(step) or not step:
                self.err(path + ".step", "must be a non-empty string")
                step = ""
            bid = source.get("branch")
            if not is_text(bid) or not bid:
                self.err(path + ".branch", "must be a non-empty string")
                return None
            if self.route_loaded and step and step not in self.route_ids:
                self.err(path + ".step", f"unknown route step {step!r}")
            branch = self.branches.get(bid)
            if branch is None:
                self.err(path + ".branch", f"unknown branch {bid!r}")
                return None
            if branch["step"] != step:
                self.err(path + ".step", f"does not match branch {bid!r} step {branch['step']!r}")
            if branch["scene"] != file:
                self.err(path + ".file", f"does not match branch {bid!r} scene")
            if branch["choice_locid"] != locid:
                self.err(path + ".locid", f"does not match branch {bid!r} choice_locid")
        elif branch is not None:
            if branch["scene"] != file:
                self.err(path + ".file", f"does not match branch {branch['id']!r} scene")
            if branch["choice_locid"] != locid:
                self.err(path + ".locid", f"does not match branch {branch['id']!r} choice_locid")

        if self.strings is not None and locid > 0:
            if not self.strings.text(locid):
                self.err(path + ".locid", f"locId {locid} has no text in the string database")
        return branch

    def check_target(self, tid, target):
        path = f"targets.{tid}"
        if not isinstance(target, dict):
            self.err(path, "must be an object")
            return
        for key in sorted(set(target) - TARGET_KEYS):
            self.err(path, f"unknown key {key!r}")

        label = target.get("label")
        if not is_text(label):
            self.err(path + ".label", "must be a string")
        else:
            if label != label.strip():
                self.err(path + ".label", "must not have leading or trailing whitespace")
            if len(label) < 1 or len(label) > 80:
                self.err(path + ".label", "must be 1-80 characters")
            if label.endswith("."):
                self.err(path + ".label", "must not end with a period")
            self.target_labels.append((tid, label))

        if not ID.fullmatch(tid):
            self.err(path, "target id must match ^[a-z][a-z0-9_]{2,63}$")
        if tid in PACKS:
            self.err(path, f"target id must not equal pack code {tid!r}")
        if tid in self.route_ids:
            self.err(path, f"target id must not equal route step {tid!r}")
        if self.release and tid.startswith("fixture_"):
            self.err(path, "target id must not begin with 'fixture_' in shipped data")

        pack = target.get("pack")
        if pack not in PACKS:
            self.err(path + ".pack", f"must be one of {', '.join(PACKS)}")
        else:
            self.target_packs[tid] = pack

        if target.get("spoiler") is not True:
            self.err(path + ".spoiler", "must be true in v1")

        if not valid_date(target.get("reviewed")):
            self.err(path + ".reviewed", "must be a real YYYY-MM-DD date")

        if "review_note" in target and not is_text(target["review_note"]):
            self.err(path + ".review_note", "must be a string")

        requires = target.get("requires")
        if not isinstance(requires, list):
            self.err(path + ".requires", "must be a list")
            requires = []
        guidance = target.get("guidance")
        if not isinstance(guidance, list):
            self.err(path + ".guidance", "must be a list")
            guidance = []

        status = target.get("guidance_status")
        if status not in ("guided", "not_guided_yet"):
            self.err(path + ".guidance_status", "must be 'guided' or 'not_guided_yet'")
            return

        has_reason = "guidance_reason" in target
        reason = target.get("guidance_reason")
        if has_reason and not is_text(reason):
            self.err(path + ".guidance_reason", "must be a string")

        outcome_id = target.get("outcome")
        if outcome_id is not None:
            if not is_text(outcome_id) or not ID.fullmatch(outcome_id):
                self.err(path + ".outcome", "must match ^[a-z][a-z0-9_]{2,63}$")
                outcome_id = None
            elif outcome_id not in self.outcomes:
                self.err(path + ".outcome", f"unknown outcome {outcome_id!r}")
                outcome_id = None
            else:
                outcome = self.outcomes[outcome_id]
                if outcome.get("pack") != pack:
                    self.err(path + ".pack", f"does not match outcome pack {outcome.get('pack')!r}")
                if outcome.get("guidance_status") != status:
                    self.err(path + ".guidance_status",
                             f"does not match outcome status {outcome.get('guidance_status')!r}")
                self.target_outcomes[tid] = outcome_id

        if status == "guided":
            if has_reason:
                self.err(path + ".guidance_reason", "must not be present on a guided target")
            if outcome_id is not None:
                # The rows live once, in outcomes.json. Duplicating them here would let the
                # target and the matrix disagree about the same ending.
                if requires:
                    self.err(path + ".requires", "must be empty on an outcome-backed target")
                if guidance:
                    self.err(path + ".guidance", "must be empty on an outcome-backed target")
                return
            if not requires:
                self.err(path + ".requires", "a guided target needs at least one row")
            if not guidance:
                self.err(path + ".guidance", "a guided target needs at least one row")
            facts = self.check_requires(tid, requires)
            self.check_guidance(tid, guidance, facts)
            return

        self.counts["pending"] += 1
        if requires != []:
            self.err(path + ".requires", "must be empty when guidance_status is not_guided_yet")
        if guidance != []:
            self.err(path + ".guidance", "must be empty when guidance_status is not_guided_yet")
        if not has_reason or not is_text(reason) or not reason.strip():
            self.err(path + ".guidance_reason", "required and non-empty when guidance_status is not_guided_yet")

    def check_requires(self, tid, rows):
        path = f"targets.{tid}.requires"
        facts = []
        for i, row in enumerate(rows):
            p = f"{path}[{i}]"
            if not isinstance(row, dict):
                self.err(p, "must be an object")
                continue
            for key in sorted(set(row) - REQUIRE_KEYS):
                self.err(p, f"unknown key {key!r}")
            for key in sorted(REQUIRE_KEYS - set(row)):
                self.err(p, f"missing required key {key!r}")
            fact = row.get("fact")
            if not is_text(fact) or not fact:
                self.err(p + ".fact", "must be a non-empty string")
                fact = None
            else:
                if any(ch.isspace() for ch in fact):
                    self.err(p + ".fact", "must not contain whitespace")
                    fact = None
                elif fact in facts:
                    self.err(p + ".fact", f"duplicate required fact {fact!r}")
            if row.get("value") is not True:
                self.err(p + ".value", "must be true in v1")

            source = row.get("source")
            branch = self.check_source(source, p + ".source") if isinstance(source, dict) else None
            if not isinstance(source, dict):
                self.err(p + ".source", "must be an object")
            if fact is not None and branch is not None and fact not in branch["sets"]:
                self.err(p + ".fact", f"branch {branch['id']!r} does not set {fact!r}")
            if fact is not None and branch is not None:
                quest = self.quests_by_step.get(branch["step"])
                branch_facts = quest.get("branch_facts") if isinstance(quest, dict) else None
                if isinstance(branch_facts, list) and branch_facts and fact not in branch_facts:
                    self.warn(p + ".fact",
                              f"quest_index.json branch_facts for {branch['step']!r} does not list {fact!r}")
            if fact is not None:
                facts.append(fact)

        if facts != sorted(facts):
            self.err(path, "rows must be sorted by fact ascending")
        return facts

    def check_guidance(self, tid, rows, facts):
        path = f"targets.{tid}.guidance"
        entries = []
        seen_steps = set()
        branch_sets = []
        for i, row in enumerate(rows):
            p = f"{path}[{i}]"
            if not isinstance(row, dict):
                self.err(p, "must be an object")
                continue
            for key in sorted(set(row) - GUIDANCE_KEYS):
                self.err(p, f"unknown key {key!r}")
            for key in sorted(GUIDANCE_KEYS - set(row)):
                self.err(p, f"missing required key {key!r}")

            step = row.get("step")
            if not is_text(step) or not step:
                self.err(p + ".step", "must be a non-empty string")
                step = None
            else:
                if self.route_loaded and step not in self.route_ids:
                    self.err(p + ".step", f"unknown route step {step!r}")
                if step in seen_steps:
                    self.err(p + ".step", f"duplicate guidance step {step!r}")
                seen_steps.add(step)

            bid = row.get("branch")
            branch = None
            if not is_text(bid) or not bid:
                self.err(p + ".branch", "must be a non-empty string")
            else:
                branch = self.branches.get(bid)
                if branch is None:
                    self.err(p + ".branch", f"unknown branch {bid!r}")
                else:
                    if step is not None and branch["step"] != step:
                        self.err(p + ".step", f"does not match branch {bid!r} step {branch['step']!r}")
                    if not (branch["sets"] & set(facts)):
                        self.err(p + ".branch", f"sets none of this target's required facts")
                    branch_sets.append(branch)

            instruction = row.get("instruction")
            if not is_text(instruction) or not instruction.strip():
                self.err(p + ".instruction", "must be a non-empty string")
                instruction = None

            source = row.get("source")
            if isinstance(source, dict):
                self.check_source(source, p + ".source", branch=branch, guidance=True)
            else:
                self.err(p + ".source", "must be an object")

            if (instruction is not None and self.strings is not None
                    and isinstance(source, dict)
                    and is_int(source.get("locid")) and source["locid"] > 0):
                text = self.strings.text(source["locid"])
                if text and normalize_text(instruction) != normalize_text(text):
                    self.err(p + ".instruction",
                             f"must equal the string-database text for locId {source['locid']}")

            entries.append((self.route_index.get(step, len(self.route_ids) + 1),
                            bid if is_text(bid) else "", i))

        for fact in facts:
            if not any(fact in branch["sets"] for branch in branch_sets):
                self.err(path, f"required fact {fact!r} has no guidance row that sets it")

        if entries != sorted(entries):
            self.err(path, "rows must be sorted by route order of step, then branch")

    def check_presets(self, presets):
        path = "presets"
        for pid, preset in presets.items():
            p = f"{path}.{pid}"
            if not isinstance(preset, dict):
                self.err(p, "must be an object")
                continue
            for key in sorted(set(preset) - PRESET_KEYS):
                self.err(p, f"unknown key {key!r}")
            for key in sorted(PRESET_KEYS - set(preset) - {"note"}):
                self.err(p, f"missing required key {key!r}")
            if not ID.fullmatch(pid):
                self.err(p, "preset id must match ^[a-z][a-z0-9_]{2,63}$")
            label = preset.get("label")
            if not is_text(label) or not label:
                self.err(p + ".label", "must be a non-empty string")
            else:
                if len(label) > 80:
                    self.err(p + ".label", "must be 1-80 characters")
                self.preset_labels.append((pid, label))
            targets = preset.get("targets")
            if not isinstance(targets, list):
                self.err(p + ".targets", "must be a list")
                targets = []
            elif not targets:
                self.err(p + ".targets", "must contain at least one target id")
            seen = set()
            for i, target in enumerate(targets):
                if not is_text(target):
                    self.err(f"{p}.targets[{i}]", "must be a target id string")
                    continue
                if target in seen:
                    self.err(f"{p}.targets[{i}]", f"duplicate target id {target!r}")
                seen.add(target)
                if target not in self.target_ids:
                    self.err(f"{p}.targets[{i}]", f"unknown target id {target!r}")
            if not valid_date(preset.get("reviewed")):
                self.err(p + ".reviewed", "must be a real YYYY-MM-DD date")
            if "note" in preset and not is_text(preset["note"]):
                self.err(p + ".note", "must be a string")
            if pid == "recommended" and label != "Recommended endings":
                self.err(p + ".label", "must be exactly 'Recommended endings'")

        if self.release and "recommended" not in presets:
            self.err(path, "recommended preset is required in a release check")

    def check_duplicate_labels(self):
        seen = {}
        for tid, label in self.target_labels:
            if label in seen:
                self.err(f"targets.{tid}.label", f"duplicate target label {label!r} (also {seen[label]})")
            else:
                seen[label] = tid
        seen = {}
        for pid, label in self.preset_labels:
            if label in seen:
                self.err(f"presets.{pid}.label", f"duplicate preset label {label!r} (also {seen[label]})")
            else:
                seen[label] = pid

    def check_id_collisions(self):
        for tid in self.target_ids:
            if tid in self.branches:
                self.err(self.branches[tid]["path"] + ".id", f"branch id collides with target id {tid!r}",
                         where="branches.json")

    def check_exclusive_warnings(self, presets):
        edges = set(self.target_edges)
        for edge in self.outcome_edges:
            pair = sorted(edge)
            owners = []
            for oid in pair:
                owners.append([tid for tid, target_oid in self.target_outcomes.items() if target_oid == oid])
            for a in owners[0]:
                for b in owners[1]:
                    if a != b:
                        edges.add(frozenset((a, b)))
        for pid, preset in presets.items():
            if not isinstance(preset, dict) or not isinstance(preset.get("targets"), list):
                continue
            targets = [t for t in preset["targets"] if is_text(t) and t in self.target_ids]
            for a, b in itertools.combinations(targets, 2):
                if frozenset((a, b)) in edges:
                    self.warn(f"presets.{pid}.targets",
                              f"contains exclusive targets {a!r} and {b!r}; show the tradeoff before applying")

    def check_coverage_warnings(self):
        if not self.target_packs:
            return
        if self.coverage_packs is None:
            state = "not found" if not self.coverage_path.exists() else "not available"
            self.warn("file", f"{state} ({self.coverage_path}); pack coverage was not checked",
                      where="coverage.json")
            return
        for tid, pack in self.target_packs.items():
            if pack not in self.coverage_packs:
                self.warn(f"targets.{tid}.pack", f"pack {pack!r} has no coverage row", where="coverage.json")

    def check_document(self, doc):
        self.scan_placeholders(doc)
        for key in sorted(set(doc) - {"version", "note", "targets", "presets"}):
            self.err(str(key), f"unknown key {key!r}")

        if not is_int(doc.get("version")) or doc.get("version") != 1:
            self.err("version", "must be 1")
        if not is_text(doc.get("note")):
            self.err("note", "must be a string")

        targets = doc.get("targets")
        if not isinstance(targets, dict):
            self.err("targets", "must be an object keyed by target id")
            targets = {}
        presets = doc.get("presets")
        if not isinstance(presets, dict):
            self.err("presets", "must be an object keyed by preset id")
            presets = {}

        self.target_ids = set(targets)
        if not targets:
            if self.release:
                self.err("targets", "must contain at least one target in a release check")
            else:
                self.warn("targets", "no targets are reviewed yet")

        for tid, target in targets.items():
            self.check_target(tid, target)
            if isinstance(target, dict) and target.get("guidance_status") == "guided":
                self.counts["guided"] += 1
        self.counts["targets"] = len(targets)
        self.counts["presets"] = len(presets)

        self.check_presets(presets)
        self.check_duplicate_labels()
        self.check_id_collisions()
        self.check_exclusive_warnings(presets)
        self.check_coverage_warnings()

    def run(self):
        doc = self.load_endings()
        self.load_route()
        self.load_quest_index()
        self.load_exclusive()
        self.load_coverage()
        if doc is None:
            return self.ok

        targets = doc.get("targets") if isinstance(doc.get("targets"), dict) else {}
        guided = any(isinstance(t, dict) and t.get("guidance_status") != "not_guided_yet"
                     for t in targets.values())
        outcome_backed = any(isinstance(t, dict) and "outcome" in t for t in targets.values())
        if guided and not self.route_loaded and not self.route_path.exists():
            self.err("file", f"not found ({self.route_path}); a guided target needs route steps",
                     where="route.json")
        self.load_outcomes(required=outcome_backed)
        self.load_branches(required=guided)
        if guided:
            self.load_strings()
        self.check_document(doc)
        return self.ok


def add_check_arguments(parser):
    parser.add_argument("--release", action="store_true",
                        help="also require presets.recommended and no fixture_ ids")
    parser.add_argument("--endings", type=Path, default=None,
                        help="default: data/endings.json")
    parser.add_argument("--branches", type=Path, default=TRACKER / "data" / "branches.json")
    parser.add_argument("--route", type=Path, default=TRACKER / "data" / "route.json")
    parser.add_argument("--quest-index", type=Path, default=default_quest_index())
    parser.add_argument("--exclusive", type=Path, default=TRACKER / "data" / "exclusive.json")
    parser.add_argument("--coverage", type=Path, default=TRACKER / "data" / "coverage.json")
    parser.add_argument("--outcomes", type=Path, default=TRACKER / "data" / "outcomes.json")
    parser.add_argument("--string-db", type=Path, default=STRING_DB)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="validate endings.json; never rewrite it")
    add_check_arguments(check)
    args = parser.parse_args(argv)

    if args.command != "check":
        parser.error("unknown command")
    endings_path = args.endings if args.endings is not None else TRACKER / "data" / "endings.json"
    allow_missing = args.endings is None and not args.release
    checker = Checker(endings_path, args.branches, args.route, args.quest_index, args.exclusive,
                      args.coverage, args.string_db, release=args.release,
                      allow_missing_endings=allow_missing, outcomes_path=args.outcomes)
    checker.run()

    warnings, errors = checker.warnings, checker.errors
    checker.close()
    for warning in warnings:
        print(f"warning: {warning}")
    for error in errors:
        print(f"error: {error}")
    if errors:
        print(f"{len(errors)} problem(s); endings.json is not shippable")
        return 1
    counts = checker.counts
    print(f"endings ok: {counts['targets']} target(s), {counts['guided']} guided, "
          f"{counts['pending']} not guided yet, {counts['presets']} preset(s); "
          f"{len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
