"""Keep the AE9VT cross-revision comparison tied to its source."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import k7222_25_operating_crosscheck as check


class K722225OperatingCrosscheckTests(unittest.TestCase):
    def test_saved_comparison_tracks_current_inputs(self):
        saved = check.run()
        self.assertEqual(saved['k7222_25_41p_v'], [39, 43])
        self.assertNotIn('conditional_tby7_nominal_crossing_feed_v', saved)

    def test_cross_revision_rejects_wrong_c21_voltage_reference(self):
        report = json.loads(check.READ.read_text())
        report['horizontal_stage_k7222_25']['boost_voltage_reference'] = 'to ground'
        with tempfile.TemporaryDirectory() as directory:
            altered = Path(directory) / 'read.json'
            altered.write_text(json.dumps(report))
            with patch.object(check, 'READ', altered), self.assertRaisesRegex(
                    ValueError, 'boost voltage reference changed'):
                check.run()


if __name__ == '__main__':
    unittest.main()
