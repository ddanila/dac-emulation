"""Keep the optional retrace-capacitor choice visible in A5."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import horizontal_retrace_c30_sensitivity as check


class C30SensitivityTests(unittest.TestCase):
    def test_c30_population_changes_resonance_and_loaded_stage(self):
        saved = json.loads((ROOT/'reference/k7222-11/horizontal-retrace-c30-sensitivity.json').read_text())
        result = check.run()
        self.assertTrue(result['analysis_valid'])
        self.assertTrue(result['exceeds_2pct_stage_sensitivity'])
        self.assertEqual(len(result['loaded_cases']), 4)
        by_population = {row['c30_populated']: row for row in result['analytic_scenarios']}
        self.assertGreater(by_population[False]['effective_inductance_h_for_16us_retrace']['nominal'],
                           by_population[True]['effective_inductance_h_for_16us_retrace']['nominal'])
        for current, reference in zip(result['loaded_cases'], saved['loaded_cases']):
            self.assertEqual(current['result']['status'], 'complete')
            self.assertAlmostEqual(current['result']['eht_final_v'],
                                   reference['result']['eht_final_v'], delta=1)
        for comparison in result['loaded_sensitivity']:
            self.assertGreater(comparison['absent_relative_to_populated']['eht_final_v'], .02)


if __name__ == '__main__':
    unittest.main()
