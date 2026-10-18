"""Keep role-specific substitutions isolated and verify current sensitivity."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from ls00_parameter_screen import candidate as junction_candidate
from ls00_rolloff_screen import candidate

HERE = Path(__file__).resolve().parent


class RolloffTests(unittest.TestCase):
    def source(self):
        return junction_candidate((HERE/'ls00_transistor_candidate.cir').read_text(), 100, 1e-12)

    def test_sink_only_preserves_shared_model_and_other_stages(self):
        source = self.source()
        result = candidate(source, 'sink', .01)
        self.assertIn('Xphase drive input sinkbase LS00_SCHOTTKY_NPN_ASSUMED', result)
        self.assertIn('Qhigh collector highbase y LS00_NPN_ASSUMED', result)
        self.assertIn('Xsink y sinkbase g LS00_SINK_NPN_CANDIDATE', result)
        self.assertEqual(result.count('IKF='), 1)
        self.assertIn('LS00_SINK_ASSUMED NPN(', result)
        with self.assertRaises(ValueError):
            candidate(candidate(source, 'all', .01), 'all', .1)
        with self.assertRaises(ValueError):
            candidate(source, 'other', .1)

    @unittest.skipUnless(shutil.which('ngspice'), 'ngspice required')
    def test_rolloff_reduces_forced_output_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            values = []
            for label, text in [('base', self.source()), ('rolloff', candidate(self.source(), 'sink', .01))]:
                model = root/(label+'.cir');model.write_text(text)
                out = root/label
                subprocess.run([sys.executable, str(HERE/'ls00_iv_probe.py'), '--model', str(model),
                                '--out', str(out)], check=True, capture_output=True, text=True, timeout=60)
                report = json.loads((out/'assessment.json').read_text())
                self.assertTrue(report['completed'])
                values.append(next(abs(p['outputSourceAmps']) for c in report['cases']
                                   if c['name']=='low-threshold' for p in c['selectedPoints']
                                   if abs(p['outputVolts']-2)<1e-10))
            self.assertLess(values[1], values[0]/2)


if __name__ == '__main__':
    unittest.main()
