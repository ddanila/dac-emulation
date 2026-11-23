"""Keep the manual IS boundary target distinct from the original V5 driver."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page3_4_is_boundary_requirement as boundary


class ISBoundaryRequirementTests(unittest.TestCase):
    def test_normal_bright_target_needs_stiff_high_is_drive(self):
        project = ROOT.parents[1]
        subprocess.run(['make', 'build/robotron-signal-pattern'], cwd=project,
                       check=True, capture_output=True)
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory)/'highlight.json'
            capture.write_bytes(subprocess.check_output(
                [str(project/'build/robotron-signal-pattern'), 'highlight']))
            live = boundary.run(capture)
        saved = live
        ideal = live['ideal_source_rows']
        for row in ideal:
            if row['video_logic'] == 0:
                self.assertAlmostEqual(row['cathode_v'], 33.68531, places=3)
        normal = live['nominal_boundary_example']
        self.assertAlmostEqual(normal['cathode_v'], 15, delta=.1)
        self.assertGreater(normal['source_delivered_current_a'], .02)
        self.assertLess(normal['source_delivered_current_a'], .04)
        loaded = live['series_resistance_rows']
        self.assertEqual([row['source_resistance_ohm'] for row in loaded],
                         [0, 10, 100, 1000, 10000])
        self.assertTrue(all(a['cathode_v'] > b['cathode_v']
                            for a, b in zip(loaded, loaded[1:])))
        self.assertLess(loaded[2]['cathode_v'], 13)


if __name__ == '__main__':
    unittest.main()
