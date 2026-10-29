"""Check `data/outcomes.json` against the game files and the reviewed target set.

`outcomes.json` is reviewed data: it names the terminal outcomes, the fact each one needs and the
exact line or journal description that proves it. This checker is what makes that file safe to
ship. It never rewrites anything.

It resolves four kinds of evidence:

  phase_fact     the fact is set by a phase file in tools/fact_index.json
  scene_choice   the branch exists in data/branches.json, is on the route step, and sets the fact
  scene_line     the locId is in the string database and its resource is the named scene file
  journal_group  the locId and baseName are a CJournalQuestDescriptionEntry in the named .journal

Groups are `selection: one`: each group's outcomes are alternatives, and a release check requires
a reviewed exclusion edge for every pair in the group. Cross-group edges are allowed only when
they carry evidence; none are inferred.

  py outcomecheck.py
  py outcomecheck.py --release
  py outcomecheck.py --outcomes data/outcomes.json --endings data/endings.json

Exit 1 on any error. `tools/test_outcomes.py` drives it against valid and negative fixtures.
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
import cr2w
import endings
import stringsdb
from paths import HERE, REDKIT_R4, STRING_DB, TRACKER

PACKS = ("base", "ep1", "bob", "other_dlc", "gwent")
ID = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
FACT = re.compile(r"^[a-z][a-z0-9_]{3,}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PLACEHOLDERS = ("<", ">", "TODO", "TBD", "FIXTURE")
OUTCOME_KEYS = {"group", "pack", "label", "spoiler", "reviewed", "review_note",
                "guidance_status", "guidance_reason", "requires", "guidance", "journal_outcome"}
GROUP_KEYS = {"pack", "label", "selection", "outcomes"}
REQUIRE_KEYS = {"fact", "value", "source"}
GUIDANCE_KEYS = {"step", "kind", "branch", "instruction", "facts", "source", "mechanism"}
SOURCE_KEYS = {"kind", "step", "branch", "file", "locid", "fact"}
JOURNAL_KEYS = {"file", "locid", "base_name"}
EDGE_KEYS = {"kind", "a", "b", "reason", "mechanism", "evidence"}
EVIDENCE_KEYS = {"kind", "value"}


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def is_text(value):
    return isinstance(value, str)


def norm(value):
    return unicodedata.normalize("NFC", value).strip()


def valid_date(value):
    if not is_text(value) or not DATE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def rel_path(value):
    """Normalize a game-relative path for comparisons and existence checks."""
    return str(value).replace("/", "\\").lower()


class Checker:
    def __init__(self, outcomes_path, endings_path, branches_path, route_path, quest_index_path,
                 exclusive_path, fact_index_path, string_db_path, release=False):
        self.outcomes_path = Path(outcomes_path)
        self.endings_path = Path(endings_path)
        self.branches_path = Path(branches_path)
        self.route_path = Path(route_path)
        self.quest_index_path = Path(quest_index_path)
        self.exclusive_path = Path(exclusive_path)
        self.fact_index_path = Path(fact_index_path)
        self.string_db_path = Path(string_db_path)
        self.release = release

        self.errors = []
        self.warnings = []
        self.loaded = False
        self.groups = {}
        self.outcomes = {}
        self.targets = {}
        self.target_outcomes = {}
        self.branches = {}
        self.route_ids = {}
        self.route_index = {}
        self.facts = {}          # (file_lower, fact) -> list of rows
        self.phase_cache = {}
        self.quests = {}
        self.strings = None
        self.journals = {}
        self.journal_objectives = {}
        self.edges = []
        self.counts = {"groups": 0, "outcomes": 0, "guided": 0, "pending": 0, "targets": 0, "edges": 0}

    @property
    def ok(self):
        return not self.errors

    def close(self):
        if self.strings is not None:
            self.strings.close()

    def err(self, path, message, where="outcomes.json"):
        self.errors.append(f"{where}: {path}: {message}")

    def warn(self, path, message, where="outcomes.json"):
        self.warnings.append(f"{where}: {path}: {message}")

    # ---------------------------------------------------------------- inputs

    def load_json(self, path, where):
        try:
            return endings.load_json(path)
        except endings.DuplicateKey as exc:
            self.err("file", str(exc), where=where)
        except (OSError, ValueError) as exc:
            self.err("file", f"invalid JSON: {exc}", where=where)
        return None

    def load_outcomes(self):
        if not self.outcomes_path.exists():
            self.err("file", f"not found ({self.outcomes_path})")
            return None
        doc = self.load_json(self.outcomes_path, "outcomes.json")
        if not isinstance(doc, dict):
            if doc is not None:
                self.err("file", "must be a JSON object")
            return None
        return doc

    def load_endings(self):
        if not self.endings_path.exists():
            self.err("file", f"not found ({self.endings_path})", where="endings.json")
            return
        doc = self.load_json(self.endings_path, "endings.json")
        targets = doc.get("targets") if isinstance(doc, dict) else None
        if not isinstance(targets, dict):
            self.err("targets", "must be an object in endings.json", where="endings.json")
            return
        self.targets = targets
        for tid, target in targets.items():
            if isinstance(target, dict) and is_text(target.get("outcome")):
                self.target_outcomes[tid] = target["outcome"]

    def load_branches(self):
        if not self.branches_path.exists():
            self.err("file", f"not found ({self.branches_path})", where="branches.json")
            return
        doc = self.load_json(self.branches_path, "branches.json")
        groups = doc.get("branches") if isinstance(doc, dict) else None
        if not isinstance(groups, dict):
            self.err("branches", "must be an object", where="branches.json")
            return
        for key, entry in groups.items():
            if not isinstance(entry, dict):
                continue
            choices = entry.get("choices")
            if choices is None:
                choices = [entry] if "id" in entry else []
            for choice in choices if isinstance(choices, list) else []:
                if not isinstance(choice, dict):
                    continue
                bid = choice.get("id")
                step = choice.get("step") or entry.get("step") or key
                scene = choice.get("scene") or entry.get("scene") or ""
                locid = choice.get("choice_locid", entry.get("choice_locid"))
                sets = choice.get("sets", entry.get("sets", []))
                if is_text(bid) and is_text(step) and is_int(locid):
                    self.branches[bid] = {
                        "id": bid, "step": step, "scene": scene,
                        "locid": locid, "sets": set(sets if isinstance(sets, list) else []),
                    }

    def load_route(self):
        if not self.route_path.exists():
            self.err("file", f"not found ({self.route_path})", where="route.json")
            return
        doc = self.load_json(self.route_path, "route.json")
        nodes = doc.get("nodes") if isinstance(doc, dict) else None
        if not isinstance(nodes, list):
            self.err("nodes", "must be a list", where="route.json")
            return
        for i, node in enumerate(nodes):
            if isinstance(node, dict) and is_text(node.get("id")):
                self.route_ids[node["id"]] = node
                self.route_index[node["id"]] = i

    def load_quest_index(self):
        if not self.quest_index_path.exists():
            return
        doc = self.load_json(self.quest_index_path, "quest_index.json")
        quests = doc.get("quests") if isinstance(doc, dict) else None
        if not isinstance(quests, dict):
            return
        for stem, quest in quests.items():
            if not isinstance(quest, dict):
                continue
            for name in quest.get("bundle_names") or [stem]:
                if is_text(name) and name:
                    self.quests[name] = quest

    def load_facts(self):
        if not self.fact_index_path.exists():
            self.warn("file", f"not found ({self.fact_index_path}); phase facts will be read from the files directly",
                      where="fact_index.json")
            return
        rows = self.load_json(self.fact_index_path, "fact_index.json")
        if not isinstance(rows, list):
            self.err("file", "must be a JSON list", where="fact_index.json")
            return
        for row in rows:
            if not isinstance(row, dict) or row.get("kind") != "set":
                continue
            src = row.get("src")
            fact = row.get("fact")
            if is_text(src) and is_text(fact):
                self.facts.setdefault((rel_path(src), fact), []).append(row)

    def phase_sets(self, file_value, fact):
        """Direct evidence: does this .w2phase contain a facts-changing block for `fact`?"""
        key = (rel_path(file_value), fact)
        if key in self.phase_cache:
            return self.phase_cache[key]
        p = REDKIT_R4 / str(file_value)
        if not p.exists():
            self.err("file", f"phase file not found under REDkit: {file_value!r}", where="outcomes.json")
            self.phase_cache[key] = False
            return False
        try:
            doc = cr2w.parse(p)
        except Exception as exc:
            self.err("file", f"cannot parse {file_value}: {exc}", where="outcomes.json")
            self.phase_cache[key] = False
            return False
        found = False
        for e in doc["exports"]:
            if e["className"] != "CQuestFactsDBChangingBlock":
                continue
            ps = {x["name"]: x["value"] for x in cr2w.props(doc, e)}
            f = ps.get("factID") or ps.get("factId")
            if f == fact:
                found = True
                break
        self.phase_cache[key] = found
        return found

    def load_strings(self):
        if not self.string_db_path.exists():
            self.err("file", f"not found ({self.string_db_path}); exact text cannot be checked")
            return
        try:
            self.strings = endings.Strings(self.string_db_path)
        except Exception as exc:
            self.err("file", f"cannot open {self.string_db_path}: {exc}")

    def journal_entries(self, file_value):
        key = rel_path(file_value)
        if key in self.journals:
            return self.journals[key]
        p = REDKIT_R4 / str(file_value)
        if not p.exists():
            self.journals[key] = None
            return None
        try:
            doc = cr2w.parse(p)
        except Exception as exc:
            self.err("file", f"cannot parse {file_value}: {exc}", where="outcomes.json")
            self.journals[key] = None
            return None
        out = {}
        for e in doc["exports"]:
            if e["className"] != "CJournalQuestDescriptionEntry":
                continue
            ps = {x["name"]: x["value"] for x in cr2w.props(doc, e)}
            desc = ps.get("description")
            locid = desc.get("locId") if isinstance(desc, dict) else desc
            if is_int(locid):
                out[locid] = ps.get("baseName")
        self.journals[key] = out
        return out

    def objective_titles(self, file_value):
        key = rel_path(file_value)
        if key in self.journal_objectives:
            return self.journal_objectives[key]
        p = REDKIT_R4 / str(file_value)
        if not p.exists():
            self.journal_objectives[key] = None
            return None
        try:
            doc = cr2w.parse(p)
        except Exception as exc:
            self.err("file", f"cannot parse {file_value}: {exc}", where="outcomes.json")
            self.journal_objectives[key] = None
            return None
        out = {}
        for e in doc["exports"]:
            if e["className"] != "CJournalQuestObjective":
                continue
            ps = {x["name"]: x["value"] for x in cr2w.props(doc, e)}
            title = ps.get("title")
            locid = title.get("locId") if isinstance(title, dict) else title
            if is_int(locid):
                out[locid] = ps.get("baseName")
        self.journal_objectives[key] = out
        return out

    def scene_resource(self, locid):
        if self.strings is None:
            return ""
        row = self.strings.conn.execute(
            "select RESOURCE from STRING_INFO where STRING_ID=? limit 1", (int(locid),)
        ).fetchone()
        return stringsdb.path_of(row[0]) if row else ""

    # ---------------------------------------------------------------- helpers

    def check_placeholders(self, value, path=""):
        if isinstance(value, str):
            for token in PLACEHOLDERS:
                if token in value:
                    self.err(path or "value", f"contains placeholder token {token!r}")
        elif isinstance(value, dict):
            for key, item in value.items():
                self.check_placeholders(item, f"{path}.{key}" if path else str(key))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                self.check_placeholders(item, f"{path}[{i}]")

    def check_source(self, source, path, fact=None):
        if not isinstance(source, dict):
            self.err(path, "must be an object")
            return None
        for key in sorted(set(source) - SOURCE_KEYS):
            self.err(path, f"unknown key {key!r}")
        kind = source.get("kind")
        if kind not in ("phase_fact", "scene_choice", "scene_line", "journal_objective"):
            self.err(path + ".kind", "must be phase_fact, scene_choice, scene_line or journal_objective")
            return None
        step = source.get("step")
        file = source.get("file")
        locid = source.get("locid")
        if not is_text(file) or not file:
            self.err(path + ".file", "must be a non-empty string")
            file = ""
        if kind == "phase_fact":
            if not is_text(step) or not step:
                self.err(path + ".step", "must be a non-empty string")
            elif self.route_ids and step not in self.route_ids:
                self.err(path + ".step", f"unknown route step {step!r}")
            f = source.get("fact")
            if not is_text(f) or not f:
                self.err(path + ".fact", "must be a non-empty string")
                f = ""
            if fact is not None and f and f != fact:
                self.err(path + ".fact", f"must equal the requirement fact {fact!r}")
            if f and file and (rel_path(file), f) not in self.facts and not self.phase_sets(file, f):
                self.err(path, f"no set row for {f!r} in {file!r} (fact index and phase file agree)")
            return {"kind": kind, "step": step if is_text(step) else "", "file": file, "fact": f}
        if kind == "scene_choice":
            if not is_text(step) or not step:
                self.err(path + ".step", "must be a non-empty string")
                step = ""
            bid = source.get("branch")
            if not is_text(bid) or not bid:
                self.err(path + ".branch", "must be a non-empty string")
                return None
            branch = self.branches.get(bid)
            if branch is None:
                self.err(path + ".branch", f"unknown branch {bid!r}")
                return None
            if step and branch["step"] != step:
                self.err(path + ".step", f"does not match branch {bid!r} step {branch['step']!r}")
            if file and rel_path(branch["scene"]) != rel_path(file):
                self.err(path + ".file", f"does not match branch {bid!r} scene")
            if not is_int(locid) or locid != branch["locid"]:
                self.err(path + ".locid", f"does not match branch {bid!r} choice_locid")
            if fact is not None and fact not in branch["sets"]:
                self.err(path, f"branch {bid!r} does not set {fact!r}")
            return {"kind": kind, "step": branch["step"], "file": branch["scene"],
                    "locid": branch["locid"], "branch": bid, "sets": branch["sets"]}
        # scene_line / journal_objective: player-facing text with no fact-setting branch
        if not is_text(step) or not step:
            self.err(path + ".step", "must be a non-empty string")
        elif self.route_ids and step not in self.route_ids:
            self.err(path + ".step", f"unknown route step {step!r}")
        if not is_int(locid) or locid <= 0:
            self.err(path + ".locid", "must be a positive integer")
            locid = 0
        if locid and not (REDKIT_R4 / file).exists():
            self.err(path + ".file", f"does not exist under REDkit: {file!r}")
        if kind == "scene_line" and locid and self.scene_resource(locid) and rel_path(self.scene_resource(locid)) != rel_path(file):
            self.err(path + ".file", f"string-database resource for locId {locid} is not {file!r}")
        if kind == "journal_objective" and locid:
            titles = self.objective_titles(file)
            if titles is None:
                self.err(path + ".file", f"journal file not found under REDkit: {file!r}")
            elif locid not in titles:
                self.err(path + ".locid", f"{locid} is not an objective title in {file!r}")
        if fact is not None:
            self.err(path, f"a {kind} cannot be the source of a required fact")
        return {"kind": kind, "step": step if is_text(step) else "", "file": file, "locid": locid}

    # ---------------------------------------------------------------- checks

    def check_journal_outcome(self, value, path):
        if not isinstance(value, dict):
            self.err(path, "must be an object")
            return
        for key in sorted(set(value) - JOURNAL_KEYS):
            self.err(path, f"unknown key {key!r}")
        for key in sorted(JOURNAL_KEYS - set(value)):
            self.err(path, f"missing required key {key!r}")
        file = value.get("file")
        locid = value.get("locid")
        base = value.get("base_name")
        if not is_text(file) or not file:
            self.err(path + ".file", "must be a non-empty string")
            return
        if not is_int(locid) or locid <= 0:
            self.err(path + ".locid", "must be a positive integer")
            return
        if not is_text(base) or not base:
            self.err(path + ".base_name", "must be a non-empty string")
        entries = self.journal_entries(file)
        if entries is None:
            self.err(path + ".file", f"journal file not found under REDkit: {file!r}")
            return
        if locid not in entries:
            self.err(path + ".locid", f"{locid} is not a description entry in {file!r}")
            return
        if is_text(base) and entries[locid] != base:
            self.err(path + ".base_name", f"is {entries[locid]!r} in the journal, not {base!r}")
        if self.strings is not None and not self.strings.text(locid):
            self.err(path + ".locid", f"locId {locid} has no text in the string database")

    def check_outcome(self, oid, outcome):
        path = f"outcomes.{oid}"
        if not isinstance(outcome, dict):
            self.err(path, "must be an object")
            return
        for key in sorted(set(outcome) - OUTCOME_KEYS):
            self.err(path, f"unknown key {key!r}")
        if not ID.fullmatch(oid):
            self.err(path, "outcome id must match ^[a-z][a-z0-9_]{2,63}$")
        group = outcome.get("group")
        if not is_text(group) or group not in self.groups:
            self.err(path + ".group", f"unknown group {group!r}")
            group = None
        pack = outcome.get("pack")
        if pack not in PACKS:
            self.err(path + ".pack", f"must be one of {', '.join(PACKS)}")
        elif group is not None and pack != self.groups[group]["pack"]:
            self.err(path + ".pack", f"does not match group {group!r} pack")
        label = outcome.get("label")
        if not is_text(label) or not label.strip():
            self.err(path + ".label", "must be a non-empty string")
            label = None
        else:
            if label != label.strip():
                self.err(path + ".label", "must not have leading or trailing whitespace")
            if len(label) > 80:
                self.err(path + ".label", "must be 1-80 characters")
            if label.endswith("."):
                self.err(path + ".label", "must not end with a period")
        if outcome.get("spoiler") is not True:
            self.err(path + ".spoiler", "must be true")
        if not valid_date(outcome.get("reviewed")):
            self.err(path + ".reviewed", "must be a real YYYY-MM-DD date")
        if not is_text(outcome.get("review_note")) or not outcome.get("review_note", "").strip():
            self.err(path + ".review_note", "must be a non-empty string")

        requires = outcome.get("requires")
        if not isinstance(requires, list) or not requires:
            self.err(path + ".requires", "must be a non-empty list")
            requires = []
        guidance = outcome.get("guidance")
        if not isinstance(guidance, list):
            self.err(path + ".guidance", "must be a list")
            guidance = []
        status = outcome.get("guidance_status")
        if status not in ("guided", "not_guided_yet"):
            self.err(path + ".guidance_status", "must be guided or not_guided_yet")
            status = None
        reason = outcome.get("guidance_reason")
        if status == "guided":
            if "guidance_reason" in outcome:
                self.err(path + ".guidance_reason", "must not be present on a guided outcome")
            if not guidance:
                self.err(path + ".guidance", "a guided outcome needs at least one row")
        elif status == "not_guided_yet":
            if guidance:
                self.err(path + ".guidance", "must be empty when not guided")
            if not is_text(reason) or not reason.strip():
                self.err(path + ".guidance_reason", "required and non-empty when not guided")

        facts = []
        for i, row in enumerate(requires):
            p = f"{path}.requires[{i}]"
            if not isinstance(row, dict):
                self.err(p, "must be an object")
                continue
            for key in sorted(set(row) - REQUIRE_KEYS):
                self.err(p, f"unknown key {key!r}")
            for key in sorted(REQUIRE_KEYS - set(row)):
                self.err(p, f"missing required key {key!r}")
            fact = row.get("fact")
            if not is_text(fact) or not FACT.fullmatch(fact):
                self.err(p + ".fact", "must match ^[a-z][a-z0-9_]{3,}$")
                fact = None
            elif fact in facts:
                self.err(p + ".fact", f"duplicate required fact {fact!r}")
            if not isinstance(row.get("value"), bool):
                self.err(p + ".value", "must be true or false")
            source = self.check_source(row.get("source"), p + ".source", fact=fact)
            if fact is not None and source is not None and source["kind"] == "phase_fact":
                if source.get("fact") != fact:
                    self.err(p + ".source.fact", "must equal the requirement fact")
            if fact is not None:
                facts.append(fact)
        if facts != sorted(facts):
            self.err(path + ".requires", "rows must be sorted by fact ascending")

        covered = set()
        guidance_rows = []
        for i, row in enumerate(guidance):
            p = f"{path}.guidance[{i}]"
            if not isinstance(row, dict):
                self.err(p, "must be an object")
                continue
            for key in sorted(set(row) - GUIDANCE_KEYS):
                self.err(p, f"unknown key {key!r}")
            for key in sorted(GUIDANCE_KEYS - set(row) - {"branch"}):
                self.err(p, f"missing required key {key!r}")
            step = row.get("step")
            if not is_text(step) or not step:
                self.err(p + ".step", "must be a non-empty string")
                step = ""
            elif self.route_ids and step not in self.route_ids:
                self.err(p + ".step", f"unknown route step {step!r}")
            kind = row.get("kind")
            if kind not in ("scene_choice", "scene_line", "journal_objective"):
                self.err(p + ".kind", "must be scene_choice, scene_line or journal_objective")
                kind = None
            instruction = row.get("instruction")
            if not is_text(instruction) or not instruction.strip():
                self.err(p + ".instruction", "must be a non-empty string")
                instruction = None
            elif self.strings is not None:
                source = row.get("source") if isinstance(row.get("source"), dict) else {}
                locid = source.get("locid")
                if is_int(locid) and locid > 0:
                    text = self.strings.text(locid)
                    if text and norm(instruction) != norm(text):
                        self.err(p + ".instruction",
                                 f"must equal the string-database text for locId {locid}")
            facts_row = row.get("facts")
            if not isinstance(facts_row, list) or any(not is_text(f) for f in facts_row):
                self.err(p + ".facts", "must be a list of fact strings")
                facts_row = []
            for f in facts_row:
                if f not in facts:
                    self.err(p + ".facts", f"fact {f!r} is not a requirement of this outcome")
            branch = row.get("branch")
            if kind == "scene_choice":
                if not is_text(branch) or not branch:
                    self.err(p + ".branch", "a scene_choice row needs a branch")
            elif kind in ("scene_line", "journal_objective") and branch not in (None, ""):
                self.err(p + ".branch", f"a {kind} row must not name a branch")
            source = row.get("source")
            resolved = self.check_source(source, p + ".source")
            if kind == "scene_choice" and resolved is not None:
                if resolved.get("kind") != "scene_choice":
                    self.err(p + ".source.kind", "must be scene_choice for this row")
                elif is_text(branch) and resolved.get("branch") != branch:
                    self.err(p + ".branch", "does not match the source branch")
                for f in facts_row:
                    if f not in resolved.get("sets", set()):
                        self.err(p + ".facts", f"source branch does not set {f!r}")
            if kind in ("scene_line", "journal_objective") and resolved is not None:
                if resolved.get("kind") != kind:
                    self.err(p + ".source.kind", f"must be {kind} for this row")
                if facts_row:
                    self.err(p + ".facts", f"a {kind} row cannot set a fact")
            if not is_text(row.get("mechanism")) or not row.get("mechanism", "").strip():
                self.err(p + ".mechanism", "must be a non-empty string")
            covered.update(facts_row)
            guidance_rows.append((self.route_index.get(step, len(self.route_ids) + 1),
                                  str(branch or ""), i))
        if guidance_rows != sorted(guidance_rows):
            self.err(path + ".guidance", "rows must be sorted by route order, then branch")
        if status == "guided":
            for i, row in enumerate(requires):
                source = row.get("source") if isinstance(row, dict) else None
                if (isinstance(source, dict) and source.get("kind") == "scene_choice"
                        and row.get("value") is True and row.get("fact") not in covered):
                    self.err(f"{path}.requires[{i}]",
                             "a positive scene_choice fact needs a guidance row that sets it")

        journal = outcome.get("journal_outcome")
        self.check_journal_outcome(journal, path + ".journal_outcome")

    def check_groups(self):
        for gid, group in self.groups.items():
            path = f"groups.{gid}"
            if not ID.fullmatch(gid):
                self.err(path, "group id must match ^[a-z][a-z0-9_]{2,63}$")
            if not isinstance(group, dict):
                self.err(path, "must be an object")
                continue
            for key in sorted(set(group) - GROUP_KEYS):
                self.err(path, f"unknown key {key!r}")
            for key in sorted(GROUP_KEYS - set(group)):
                self.err(path, f"missing required key {key!r}")
            if group.get("pack") not in PACKS:
                self.err(path + ".pack", f"must be one of {', '.join(PACKS)}")
            if not is_text(group.get("label")) or not group.get("label", "").strip():
                self.err(path + ".label", "must be a non-empty string")
            if group.get("selection") != "one":
                self.err(path + ".selection", "must be 'one' in v1")
            members = group.get("outcomes")
            if not isinstance(members, list) or len(members) < 2:
                self.err(path + ".outcomes", "must list at least two outcomes")
                continue
            if len(set(members)) != len(members):
                self.err(path + ".outcomes", "must not contain duplicates")
            for oid in members:
                if not is_text(oid):
                    self.err(path + ".outcomes", "must contain outcome id strings")
                    continue
                outcome = self.outcomes.get(oid)
                if not isinstance(outcome, dict):
                    self.err(path + ".outcomes", f"unknown outcome {oid!r}")
                elif outcome.get("group") != gid:
                    self.err(path + ".outcomes", f"outcome {oid!r} names group {outcome.get('group')!r}")

    def check_targets(self):
        if not self.targets:
            self.err("targets", "endings.json has no targets", where="endings.json")
            return
        recommended = {}
        doc = self.load_json(self.endings_path, "endings.json") if self.endings_path.exists() else {}
        presets = doc.get("presets") if isinstance(doc, dict) else {}
        if isinstance(presets, dict) and isinstance(presets.get("recommended"), dict):
            recommended = presets["recommended"]
        rec_targets = recommended.get("targets") if isinstance(recommended, dict) else None
        if not isinstance(rec_targets, list) or not rec_targets:
            self.err("presets.recommended.targets", "must be a non-empty list", where="endings.json")
            rec_targets = []
        covered_groups = {}
        for tid, target in self.targets.items():
            if not isinstance(target, dict):
                continue
            oid = target.get("outcome")
            if oid is None:
                continue
            if not is_text(oid) or oid not in self.outcomes:
                self.err(f"targets.{tid}.outcome", f"unknown outcome {oid!r}", where="endings.json")
                continue
            outcome = self.outcomes[oid]
            if target.get("pack") != outcome.get("pack"):
                self.err(f"targets.{tid}.pack",
                         f"does not match outcome pack {outcome.get('pack')!r}", where="endings.json")
            if target.get("guidance_status") != outcome.get("guidance_status"):
                self.err(f"targets.{tid}.guidance_status",
                         f"does not match outcome status {outcome.get('guidance_status')!r}",
                         where="endings.json")
            if tid in rec_targets:
                if outcome.get("guidance_status") != "guided":
                    self.err(f"presets.recommended.targets",
                             f"{tid!r} is not guided", where="endings.json")
                covered_groups.setdefault(outcome.get("group"), []).append(tid)
        for gid in self.groups:
            got = covered_groups.get(gid, [])
            if len(got) != 1:
                self.err("presets.recommended.targets",
                         f"must cover group {gid!r} exactly once; found {len(got)}", where="endings.json")

    def check_edges(self):
        if not self.exclusive_path.exists():
            self.err("file", f"not found ({self.exclusive_path})", where="exclusive.json")
            return
        doc = self.load_json(self.exclusive_path, "exclusive.json")
        edges = doc.get("edges") if isinstance(doc, dict) else None
        if not isinstance(edges, list):
            self.err("edges", "must be a list", where="exclusive.json")
            return
        seen = set()
        for i, edge in enumerate(edges):
            p = f"edges[{i}]"
            if not isinstance(edge, dict):
                self.err(p, "must be an object", where="exclusive.json")
                continue
            for key in sorted(set(edge) - EDGE_KEYS):
                self.err(p, f"unknown key {key!r}", where="exclusive.json")
            for key in sorted(EDGE_KEYS - set(edge)):
                self.err(p, f"missing required key {key!r}", where="exclusive.json")
            kind = edge.get("kind")
            if kind not in ("outcome", "target"):
                self.err(p + ".kind", "must be outcome or target", where="exclusive.json")
                continue
            a, b = edge.get("a"), edge.get("b")
            if not is_text(a) or not is_text(b) or not a or not b or a == b:
                self.err(p, "a and b must be distinct non-empty strings", where="exclusive.json")
                continue
            pair = tuple(sorted((a, b)))
            if pair in seen:
                self.err(p, "duplicate exclusion edge", where="exclusive.json")
            seen.add(pair)
            if kind == "outcome":
                for name, oid in (("a", a), ("b", b)):
                    if oid not in self.outcomes:
                        self.err(f"{p}.{name}", f"unknown outcome {oid!r}", where="exclusive.json")
            else:
                for name, tid in (("a", a), ("b", b)):
                    if tid not in self.targets:
                        self.err(f"{p}.{name}", f"unknown target {tid!r}", where="exclusive.json")
            if not is_text(edge.get("reason")) or not edge.get("reason", "").strip():
                self.err(p + ".reason", "must be a non-empty string", where="exclusive.json")
            if not is_text(edge.get("mechanism")) or not edge.get("mechanism", "").strip():
                self.err(p + ".mechanism", "must be a non-empty string", where="exclusive.json")
            evidence = edge.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                self.err(p + ".evidence", "must be a non-empty list", where="exclusive.json")
                continue
            for j, ev in enumerate(evidence):
                q = f"{p}.evidence[{j}]"
                if not isinstance(ev, dict):
                    self.err(q, "must be an object", where="exclusive.json")
                    continue
                for key in sorted(set(ev) - EVIDENCE_KEYS):
                    self.err(q, f"unknown key {key!r}", where="exclusive.json")
                ek = ev.get("kind")
                val = ev.get("value")
                if ek == "branch":
                    if not is_text(val) or val not in self.branches:
                        self.err(q, f"unknown branch {val!r}", where="exclusive.json")
                elif ek == "file":
                    if not is_text(val) or not (REDKIT_R4 / val).exists():
                        self.err(q, f"file not found under REDkit: {val!r}", where="exclusive.json")
                elif ek == "locid":
                    if not is_int(val) or val <= 0 or (self.strings and not self.strings.text(val)):
                        self.err(q, f"locId {val!r} has no text", where="exclusive.json")
                else:
                    self.err(q + ".kind", "must be branch, file or locid", where="exclusive.json")
            self.edges.append(edge)
        self.counts["edges"] = len(edges)

        if self.release:
            if not edges:
                self.err("edges", "must contain at least one reviewed edge in a release check",
                         where="exclusive.json")
            for gid, group in self.groups.items():
                members = group.get("outcomes") if isinstance(group, dict) else []
                for a, b in itertools.combinations(members if isinstance(members, list) else [], 2):
                    if tuple(sorted((a, b))) not in seen:
                        self.err("edges", f"group {gid!r} is missing an edge between {a!r} and {b!r}",
                                 where="exclusive.json")

    def check_document(self, doc):
        self.check_placeholders(doc)
        for key in sorted(set(doc) - {"version", "note", "groups", "outcomes"}):
            self.err(str(key), f"unknown key {key!r}")
        if doc.get("version") != 1:
            self.err("version", "must be 1")
        if not is_text(doc.get("note")):
            self.err("note", "must be a string")
        groups = doc.get("groups")
        if not isinstance(groups, dict):
            self.err("groups", "must be an object keyed by group id")
            groups = {}
        outcomes = doc.get("outcomes")
        if not isinstance(outcomes, dict):
            self.err("outcomes", "must be an object keyed by outcome id")
            outcomes = {}
        self.groups = groups
        self.outcomes = outcomes
        self.counts["groups"] = len(groups)
        self.counts["outcomes"] = len(outcomes)
        self.check_groups()
        for oid, outcome in outcomes.items():
            self.check_outcome(oid, outcome)
            if isinstance(outcome, dict):
                self.counts["guided" if outcome.get("guidance_status") == "guided" else "pending"] += 1

        # Every group outcome must exist and every outcome must be in exactly one group.
        placed = {}
        for gid, group in groups.items():
            members = group.get("outcomes") if isinstance(group, dict) else []
            for oid in members if isinstance(members, list) else []:
                if oid in placed:
                    self.err(f"groups.{gid}.outcomes", f"outcome {oid!r} is also in {placed[oid]!r}")
                placed[oid] = gid
        for oid in outcomes:
            if oid not in placed:
                self.err(f"outcomes.{oid}", "is not listed in any group")

        self.check_targets()
        self.check_edges()
        self.counts["targets"] = sum(1 for t in self.targets.values()
                                     if isinstance(t, dict) and is_text(t.get("outcome")))

    def run(self):
        doc = self.load_outcomes()
        if doc is None:
            return False
        self.loaded = True
        self.load_endings()
        self.load_branches()
        self.load_route()
        self.load_quest_index()
        self.load_facts()
        self.load_strings()
        self.check_document(doc)
        return self.ok


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", action="store_true",
                        help="also require a reviewed edge for every pair in each group")
    parser.add_argument("--outcomes", type=Path, default=TRACKER / "data" / "outcomes.json")
    parser.add_argument("--endings", type=Path, default=TRACKER / "data" / "endings.json")
    parser.add_argument("--branches", type=Path, default=TRACKER / "data" / "branches.json")
    parser.add_argument("--route", type=Path, default=TRACKER / "data" / "route.json")
    parser.add_argument("--quest-index", type=Path, default=endings.default_quest_index())
    parser.add_argument("--exclusive", type=Path, default=TRACKER / "data" / "exclusive.json")
    parser.add_argument("--fact-index", type=Path, default=HERE / "fact_index.json")
    parser.add_argument("--string-db", type=Path, default=STRING_DB)
    args = parser.parse_args(argv)

    checker = Checker(args.outcomes, args.endings, args.branches, args.route, args.quest_index,
                      args.exclusive, args.fact_index, args.string_db, release=args.release)
    checker.run()
    warnings, errors = checker.warnings, checker.errors
    checker.close()
    for warning in warnings:
        print(f"warning: {warning}")
    for error in errors:
        print(f"error: {error}")
    if errors:
        print(f"{len(errors)} problem(s); outcomes.json is not shippable")
        return 1
    c = checker.counts
    print(f"outcomes ok: {c['groups']} group(s), {c['outcomes']} outcome(s), "
          f"{c['guided']} guided, {c['pending']} not guided yet, {c['targets']} target(s), "
          f"{c['edges']} exclusion edge(s); {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
