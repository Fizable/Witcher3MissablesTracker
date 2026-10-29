"""Negative fixtures for `matrixcheck.py`.

The valid case is the shipped data. Every other test changes one reviewed or generated thing in
memory and requires the checker to refuse it.

  py tools/test_matrix.py -v
"""
import copy
import json
import unittest

import matrixcheck as mc


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class MatrixCheckerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.route = load(mc.ROUTE)
        cls.idx = load(mc.INDEX)
        cls.ov = load(mc.OVERRIDES)
        cls.sec = load(mc.SECTIONS)
        cls.derived = load(mc.DERIVED)
        cls.coverage = load(mc.COVERAGE)
        cls.endings = load(mc.ENDINGS)
        cls.outcomes = load(mc.OUTCOMES)
        cls.exclusive = load(mc.EXCLUSIVE)
        cls.ui = mc.UI.read_text(encoding="utf-8")

    def audit(self, route=None, ov=None, derived=None, exclusive=None, ui=None, docs=None):
        return mc.audit(
            route or self.route, self.idx, ov or self.ov, self.sec,
            derived or self.derived, self.coverage, self.endings, self.outcomes,
            exclusive or self.exclusive, ui if ui is not None else self.ui, docs,
        )

    def assert_problem(self, problems, needle):
        self.assertTrue(any(needle in p for p in problems),
                        f"expected {needle!r} in:\n" + "\n".join(problems))

    def test_the_shipped_matrix_is_valid(self):
        self.assertEqual(self.audit(), [])

    def test_an_unlabelled_manual_step_is_rejected(self):
        route = copy.deepcopy(self.route)
        for n in route["nodes"]:
            if not n["files"]:
                n["provenance"] = ""
                break
        self.assert_problem(self.audit(route=route), "not labelled manual_reviewed")

    def test_a_manual_row_without_a_resolvable_source_is_rejected(self):
        route = copy.deepcopy(self.route)
        for n in route["nodes"]:
            if not n["files"]:
                n["review_source"] = "docs/MANUAL-STEPS-AUDIT.md#not-a-step"
                break
        self.assert_problem(self.audit(route=route), "no resolvable review source")

    def test_restoring_a_replaced_duplicate_is_rejected(self):
        route = copy.deepcopy(self.route)
        old = self.ov["manual_replaced"][0]
        route["nodes"].append({
            "section": "Secondary", "id": old["id"], "title": old["title"], "lv": "",
            "files": [], "hard": [], "hard_facts": {}, "by": [], "note": "", "kind": "manual",
            "opt": False, "when": [], "order": 0, "desc": "", "branch": False,
            "dialogue_choice": False, "ending_relevant": False, "start_known": False,
            "provenance": "manual_reviewed", "review_reason": "x",
            "review_source": old["review_source"], "reviewed": old["reviewed"],
        })
        self.assert_problem(self.audit(route=route), "is still in the route")

    def test_a_missing_derived_row_is_rejected(self):
        derived = copy.deepcopy(self.derived)
        removed = next(iter(derived["steps"]))
        del derived["steps"][removed]
        self.assert_problem(self.audit(derived=derived), "derived rows do not match")

    def test_a_chosen_target_joined_by_an_exclusive_edge_is_rejected(self):
        exclusive = copy.deepcopy(self.exclusive)
        exclusive["edges"].append({"kind": "outcome", "a": "ciri_witcher", "b": "olgierd_saved",
                                   "reason": "fixture"})
        self.assert_problem(self.audit(exclusive=exclusive), "exclusive edge")

    def test_a_missing_visible_manual_label_is_rejected(self):
        self.assert_problem(self.audit(ui="function render() {}"), "MANUAL REVIEWED")

    def test_a_stale_count_in_the_readme_is_rejected(self):
        docs = {p: p.read_text(encoding="utf-8") for p in mc.DOCS}
        readme = next(p for p in mc.DOCS if p.name == "README.md")
        docs[readme] = docs[readme].replace("412", "414")
        self.assert_problem(self.audit(docs=docs), "does not state 412")


if __name__ == "__main__":
    unittest.main()
