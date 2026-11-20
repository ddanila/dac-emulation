import json
from pathlib import Path
import re
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import horizontal_diode_check as diode
import hv_rectifier_check as hv


class HvRectifierCheckTests(unittest.TestCase):
    def test_live_v21_model_and_saved_class_response(self):
        register=json.loads((ROOT/'reference/k7222-11/device-model-register.json').read_text())
        device=next(row for row in register['devices'] if row['id']=='012-6921:V21')
        line=diode.model_line('HOR_HV_RECT')
        actual=dict(re.findall(r'([A-Z]+)=([0-9.eE+-]+[pnuk]?)',line))
        self.assertEqual(set(actual),{p['spice_parameter'] for p in device['parameters'].values()})
        scale={'p':1e-12,'n':1e-9,'u':1e-6,'k':1e3}
        for parameter in device['parameters'].values():
            raw=actual[parameter['spice_parameter']]
            value=float(raw[:-1])*scale[raw[-1]] if raw[-1] in scale else float(raw)
            self.assertAlmostEqual(value,parameter['nominal'])
        report=hv.run()
        saved=json.loads((ROOT/'reference/k7222-11/hv-rectifier-class-check.json').read_text())
        self.assertEqual(report,saved)
        self.assertTrue(report['passed'])

    def test_old_series_resistance_exceeds_semtech_forward_limit(self):
        line=diode.model_line('HOR_HV_RECT')
        old=line.replace('RS=90','RS=100')
        self.assertNotEqual(old,line)
        voltage=diode.solve(old,'IF 0 a 0.2\nD1 a 0 HOR_HV_RECT','op',['v(a)'])['v(a)']
        self.assertGreater(voltage,20.)


if __name__=='__main__':unittest.main()
