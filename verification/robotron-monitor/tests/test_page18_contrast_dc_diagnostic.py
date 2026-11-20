"""Keep the source INTENS passthrough and contrast-path limit reproducible."""
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
    def test_intensity_reaches_neck_while_contrast_dc_effect_remains_open(self):
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
        for row in live['rows']:
            self.assertAlmostEqual(row['voltages_v']['rx_intens'],
                                   row['voltages_v']['intens'], places=8)
        at_low_contrast = [row for row in live['rows']
                           if row['feed_resistance_ohm'] == 0 and
                           row['contrast_position'] == .05 and row['logic_video'] == 1]
        dark_intensity, bright_intensity = at_low_contrast
        self.assertGreater(bright_intensity['voltages_v']['cathode']-
                           dark_intensity['voltages_v']['cathode'], 2)
        comparison = next(row for row in live['comparisons']
                          if row['feed_resistance_ohm'] == 0 and
                          row['logic_video'] == row['logic_intensity'] == 1)
        self.assertGreater(abs(comparison['high_minus_low_v1_collector_current_a']), .02)
        self.assertLess(abs(comparison['high_minus_low_voltage_v']['cathode']), .001)


if __name__ == '__main__':
    unittest.main()
