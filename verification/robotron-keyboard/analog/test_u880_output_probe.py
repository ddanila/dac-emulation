import json
from pathlib import Path
import shutil
import tempfile
import unittest
from u880_output_probe import HERE, cases, verify


class CpuOutputTests(unittest.TestCase):
    def test_dc_only_candidates_fail_fastest_case(self):
        rows = list(cases())
        self.assertEqual(len(rows), 24)
        for mode in ('minimum-supply', 'supply-tracking'):
            selected = [c for c in rows if c['hypothesis'] == mode]
            self.assertTrue(all(not c['withinBudget'] for c in selected))
            fastest = min(selected, key=lambda c: c['analyticSeconds'])
            self.assertEqual(fastest['initialVolts'], .8)
            self.assertEqual(fastest['extraCapacitanceFarads'], 0)
            self.assertGreater(fastest['analyticSeconds'], 340e-9)

    def test_alternatives_preserve_dc_across_rated_supplies(self):
        for ohms in (3000., 4000.):
            for supply in (4.75, 5., 5.25):
                self.assertGreaterEqual(supply - 250e-6 * ohms, 2.4)
            selected = [c for c in cases() if c['highOhms'] == ohms]
            self.assertTrue(all(c['withinBudget'] for c in selected))
            self.assertTrue(all(c['internalDelayHeadroomSeconds'] > 0 for c in selected))
        worst = max((c for c in cases() if c['hypothesis'] == 'linear-4000'), key=lambda c: c['analyticSeconds'])
        self.assertEqual(worst['initialVolts'], 0)
        self.assertAlmostEqual(worst['internalDelayHeadroomSeconds'] * 1e9, 19.5207691980492)

    def test_retained_replay_refuses_threshold_and_missing_cases(self):
        retained = HERE / 'reports/u880-output-candidates'
        verify(retained)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'report'
            shutil.copytree(retained, out)
            path = out / 'assessment.json'
            original = path.read_text()
            report = json.loads(original)
            report['cases'][0]['case']['targetVolts'] = 1.4
            path.write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                verify(out)
            report = json.loads(original)
            report['cases'].pop()
            path.write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                verify(out)


if __name__ == '__main__':
    unittest.main()
