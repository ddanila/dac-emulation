import json
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import vertical_diode_check


class VerticalDiodeCheckTests(unittest.TestCase):
    def test_live_model_matches_saved_comparator_results(self):
        report = vertical_diode_check.run()
        saved = json.loads((ROOT/'reference/k7222-11/vertical-diode-model-check.json').read_text())
        self.assertEqual(report, saved)
        self.assertTrue(all(report['checked'].values()))
        self.assertLessEqual(report['recovery_test']['reverse_recovery_s'], 4e-9)
        self.assertIn('joint-bound and native connected-frame response', report['unchecked'])

    def test_stage_sensitivity_receipt_tracks_current_sources(self):
        saved = json.loads((ROOT/'reference/k7222-11/vertical-diode-stage-sensitivity.json').read_text())
        current_hash = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(saved['model_sha256'], current_hash(vertical_diode_check.MODEL))
        self.assertEqual(saved['profile_sha256'], current_hash(vertical_diode_check.PROFILE))
        self.assertEqual(saved['register_sha256'], current_hash(ROOT/'reference/k7222-11/device-model-register.json'))
        self.assertEqual(saved['stage_source_hashes']['schematic_2'],
                         current_hash(ROOT/'circuits/k7222-11-vertical-output.kicad_sch'))
        self.assertEqual(saved['stage_source_hashes']['bench'],
                         current_hash(ROOT/'circuits/k7222-11-vertical-output-bench.cir'))
        self.assertEqual(len(saved['cases']), 24)
        self.assertEqual(len(saved['member_ids']), 10)


if __name__ == '__main__':
    unittest.main()
