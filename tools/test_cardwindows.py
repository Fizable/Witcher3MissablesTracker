"""Tests for the card-window checker itself.

These are deliberately mutation tests: a checker that cannot fail is not a gate. They use the
shipped generated files read-only and mutate an in-memory copy.
"""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cardwindows


class CardWindowCheckerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = cardwindows.load_json(cardwindows.CARDS)
        cls.report = cardwindows.load_json(cardwindows.OUT)
        cls.review = cardwindows.load_review()
        cls.route = set(cardwindows.route_titles())

    def validate(self, doc, report):
        return cardwindows.validate(doc, report, self.review, self.route)[0]

    def test_clean_files_pass(self):
        self.assertEqual(self.validate(self.doc, self.report), [])

    def test_a_missing_card_fails(self):
        doc = copy.deepcopy(self.doc)
        doc["cards"] = [card for card in doc["cards"] if card["id"] != "card_dandelion"]
        errors = self.validate(doc, self.report)
        self.assertTrue(errors, "a missing card must fail the checker")
        self.assertTrue(any("223 cards" in error or "not shipped" in error for error in errors), errors)

    def test_a_tier_b_row_without_a_source_fails(self):
        doc = copy.deepcopy(self.doc)
        card = next(card for card in doc["cards"] if card["id"] == "card_dandelion")
        card["window"].pop("source")
        report = copy.deepcopy(self.report)
        row = next(row for row in report["cards"] if row["id"] == "card_dandelion")
        row.pop("source")
        errors = self.validate(doc, report)
        self.assertTrue(any("community window needs a source" in error for error in errors), errors)

    def test_a_stale_report_fails(self):
        doc = copy.deepcopy(self.doc)
        report = copy.deepcopy(self.report)
        card = next(card for card in doc["cards"] if card["id"] == "card_ciri")
        card["window"]["kind"] = "missable"
        errors = self.validate(doc, report)
        self.assertTrue(any("disagree" in error for error in errors), errors)

    def test_a_bare_zero_fails(self):
        doc = copy.deepcopy(self.doc)
        report = copy.deepcopy(self.report)
        report["counts"]["missable"] = 0
        errors = self.validate(doc, report)
        self.assertTrue(any("counts.missable" in error for error in errors), errors)

    def test_a_category_only_no_window_reason_fails(self):
        doc = copy.deepcopy(self.doc)
        report = copy.deepcopy(self.report)
        card = next(card for card in doc["cards"] if card["window"]["kind"] == "none")
        card["window"]["reason"] = "Persistent source row(s): vendor; no deadline exists."
        row = next(row for row in report["cards"] if row["id"] == card["id"])
        row["reason"] = card["window"]["reason"]
        errors = self.validate(doc, report)
        self.assertTrue(any("specific checked source" in error for error in errors), errors)

    def test_a_no_window_row_without_sources_checked_fails(self):
        doc = copy.deepcopy(self.doc)
        report = copy.deepcopy(self.report)
        card = next(card for card in doc["cards"] if card["window"]["kind"] == "none")
        card["window"].pop("sources_checked")
        row = next(row for row in report["cards"] if row["id"] == card["id"])
        row.pop("sources_checked")
        errors = self.validate(doc, report)
        self.assertTrue(any("needs sources_checked" in error for error in errors), errors)

    def test_a_report_without_the_static_ownership_marker_fails(self):
        report = copy.deepcopy(self.report)
        report["ownership"]["in_artifact"] = True
        errors = self.validate(self.doc, report)
        self.assertTrue(any("ownership.in_artifact" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
