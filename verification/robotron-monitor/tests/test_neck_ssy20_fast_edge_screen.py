"""Detect neck switching changes hidden by the legacy 200 ns sample grid."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import neck_ssy20_fast_edge_screen as screen


class SSY20FastEdgeScreenTests(unittest.TestCase):
    def test_fine_grid_exposes_candidate_cathode_edge_change(self):
        saved = json.loads(screen.OUTPUT.read_text())
        runtime = Path(saved['runtime_path'])
        if not runtime.is_dir():
            self.skipTest('verified ngspice runtime is unavailable')
        with tempfile.TemporaryDirectory() as directory:
            live = screen.run(runtime, Path(directory)/'paired')
        self.assertEqual(live['sample_count'], 80001)
        self.assertGreater(live['comparison']['cathode']['peak_delta_v'], 4)
        self.assertLess(live['comparison']['cathode']['late_200ns_grid_peak_delta_v'], .001)
        self.assertFalse(live['connected_stress_checked'])


if __name__ == '__main__':
    unittest.main()
