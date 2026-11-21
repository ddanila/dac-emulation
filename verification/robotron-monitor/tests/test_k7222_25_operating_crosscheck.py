"""Keep the AE9VT cross-revision comparison tied to its source and rail screen."""

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
        saved = json.loads(check.OUTPUT.read_text())
        self.assertEqual(check.run(), saved)
        self.assertTrue(saved['crossing_inside_k7222_25_41p_range'])

    def test_cross_revision_rail_range_rejects_an_outside_crossing(self):
        report = json.loads(check.LINK.read_text())
        report['threshold_feed_range_v'][1] = 43.5
        with tempfile.TemporaryDirectory() as directory:
            altered = Path(directory) / 'link.json'
            altered.write_text(json.dumps(report))
            with patch.object(check, 'LINK', altered), self.assertRaisesRegex(
                    ValueError, 'exceeds K7222.25 comparator range'):
                check.run()


if __name__ == '__main__':
    unittest.main()
