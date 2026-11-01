import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import default_dialogues as dd

HERE = Path(__file__).resolve().parent


def berengar():
    data = json.loads((HERE / "cutoff_windows.json").read_text(encoding="utf-8"))
    return next(w for w in data["windows"] if w["id"] == "berengar_vesemir_before_battle")


class DefaultDialogues(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.idx = json.loads((HERE / "quest_index.json").read_text(encoding="utf-8"))
        cls.index = dd.load_index()
        cls.rows = dd.scan(cls.idx, cls.index)

    def test_berengar_window_is_proven_by_the_files(self):
        err, ev = dd.window_evidence(self.idx, berengar(), self.index)
        self.assertEqual(err, "")
        self.assertEqual({s["file"] for s in ev["close_setters"]},
                         {r"quests\part_2\q403_battle.w2phase",
                          r"quests\part_2\quest_files\q403_battle\phases\q403_supporters.w2phase"})

    def test_the_vesemir_hook_is_the_only_final_side_quest_stop(self):
        side = [r for r in self.rows if r["final_stops"] and r["quests"]
                and not any(q.startswith(("q0", "q1", "q2", "q3", "q4", "q5")) for q in r["quests"])]
        self.assertEqual([(r["quests"], r["block"]) for r in side], [(["mq4005sword"], 72)])

    def test_an_unplaced_start_setter_keeps_a_stop_from_being_final(self):
        # Dandelion's chat is started again in q308_psycho, which the main story does not place
        sq303 = [r for r in self.rows if r["quests"] == ["sq303brothel"] and r["npc"] == "dandelion"]
        self.assertTrue(sq303)
        for r in sq303:
            self.assertEqual(r["final_stops"], [])
            self.assertTrue(r["reopen_unknown"])

    def test_wrong_stop_fact_or_closer_is_rejected(self):
        w = copy.deepcopy(berengar())
        w["close_gate"] = "lambert_dd_stop"
        err, _ = dd.window_evidence(self.idx, w, self.index)
        self.assertIn("not stopped by lambert_dd_stop", err)
        w = copy.deepcopy(berengar())
        w["closer"] = "q402ciri"
        err, _ = dd.window_evidence(self.idx, w, self.index)
        self.assertIn("never sets vesemir_dd_stop", err)
        w = copy.deepcopy(berengar())
        w["step"] = "mq4005sword#Talk to Lambert"
        err, _ = dd.window_evidence(self.idx, w, self.index)
        self.assertIn("not an objective", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
