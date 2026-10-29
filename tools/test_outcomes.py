"""Negative fixtures for `outcomecheck.py`.

The valid case is the shipped data. Each other test copies the three reviewed files into a temporary
folder, changes one thing, and requires the checker to refuse it. The game files, route, branches,
fact index and string database stay real and read-only.

  py tools/test_outcomes.py -v
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import outcomecheck
from paths import HERE, STRING_DB, TRACKER


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


class OutcomeCheckerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.outcomes = self.dir / "outcomes.json"
        self.endings = self.dir / "endings.json"
        self.exclusive = self.dir / "exclusive.json"
        self.base_outcomes = load(TRACKER / "data" / "outcomes.json")
        self.base_endings = load(TRACKER / "data" / "endings.json")
        self.base_exclusive = load(TRACKER / "data" / "exclusive.json")
        self.write(self.base_outcomes, self.base_endings, self.base_exclusive)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, outcomes=None, endings_doc=None, exclusive=None):
        for path, value in (
            (self.outcomes, outcomes if outcomes is not None else self.base_outcomes),
            (self.endings, endings_doc if endings_doc is not None else self.base_endings),
            (self.exclusive, exclusive if exclusive is not None else self.base_exclusive),
        ):
            path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def check(self, release=False):
        checker = outcomecheck.Checker(
            self.outcomes, self.endings,
            TRACKER / "data" / "branches.json",
            TRACKER / "data" / "route.json",
            HERE / "quest_index.json",
            self.exclusive,
            HERE / "fact_index.json",
            STRING_DB,
            release=release,
        )
        checker.run()
        checker.close()
        return checker

    def assert_error(self, checker, needle):
        self.assertFalse(checker.ok, f"expected a failure containing {needle!r}; got {checker.errors}")
        self.assertTrue(any(needle in e for e in checker.errors),
                        f"expected {needle!r} in:\n" + "\n".join(checker.errors))

    def test_the_shipped_data_is_valid(self):
        checker = self.check(release=True)
        self.assertEqual(checker.errors, [])
        self.assertEqual(checker.counts, {"groups": 4, "outcomes": 11, "guided": 4,
                                          "pending": 7, "targets": 4, "edges": 11})

    def test_a_missing_journal_file_is_rejected(self):
        doc = json.loads(json.dumps(self.base_outcomes))
        doc["outcomes"]["baron_wife_cured"]["journal_outcome"]["file"] = "gameplay\\journal\\quests\\nope.journal"
        self.write(outcomes=doc)
        self.assert_error(self.check(), "journal file not found")

    def test_a_non_exact_line_is_rejected(self):
        doc = json.loads(json.dumps(self.base_outcomes))
        doc["outcomes"]["ciri_witcher"]["guidance"][0]["instruction"] = "Velen."
        self.write(outcomes=doc)
        self.assert_error(self.check(), "string-database text")

    def test_a_target_with_an_unknown_outcome_is_rejected(self):
        endings = json.loads(json.dumps(self.base_endings))
        endings["targets"]["bw_both_sisters"]["outcome"] = "nope"
        self.write(endings_doc=endings)
        self.assert_error(self.check(), "unknown outcome")

    def test_a_missing_group_edge_is_rejected_in_release(self):
        ex = json.loads(json.dumps(self.base_exclusive))
        ex["edges"] = [e for e in ex["edges"] if {e["a"], e["b"]} != {"baron_wife_cured", "baron_anna_burnt"}]
        self.write(exclusive=ex)
        self.assert_error(self.check(release=True), "missing an edge")

    def test_an_outcome_missing_from_its_group_is_rejected(self):
        doc = json.loads(json.dumps(self.base_outcomes))
        doc["groups"]["baron_family"]["outcomes"] = ["baron_wife_cured", "baron_anna_lost"]
        self.write(outcomes=doc)
        self.assert_error(self.check(), "not listed in any group")

    def test_an_outcome_pack_must_match_its_group(self):
        doc = json.loads(json.dumps(self.base_outcomes))
        doc["outcomes"]["olgierd_saved"]["pack"] = "base"
        self.write(outcomes=doc)
        self.assert_error(self.check(), "does not match group")

    def test_a_negative_fact_must_come_from_a_real_setter(self):
        doc = json.loads(json.dumps(self.base_outcomes))
        doc["outcomes"]["olgierd_dead"]["requires"][0]["source"]["fact"] = "no_such_fact"
        self.write(outcomes=doc)
        self.assert_error(self.check(), "no set row")


if __name__ == "__main__":
    unittest.main()
