"""Keep the A5 design-point summary tied to the corrected page-4 T3 read."""

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "reference/k7222-11"


class DesignPointT3IdentityTests(unittest.TestCase):
    def test_current_identity_and_historical_screens_are_distinct(self):
        design = json.loads((REF / "design-point.json").read_text())
        identity = design["t3_terminal_identity"]
        source = json.loads((ROOT / identity["source_read"]).read_text())

        for path_key, hash_key in (
            ("source_read", "source_read_sha256"),
            ("candidate_graph", "candidate_graph_sha256"),
            ("candidate_wrapper_comparison", "candidate_wrapper_comparison_sha256"),
            ("candidate_stage_screen", "candidate_stage_screen_sha256"),
            ("candidate_booster_turn_screen", "candidate_booster_turn_screen_sha256"),
        ):
            self.assertEqual(
                hashlib.sha256((ROOT / identity[path_key]).read_bytes()).hexdigest(),
                identity[hash_key],
            )

        labels = source["visible_labels"]
        self.assertEqual(identity["v21_anode_pad"], labels["v21_anode_pad"])
        self.assertEqual(identity["v21_cathode_pad"], labels["v21_cathode_pad"])
        self.assertIn(identity["drawn_upper_conductor"], source["drawn_conductor_pairs"])
        self.assertEqual(
            identity["visible_magnetic_port_count"],
            sum(len(group) for group in source["page4_visible_magnetic_terminals"].values()),
        )
        self.assertTrue(identity["active_19_port_model_source_contradicted"])
        self.assertIsNone(identity["manual_connection_16_mapping"])

        stage = json.loads((ROOT / identity["candidate_stage_screen"]).read_text())
        booster = json.loads((ROOT / identity["candidate_booster_turn_screen"]).read_text())
        self.assertEqual(stage["complete_count"], 7)
        self.assertEqual(stage["joint_sampled_match_count"], 0)
        self.assertEqual(booster["complete_count"], 5)
        self.assertEqual(booster["joint_sampled_match_count"], 0)
        for report in (stage, booster):
            for relative, expected in report["input_sha256"].items():
                self.assertEqual(
                    hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(),
                    expected, relative,
                )

        for key in (
            "conditional_t3_hv_turn_scale",
            "conditional_t3_polarity_screen",
            "conditional_t3_g1_polarity_screen",
        ):
            self.assertFalse(design[key]["valid_for_current_20_port_graph"])
        self.assertIn("not an installed T3 turns ratio", design["high_voltage_ratio"]["status"])


if __name__ == "__main__":
    unittest.main()
