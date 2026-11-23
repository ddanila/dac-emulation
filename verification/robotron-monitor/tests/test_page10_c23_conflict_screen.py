import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page10_c23_conflict_screen as screen


class Page10C23ConflictTests(unittest.TestCase):
    def test_manual_reference_choice_tracks_both_source_topologies(self):
        saved = screen.run()
        self.assertTrue(saved['comparison']['all_selected_probes_below_two_percent'])
        self.assertEqual(saved['decision']['selected'], 'manual-fig12-reference-connection')
        self.assertFalse(saved['decision']['phase_b_qualified'])


if __name__ == '__main__':
    unittest.main()
