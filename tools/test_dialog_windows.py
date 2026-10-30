import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dialog_windows as dw

STATUETTES = r"quests\minor_quests\novigrad\mq3012_jade_statuettes.w2phase"
NOW_OR_NEVER = r"quests\part_2\q309_casablanca.w2phase"


class Activations(unittest.TestCase):
    def test_statuette_quest_names_two_triss_phases(self):
        g = dw.load(STATUETTES)
        phases = {r["phase"] for r in dw.activations(g, "triss.w2comm") if r["phase"]}
        self.assertEqual(phases, {"triss_default", "q310_ap_triss_dandelions"})

    def test_now_or_never_moves_her_out_of_triss_default(self):
        g = dw.load(NOW_OR_NEVER)
        phases = {r["phase"] for r in dw.activations(g, "triss.w2comm") if r["phase"]}
        self.assertNotIn("triss_default", phases)
        self.assertTrue(any(p.startswith("q309_") for p in phases))

    def test_window_without_community_fails(self):
        idx = json.loads((Path(__file__).resolve().parent / "quest_index.json").read_text(encoding="utf-8"))
        err, lines = dw.community_evidence(idx, {"affects": ["mq3012noblestatuette"]})
        self.assertTrue(err)
        self.assertEqual(lines, [])

    def test_window_with_wrong_phase_fails(self):
        idx = json.loads((Path(__file__).resolve().parent / "quest_index.json").read_text(encoding="utf-8"))
        err, _ = dw.community_evidence(idx, {
            "affects": ["mq3012noblestatuette"],
            "community": r"quests\main_npcs\community_files\triss.w2comm",
            "community_phases": ["triss_default", "triss_at_kaer_morhen"],
        })
        self.assertIn("triss_at_kaer_morhen", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
