"""Keep the page-18 contrast failure visible in the corrected loaded bench."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page18_contrast_stage_check as contrast


class Page18ContrastStageCheckTests(unittest.TestCase):
    def test_source_connected_control_still_needs_functional_resolution(self):
        project = ROOT.parents[1]
        subprocess.run(['make', 'build/robotron-signal-pattern'], cwd=project,
                       check=True, capture_output=True)
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory)/'highlight.json'
            capture.write_bytes(subprocess.check_output(
                [str(project/'build/robotron-signal-pattern'), 'highlight']))
            live = contrast.run(capture)
        saved = live
        self.assertEqual([row['contrast_position'] for row in live['rows']], [.05, .5, .95])
        self.assertLess(live['low_high_cathode_relative_to_mid_swing'], .02)
        self.assertLess(live['low_high_beam_relative_to_mid_peak'], .02)
        self.assertGreater(live['rows'][1]['cathode']['peak_to_peak'], 30)
        self.assertGreater(live['rows'][1]['conditional_held_warm_beam_ua']['maximum'], 20)
        self.assertIn('remain unqualified', live['functional_result'])


if __name__ == '__main__':
    unittest.main()
