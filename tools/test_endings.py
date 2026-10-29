"""Positive and negative fixtures for `tools/endings.py`.

The base fixture under `tools/fixtures/endings/base/` is a small, internally consistent
`endings.json` + `branches.json` + `route.json` + `quest_index.json` + `coverage.json` set. Every
negative case starts from that document and changes one thing, so a failure names the rule it is
meant to test rather than a pile of unrelated errors.

The string database is a temporary SQLite file with the same `STRINGS` table `stringsdb.py` reads,
so exact-line checks do not need the game install.

  py tools/test_endings.py -v
"""
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE / "fixtures" / "endings" / "base"
sys.path.insert(0, str(HERE))
import endings


def base_json(name):
    return json.loads((BASE / name).read_text(encoding="utf-8"))


def target(doc, tid="test_heirs_live"):
    return doc["targets"][tid]


def pending(doc):
    return doc["targets"]["test_heirs_pending"]


def guidance(doc, i=0):
    return target(doc)["guidance"][i]


def requirement(doc, i=0):
    return target(doc)["requires"][i]


class EndingsCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.endings_path = self.dir / "endings.json"
        self.branches_path = self.dir / "branches.json"
        self.route_path = self.dir / "route.json"
        self.quest_index_path = self.dir / "quest_index.json"
        self.exclusive_path = self.dir / "exclusive.json"
        self.coverage_path = self.dir / "coverage.json"
        self.db_path = self.dir / "strings.db"
        for name in ("endings.json", "branches.json", "route.json", "quest_index.json",
                     "exclusive.json", "coverage.json"):
            shutil.copyfile(BASE / name, self.dir / name)
        self.make_strings_db()

    def tearDown(self):
        self.tmp.cleanup()

    # ------------------------------------------------------------------ helpers

    def make_strings_db(self):
        con = sqlite3.connect(self.db_path)
        con.execute("create table STRINGS (STRING_ID integer, LANG integer, TEXT text)")
        con.executemany("insert into STRINGS (STRING_ID, LANG, TEXT) values (?, 2, ?)",
                        [(900001, "Let them both live."), (900002, "Spare the guard.")])
        con.commit()
        con.close()

    def set_string(self, locid, text):
        con = sqlite3.connect(self.db_path)
        con.execute("update STRINGS set TEXT=? where STRING_ID=?", (text, locid))
        con.commit()
        con.close()

    def base_doc(self):
        return base_json("endings.json")

    def write_json(self, path, value):
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def check(self, doc=None, release=False, allow_missing=False):
        if doc is not None:
            self.write_json(self.endings_path, doc)
        checker = endings.Checker(
            self.endings_path, self.branches_path, self.route_path, self.quest_index_path,
            self.exclusive_path, self.coverage_path, self.db_path,
            release=release, allow_missing_endings=allow_missing,
        )
        checker.run()
        checker.close()
        return checker

    def assert_error(self, checker, needle):
        self.assertFalse(checker.ok, f"expected a failure containing {needle!r}; got {checker.errors}")
        self.assertTrue(any(needle in e for e in checker.errors),
                        f"expected {needle!r} in:\n" + "\n".join(checker.errors))

    # ------------------------------------------------------------------ valid

    def test_valid_fixture(self):
        checker = self.check()
        self.assertEqual(checker.errors, [])
        self.assertEqual(checker.warnings, [])
        self.assertEqual(checker.counts, {"targets": 2, "guided": 1, "pending": 1, "presets": 1})

    def test_valid_release_fixture(self):
        checker = self.check(release=True)
        self.assertEqual(checker.errors, [])
        self.assertEqual(checker.warnings, [])

    def test_pending_only_needs_no_branches(self):
        doc = base_json("endings.json")
        del doc["targets"]["test_heirs_live"]
        doc["presets"]["recommended"]["targets"] = ["test_heirs_pending"]
        self.branches_path.unlink()
        checker = self.check(doc)
        self.assertEqual(checker.errors, [])

    def test_empty_targets_is_valid_before_review(self):
        doc = {"version": 1, "note": "No target reviewed yet.", "targets": {}, "presets": {}}
        checker = self.check(doc)
        self.assertEqual(checker.errors, [])
        self.assertTrue(any("no targets" in w for w in checker.warnings))

    def test_empty_targets_fails_release(self):
        doc = {"version": 1, "note": "No target reviewed yet.", "targets": {}, "presets": {}}
        checker = self.check(doc, release=True)
        self.assert_error(checker, "at least one target")

    def test_recommended_preset_is_release_only(self):
        doc = self.base_doc()
        doc["presets"] = {}
        self.assertEqual(self.check(doc).errors, [])
        self.assert_error(self.check(doc, release=True), "recommended preset")

    def test_nfc_and_trim_normalize_the_instruction(self):
        self.set_string(900001, "Cafe\u0301 scene line")
        doc = base_json("endings.json")
        guidance(doc)["instruction"] = "Caf\u00e9 scene line"
        checker = self.check(doc)
        self.assertEqual(checker.errors, [])

    def test_cli(self):
        result = subprocess.run(
            [sys.executable, str(HERE / "endings.py"), "check",
             "--endings", str(self.endings_path), "--branches", str(self.branches_path),
             "--route", str(self.route_path), "--quest-index", str(self.quest_index_path),
             "--exclusive", str(self.exclusive_path), "--coverage", str(self.coverage_path),
             "--string-db", str(self.db_path)],
            cwd=str(HERE), text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("endings ok", result.stdout)

        result = subprocess.run(
            [sys.executable, str(HERE / "endings.py"), "check", "--release",
             "--endings", str(self.endings_path), "--branches", str(self.branches_path),
             "--route", str(self.route_path), "--quest-index", str(self.quest_index_path),
             "--exclusive", str(self.exclusive_path), "--coverage", str(self.coverage_path),
             "--string-db", str(self.db_path)],
            cwd=str(HERE), text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("endings ok", result.stdout)

    # ------------------------------------------------------------------ file basics

    def test_invalid_json(self):
        self.endings_path.write_text("{", encoding="utf-8")
        checker = self.check()
        self.assert_error(checker, "invalid JSON")

    def test_duplicate_json_key(self):
        self.endings_path.write_text(
            '{"version": 1, "version": 1, "note": "x", "targets": {}, "presets": {}}',
            encoding="utf-8")
        checker = self.check()
        self.assert_error(checker, "duplicate object key")

    def test_missing_explicit_endings_file(self):
        self.endings_path.unlink()
        checker = self.check(allow_missing=False)
        self.assert_error(checker, "not found")

    def test_missing_default_endings_file_is_allowed_before_review(self):
        self.endings_path.unlink()
        checker = self.check(allow_missing=True)
        self.assertEqual(checker.errors, [])
        self.assertTrue(any("not found" in w for w in checker.warnings))

    # ------------------------------------------------------------------ warnings

    def test_exclusive_pair_is_a_warning_not_a_drop(self):
        doc = base_json("endings.json")
        doc["presets"]["recommended"]["targets"] = ["test_heirs_live", "test_heirs_pending"]
        self.write_json(self.exclusive_path, {"version": 1, "edges": [
            {"a": "target:test_heirs_live", "b": "target:test_heirs_pending", "kind": "target"},
        ]})
        checker = self.check(doc)
        self.assertEqual(checker.errors, [])
        self.assertTrue(any("exclusive" in w for w in checker.warnings))

    def test_missing_coverage_pack_is_a_warning(self):
        coverage = base_json("coverage.json")
        del coverage["packs"]["bob"]
        self.write_json(self.coverage_path, coverage)
        checker = self.check()
        self.assertEqual(checker.errors, [])
        self.assertTrue(any("coverage row" in w for w in checker.warnings))

    def test_missing_coverage_file_is_a_warning(self):
        self.coverage_path.unlink()
        checker = self.check()
        self.assertEqual(checker.errors, [])
        self.assertTrue(any("coverage" in w for w in checker.warnings))

    # ------------------------------------------------------------------ input failures

    def test_guided_target_needs_branches(self):
        self.branches_path.unlink()
        checker = self.check()
        self.assert_error(checker, "branches.json")

    def test_guided_target_needs_the_string_database(self):
        self.db_path.unlink()
        checker = self.check()
        self.assert_error(checker, "exact instructions cannot be checked")

    def test_locid_without_string_text_fails(self):
        branches = base_json("branches.json")
        choice = branches["branches"]["test_step_heirs"]["choices"][0]
        choice["choice_locid"] = 900099
        self.write_json(self.branches_path, branches)
        doc = base_json("endings.json")
        requirement(doc)["source"]["locid"] = 900099
        guidance(doc)["source"]["locid"] = 900099
        checker = self.check(doc)
        self.assert_error(checker, "no text in the string database")

    def test_branch_file_version_is_optional_for_a_minimal_graph(self):
        branches = base_json("branches.json")
        del branches["version"]
        self.write_json(self.branches_path, branches)
        checker = self.check()
        self.assertEqual(checker.errors, [])

    def test_branch_id_colliding_with_a_target_fails(self):
        branches = base_json("branches.json")
        branches["branches"]["test_step_heirs"]["choices"][0]["id"] = "test_heirs_live"
        self.write_json(self.branches_path, branches)
        checker = self.check()
        self.assert_error(checker, "collides with target id")

    def test_duplicate_branch_id_fails(self):
        branches = base_json("branches.json")
        branches["branches"]["test_step_guard"]["choices"].append(
            deepcopy(branches["branches"]["test_step_heirs"]["choices"][0]))
        self.write_json(self.branches_path, branches)
        checker = self.check()
        self.assert_error(checker, "duplicate branch id")

    def test_fixture_target_ids_are_allowed_before_release(self):
        doc = self.base_doc()
        extra = deepcopy(doc["targets"]["test_heirs_pending"])
        extra["label"] = "A test-only pending target"
        doc["targets"]["fixture_demo"] = extra
        checker = self.check(doc)
        self.assertEqual(checker.errors, [])

    def test_release_rejects_fixture_target_ids(self):
        doc = self.base_doc()
        extra = deepcopy(doc["targets"]["test_heirs_pending"])
        extra["label"] = "A test-only pending target"
        doc["targets"]["fixture_demo"] = extra
        checker = self.check(doc, release=True)
        self.assert_error(checker, "fixture_")

    # ------------------------------------------------------------------ negative table

    def test_negative_cases(self):
        def top(key, value):
            return lambda d: d.__setitem__(key, value)

        def drop_top(key):
            return lambda d: d.pop(key)

        def set_target(key, value):
            return lambda d: target(d).__setitem__(key, value)

        def drop_target(key):
            return lambda d: target(d).pop(key)

        def add_target(key, value):
            return lambda d: d["targets"].__setitem__(key, value)

        def set_req(i, key, value):
            return lambda d: requirement(d, i).__setitem__(key, value)

        def set_req_source(i, key, value):
            return lambda d: requirement(d, i)["source"].__setitem__(key, value)

        def set_guide(i, key, value):
            return lambda d: guidance(d, i).__setitem__(key, value)

        def set_guide_source(i, key, value):
            return lambda d: guidance(d, i)["source"].__setitem__(key, value)

        def swap_requires(d):
            target(d)["requires"].reverse()

        def swap_guidance(d):
            target(d)["guidance"].reverse()

        cases = [
            ("wrong version", top("version", 2), "version"),
            ("unknown top-level key", top("extra", 1), "unknown key"),
            ("missing note", drop_top("note"), "note"),
            ("targets not an object", top("targets", []), "targets"),
            ("presets not an object", top("presets", []), "presets"),
            ("target not an object", lambda d: d["targets"].__setitem__("test_heirs_live", "x"),
             "must be an object"),
            ("missing label", drop_target("label"), "label"),
            ("label ends with a period", set_target("label", "Both heirs live."), "period"),
            ("label too long", set_target("label", "x" * 81), "1-80"),
            ("unknown target key", set_target("extra", 1), "unknown key"),
            ("bad pack", set_target("pack", "bw"), "pack"),
            ("spoiler false", set_target("spoiler", False), "spoiler"),
            ("bad reviewed date", set_target("reviewed", "2026-02-30"), "reviewed"),
            ("duplicate target label",
             lambda d: pending(d).__setitem__("label", target(d)["label"]), "duplicate target label"),
            ("guided target without requirements", set_target("requires", []), "at least one row"),
            ("guided target without guidance", set_target("guidance", []), "at least one row"),
            ("requirements not a list", set_target("requires", {}), "must be a list"),
            ("guidance not a list", set_target("guidance", {}), "must be a list"),
            ("unknown guidance status", set_target("guidance_status", "maybe"), "guidance_status"),
            ("guidance_reason on a guided target", set_target("guidance_reason", "why"), "guidance_reason"),
            ("pending target with requirements",
             lambda d: pending(d).__setitem__("requires", [deepcopy(requirement(d))]), "must be empty"),
            ("pending target with guidance",
             lambda d: pending(d).__setitem__("guidance", [deepcopy(guidance(d))]), "must be empty"),
            ("pending target without a reason", lambda d: pending(d).pop("guidance_reason"), "guidance_reason"),
            ("requirement value false", set_req(0, "value", False), "value"),
            ("requirement value 1", set_req(0, "value", 1), "value"),
            ("requirement fact with whitespace", set_req(0, "fact", "bad fact"), "whitespace"),
            ("duplicate requirement fact", set_req(1, "fact", "test_heirs_live_fact"), "duplicate required fact"),
            ("requirements not sorted", swap_requires, "sorted by fact"),
            ("requirement source kind", set_req_source(0, "kind", "fact"), "scene_choice"),
            ("requirement source missing", lambda d: requirement(d).pop("source"), "source"),
            ("requirement source not an object", set_req(0, "source", "x"), "must be an object"),
            ("requirement locid zero", set_req_source(0, "locid", 0), "positive integer"),
            ("requirement locid string", set_req_source(0, "locid", "900001"), "positive integer"),
            ("requirement step unknown", set_req_source(0, "step", "nope"), "unknown route step"),
            ("requirement branch unknown", set_req_source(0, "branch", "nope"), "unknown branch"),
            ("requirement file mismatch", set_req_source(0, "file", "quests\\other.w2scene"), "does not match"),
            ("requirement locid mismatch", set_req_source(0, "locid", 900002), "does not match"),
            ("requirement fact not set by branch", set_req(0, "fact", "test_other_fact"), "does not set"),
            ("duplicate guidance step", set_guide(1, "step", "test_step_heirs"), "duplicate guidance step"),
            ("guidance step unknown", set_guide(0, "step", "nope"), "unknown route step"),
            ("guidance branch unknown", set_guide(0, "branch", "nope"), "unknown branch"),
            ("guidance source has step", lambda d: guidance(d)["source"].__setitem__("step", "x"),
             "unknown key"),
            ("guidance source not an object", set_guide(0, "source", "x"), "must be an object"),
            ("guidance source file mismatch",
             set_guide_source(0, "file", "quests\\other.w2scene"), "does not match"),
            ("guidance source locid mismatch", set_guide_source(0, "locid", 900002), "does not match"),
            ("guidance instruction is a paraphrase", set_guide(0, "instruction", "Keep both alive."),
             "must equal the string-database text"),
            ("guidance instruction empty", set_guide(0, "instruction", ""), "non-empty"),
            ("guidance rows not sorted", swap_guidance, "sorted by route order"),
            ("preset unknown target",
             lambda d: d["presets"]["recommended"].__setitem__("targets", ["nope"]), "unknown target"),
            ("preset empty", lambda d: d["presets"]["recommended"].__setitem__("targets", []),
             "at least one target"),
            ("preset targets not a list",
             lambda d: d["presets"]["recommended"].__setitem__("targets", {}), "must be a list"),
            ("preset target not a string",
             lambda d: d["presets"]["recommended"].__setitem__("targets", [1]),
             "target id string"),
            ("preset duplicate target",
             lambda d: d["presets"]["recommended"].__setitem__(
                 "targets", ["test_heirs_live", "test_heirs_live"]), "duplicate target"),
            ("preset bad date", lambda d: d["presets"]["recommended"].__setitem__("reviewed", "2026-02-30"),
             "reviewed"),
            ("preset unknown key", lambda d: d["presets"]["recommended"].__setitem__("extra", 1),
             "unknown key"),
            ("recommended label", lambda d: d["presets"]["recommended"].__setitem__("label", "Best endings"),
             "Recommended endings"),
            ("duplicate preset label",
             lambda d: d["presets"].__setitem__("other", {
                 "label": "Recommended endings", "targets": ["test_heirs_pending"],
                 "reviewed": "2026-10-28"}), "duplicate preset label"),
            ("placeholder token", top("note", "TODO later"), "placeholder token"),
            ("fixture token in a label", set_target("label", "FIXTURE ONLY both heirs"), "placeholder token"),
            ("target id pattern", add_target("Bad-ID", deepcopy(pending_from_base())), "target id must match"),
            ("target id equals a pack", add_target("bob", deepcopy(pending_from_base())), "pack code"),
            ("target id equals a route step",
             add_target("test_step_heirs", deepcopy(pending_from_base())), "route step"),
        ]

        for name, mutate, needle in cases:
            with self.subTest(name=name):
                doc = self.base_doc()
                mutate(doc)
                checker = self.check(doc)
                self.assert_error(checker, needle)


def pending_from_base():
    return base_json("endings.json")["targets"]["test_heirs_pending"]


if __name__ == "__main__":
    unittest.main()
