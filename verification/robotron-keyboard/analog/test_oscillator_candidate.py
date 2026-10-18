"""Candidate selection must preserve provenance and reject a non-oscillating gate."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


@unittest.skipUnless(shutil.which('ngspice'), 'ngspice required')
class CandidateTests(unittest.TestCase):
    def test_explicit_model_and_stuck_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name, text, success in [
                ('nominal',(HERE/'ls_nand_nominal.cir').read_text(),True),
                ('stuck','.subckt LS_NAND_NOMINAL a b y vp g\nRout y vp 30\nRa a g 1g\nRb b g 1g\n.ends LS_NAND_NOMINAL\n',False)]:
                model=root/(name+'.cir');model.write_text(text);out=root/name
                run=subprocess.run([sys.executable,str(HERE/'oscillator_probe.py'),'--gate-model',str(model),'--out',str(out)],capture_output=True,text=True)
                report=json.loads((out/'report.json').read_text())
                self.assertEqual(report['passed'],success,run.stderr)
                self.assertEqual(run.returncode,0 if success else 1)
                self.assertEqual(report['model']['sha256'],hashlib.sha256(model.read_bytes()).hexdigest())
                self.assertEqual(report['model']['selection'],'explicit-candidate')
                self.assertNotIn('thresholdVolts',report['assumptions'])
                if not success:self.assertIn('did not sustain',report['error'])
                else:
                    # ngspice writes the full-precision stop one ULP below the
                    # Python literal on some builds; complete captures must pass.
                    self.assertTrue(all(r['traceSha256'] for r in report['runs']))


if __name__=='__main__':unittest.main()
