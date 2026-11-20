"""Check the source-corrected intensity/contrast DC diagnostic."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page18_contrast_dc_diagnostic as diagnostic


class Page18ContrastDCDiagnosticTests(unittest.TestCase):
    def test_intensity_seam_and_unqualified_output(self):
        project = ROOT.parents[1]
        subprocess.run(['make', 'build/robotron-signal-pattern'], cwd=project,
                       check=True, capture_output=True)
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory)/'highlight.json'
            capture.write_bytes(subprocess.check_output(
                [str(project/'build/robotron-signal-pattern'), 'highlight']))
            live = diagnostic.run(capture)
        saved = json.loads((ROOT/'reference/k7222-11/page18-contrast-dc-diagnostic.json').read_text())
        self.assertEqual(live, saved)
        self.assertEqual(len(live['rows']), 16)
        high_input = next(row for row in live['rows']
                          if row['feed_resistance_ohm'] == 0 and
                          row['logic_video'] == 0 and row['logic_intensity'] == 1 and
                          row['contrast_position'] == .05)
        self.assertGreater(high_input['voltages_v']['rx_intens'], 3)
        self.assertLess(high_input['voltages_v']['intens'], 1)
        self.assertGreater(high_input['voltages_v']['v1_base'], 20)
        for comparison in live['comparisons']:
            self.assertLess(comparison['high_minus_low_v1_collector_current_a'], -.02)
            self.assertLess(abs(comparison['high_minus_low_voltage_v']['cathode']), 1e-3)


if __name__ == '__main__':
    unittest.main()
