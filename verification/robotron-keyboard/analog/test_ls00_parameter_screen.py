"""Physical-limit regressions for the generic-junction screen; not calibration."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from ls00_parameter_screen import candidate

HERE = Path(__file__).resolve().parent


class ParameterScreenTests(unittest.TestCase):
    def test_template_drift_requires_review(self):
        with self.assertRaisesRegex(ValueError, 'template changed'):
            candidate('.subckt changed\n', 100, 1e-12)

    @unittest.skipUnless(shutil.which('ngspice'), 'ngspice required')
    def test_additional_dc_conditions_reject_old_junctions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for label, diode_is, expected in [('baseline', 1e-8, False), ('candidate', 1e-12, True)]:
                model = root/(label+'.cir')
                model.write_text(candidate((HERE/'ls00_transistor_candidate.cir').read_text(),100,diode_is))
                out = root/label
                run = subprocess.run([sys.executable,str(HERE/'ls00_validation_probe.py'),
                    '--model',str(model),'--out',str(out)],capture_output=True,text=True)
                report = json.loads((out/'assessment.json').read_text())
                self.assertTrue(report['completed'],run.stderr)
                self.assertEqual(report['limitsPassed'],expected)
                self.assertEqual(run.returncode,0 if expected else 1)
                if not expected:
                    low = next(c for c in report['cases'] if c['name']=='low-4ma')
                    self.assertFalse(low['checks'][0]['passed'])

    @unittest.skipUnless(shutil.which('ngspice'), 'ngspice required')
    def test_specimen_device_conditions_keep_their_own_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for label,diode_is,expected in [('old',1e-8,False),('screened',1e-12,True)]:
                model=root/(label+'.cir');model.write_text(candidate((HERE/'ls00_transistor_candidate.cir').read_text(),100,diode_is))
                out=root/label
                run=subprocess.run([sys.executable,str(HERE/'ls00_validation_probe.py'),'--device','k555la3','--model',str(model),'--out',str(out)],capture_output=True,text=True)
                report=json.loads((out/'assessment.json').read_text())
                self.assertTrue(report['completed'],run.stderr)
                self.assertEqual(report['limitsPassed'],expected)
                self.assertEqual(run.returncode,0 if expected else 1)
                self.assertEqual(report['device'],'k555la3')
                self.assertIn('k555la3.pdf',report['limits']['source']['url'])
                self.assertFalse(report['qualified'])
                self.assertIn('switching',report['limits']['unimplementedPublishedConditions'])


if __name__ == '__main__':
    unittest.main()
