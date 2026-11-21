"""Keep the optional retrace-capacitor choice visible in A5."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import horizontal_retrace_c30_sensitivity as check


class C30SensitivityTests(unittest.TestCase):
    def test_old_loaded_result_is_historical_after_t3_graph_change(self):
        saved = json.loads((ROOT/'reference/k7222-11/horizontal-retrace-c30-sensitivity.json').read_text())
        result = check.run()
        self.assertTrue(result['analysis_valid'])
        self.assertNotEqual(saved['source_hashes'][check.driver.stage.GRAPH.name],
                            check.driver.stage.sha(check.driver.stage.GRAPH))
        self.assertFalse(result['exceeds_2pct_stage_sensitivity'])
        self.assertEqual(len(result['loaded_cases']), 4)
        by_population = {row['c30_populated']: row for row in result['analytic_scenarios']}
        self.assertGreater(by_population[False]['effective_inductance_h_for_16us_retrace']['nominal'],
                           by_population[True]['effective_inductance_h_for_16us_retrace']['nominal'])
        for current in result['loaded_cases']:
            self.assertEqual(current['result']['status'], 'complete')
        self.assertTrue(saved['exceeds_2pct_stage_sensitivity'])


if __name__ == '__main__':
    unittest.main()
