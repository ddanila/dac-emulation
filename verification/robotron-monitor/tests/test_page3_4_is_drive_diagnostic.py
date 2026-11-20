"""Keep capacitive IS transients distinct from a qualified logic high."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page3_4_is_drive_diagnostic as diagnostic


def state(report, video, intensity):
    return next(row for row in report['stable_states']
                if (row['logic_video'], row['logic_intensity']) == (video, intensity))


class Page34ISDriveDiagnosticTests(unittest.TestCase):
    def test_high_interval_depends_on_neck_diode_capacitance(self):
        project = ROOT.parents[1]
        subprocess.run(['make', 'build/robotron-signal-pattern'], cwd=project,
                       check=True, capture_output=True)
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory)/'highlight.json'
            capture.write_bytes(subprocess.check_output(
                [str(project/'build/robotron-signal-pattern'), 'highlight']))
            live = diagnostic.run(capture)
        saved = json.loads((ROOT/'reference/k7222-11/page3-4-is-drive-diagnostic.json').read_text())
        self.assertEqual(live, saved)
        cases = {row['case']: row for row in live['variants']}
        self.assertGreater(state(cases['nominal'], 0, 1)['is_median_v'], 4)
        self.assertLess(state(cases['lower_bound'], 0, 1)['is_median_v'], .5)
        self.assertGreater(state(cases['upper_bound'], 0, 1)['is_median_v'], 20)
        self.assertLess(state(cases['zero_cjo_diagnostic'], 0, 1)['is_median_v'], .5)
        self.assertLess(live['fixed_state']['is_final_v'], .5)
        for case in cases.values():
            self.assertLess(state(case, 1, 1)['is_median_v'], 1)
            self.assertLess(abs(state(case, 1, 1)['cathode_median_v']-
                                state(case, 1, 0)['cathode_median_v']), .01)


if __name__ == '__main__':
    unittest.main()
