import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from i8282_propagation_probe import cases,deck,verify

HERE=Path(__file__).resolve().parent
RETAINED=HERE/'reports/i8282-propagation-candidates'


class PropagationTests(unittest.TestCase):
    def test_parallel_capacitors_share_loaded_initial_state(self):
        for c in cases():
            text=deck(c)
            capacitor_lines=[line for line in text.splitlines() if line.startswith(('Cload ','Cdevice '))]
            self.assertEqual(len(capacitor_lines),2 if c['extraCapacitancePf'] else 1)
            for line in capacitor_lines:
                self.assertEqual(float(re.search(r'IC=(\S+)',line)[1]),c['initialVolts'])
            self.assertIn('WHEN v(out)=1.5',text)
            self.assertNotIn('TRIG v(out)',text)

    def test_pin_limits_cannot_be_used_as_internal_delays(self):
        limits=json.loads((HERE/'i8282_delay_contract.json').read_text())
        values=list(cases());self.assertEqual(len(values),36)
        for c in values:
            stage=c['stageDelaySeconds'];self.assertGreater(stage,0)
            for budget,limit in [('maximumInternalDataDelaySeconds','inputToOutputMaximumSeconds'),
                                 ('maximumInternalStrobeDelaySeconds','strobeToOutputMaximumSeconds')]:
                self.assertGreater(c[budget],0)
                self.assertLess(c[budget],limits[limit])
                self.assertAlmostEqual(c[budget]+stage,limits[limit],places=20)
                self.assertGreater(limits[limit]+stage,limits[limit])

    def test_retained_measurements_and_changed_threshold(self):
        verify(RETAINED)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'evidence';shutil.copytree(RETAINED,out)
            path=out/'0/probe.cir';path.write_text(path.read_text().replace('WHEN v(out)=1.5','WHEN v(out)=0.8'))
            with self.assertRaises(ValueError):verify(out)


if __name__=='__main__':unittest.main()
