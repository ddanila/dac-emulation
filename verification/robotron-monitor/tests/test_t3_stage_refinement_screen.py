"""Guard the stage-periodicity check against a missed narrow collector edge."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import t3_stage_refinement_screen as screen


class StageLineAgreementTests(unittest.TestCase):
    def test_detects_narrow_collector_difference_between_grid_points(self):
        period = screen.PERIOD_S
        first = screen.END_S-2*period
        phases = [0, 10e-6, 30e-6, 60e-6, 61.5e-6,
                  61.505e-6, 61.51e-6, period]
        rows = [[first-1e-9, 0, 0, 0, 0, 0, 0, 0]]
        for line in range(2):
            for phase in phases[:-1] if line == 0 else phases:
                collector = 100.0 if phase == 30e-6 else 0.0
                if line == 1 and phase == 61.505e-6:
                    collector = .2
                yoke = 1.0 if phase == 30e-6 else 0.0
                flux = .5 if phase == 30e-6 else 0.0
                rows.append([first+line*period+phase, collector, 0, 0,
                             0, yoke, 0, flux])
        result = screen.line_agreement(rows)
        self.assertFalse(result['all_three_under_0_1_percent'])
        self.assertAlmostEqual(
            result['waveforms']['collector']
                  ['max_pointwise_difference_fraction_of_swing'], .002)
        self.assertEqual(
            result['waveforms']['yoke_current']
                  ['max_pointwise_difference_fraction_of_swing'], 0)


if __name__ == '__main__':
    unittest.main()
