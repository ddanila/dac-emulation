"""Keep the T3 return conclusion conditional on its HV cold connection."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import t3_cold_return_matrix


class T3ColdReturnMatrixTests(unittest.TestCase):
    def test_grounded_cold_end_removes_open_upper_return_discriminator(self):
        pdf = ROOT.parents[1]/'build/monitor/phase-a/sources/older.pdf'
        report = t3_cold_return_matrix.run(pdf)
        saved = json.loads((ROOT/'reference/k7222-11/t3-cold-return-matrix.json').read_text())
        self.assertEqual(report, saved)
        self.assertTrue(report['passed'])
        self.assertEqual(len(report['candidate_results']), 8)
        for candidate in report['candidate_results']:
            results = candidate['results']
            self.assertLess(results['open__shared_floating']['eht_peak_v'], .01)
            self.assertGreater(results['open__shared_grounded']['eht_peak_v'], 10)
            self.assertGreater(results['open__hv_only_grounded']['eht_peak_v'], 10)


if __name__ == '__main__':
    unittest.main()
