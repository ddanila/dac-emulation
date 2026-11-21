import json
from pathlib import Path
import shutil
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import t3_page4_c30_screen as screen


class T3Page4C30ScreenTests(unittest.TestCase):
    def test_source_visible_population_pair_reproduces(self):
        ngspice = shutil.which('ngspice')
        if ngspice is None:
            self.skipTest('ngspice is unavailable')
        saved = json.loads(screen.OUTPUT.read_text())
        live = screen.run(Path(ngspice), screen.visible.SOURCE_PDF)
        self.assertEqual(live, saved)
        self.assertTrue(live['sampled_three_metric_within_2pct'])
        self.assertFalse(live['sampled_tp17_waveform_within_2pct'])
        self.assertGreater(live['tp17_waveform_comparison']['peak_difference_over_populated_pp'], .02)
        self.assertGreater(live['refined_tp17_waveform_comparison']['peak_difference_over_populated_pp'], .02)
        self.assertLess(abs(live['tp17_waveform_comparison']['peak_difference_over_populated_pp'] -
                            live['refined_tp17_waveform_comparison']['peak_difference_over_populated_pp']), .001)
        self.assertEqual([row['c30_populated'] for row in live['cases']], [True, False])
        self.assertLess(live['cases'][0]['observed']['c21_voltage_at_collector_peak_v'], 60)
        self.assertLess(live['cases'][1]['observed']['c21_voltage_at_collector_peak_v'], 60)


if __name__ == '__main__':
    unittest.main()
