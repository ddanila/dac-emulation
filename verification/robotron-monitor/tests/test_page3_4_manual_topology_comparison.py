"""Keep the manual contrast alternative conditional on its source conflict."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page3_4_manual_topology_comparison as comparison


def row(report, topology, brightness, intensity, contrast):
    return next(item for item in report['rows']
                if item['topology'] == topology and
                item['brightness_position'] == brightness and
                item['logic_intensity'] == intensity and
                item['contrast_position'] == contrast)


class ManualTopologyComparisonTests(unittest.TestCase):
    def test_manual_terminal_swap_changes_output_for_one_raw_input_state(self):
        project = ROOT.parents[1]
        subprocess.run(['make', 'build/robotron-signal-pattern'], cwd=project,
                       check=True, capture_output=True)
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory)/'highlight.json'
            capture.write_bytes(subprocess.check_output(
                [str(project/'build/robotron-signal-pattern'), 'highlight']))
            live = comparison.run(capture)
        saved = live
        active = 'detailed_page3_4'
        alternate = 'manual_fig6_terminal_swap'
        active_low = row(live, active, 0, 0, .05)['voltages_v']['cathode']
        active_high = row(live, active, 0, 0, .95)['voltages_v']['cathode']
        self.assertLess(abs(active_high-active_low), .001)
        alternate_low = row(live, alternate, 0, 0, .05)['voltages_v']['cathode']
        alternate_high = row(live, alternate, 0, 0, .95)['voltages_v']['cathode']
        self.assertTrue(12 < alternate_low < 18)
        self.assertTrue(12 < alternate_high < 18)
        self.assertGreater(alternate_high-alternate_low, 2)
        other_low = row(live, alternate, 0, 1, .05)['voltages_v']['cathode']
        other_high = row(live, alternate, 0, 1, .95)['voltages_v']['cathode']
        self.assertLess(abs(other_high-other_low), .01)
        self.assertIn('not a direct test', live['logic_mapping_note'])
        for dark in live['dark_rows']:
            self.assertAlmostEqual(dark['voltages_v']['cathode'], 33.68531, places=3)


if __name__ == '__main__':
    unittest.main()
