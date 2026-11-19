import json
from pathlib import Path
import re
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import horizontal_diode_check as diode


class HorizontalDiodeCheckTests(unittest.TestCase):
    def test_registered_bounds_match_both_live_models(self):
        register=json.loads((ROOT/'reference/k7222-11/device-model-register.json').read_text())
        families=[row for row in register['families'] if row['model'] in {'HOR_D','HOR_RECT'}]
        self.assertEqual(len(families),4)
        scale={'p':1e-12,'n':1e-9,'u':1e-6,'k':1e3}
        for family in families:
            line=diode.model_line(family['model'])
            actual=dict(re.findall(r'([A-Z]+)=([0-9.eE+-]+[pnuk]?)',line))
            self.assertEqual(set(actual),set(family['parameters']))
            for key,value in actual.items():
                suffix=value[-1]
                numeric=float(value[:-1])*scale[suffix] if suffix in scale else float(value)
                self.assertAlmostEqual(numeric,family['parameters'][key]['nominal'])

    def test_live_models_match_saved_class_comparisons(self):
        report=diode.run()
        saved=json.loads((ROOT/'reference/k7222-11/horizontal-diode-class-check.json').read_text())
        self.assertEqual(report,saved)
        self.assertTrue(report['passed'])
        self.assertEqual({id for row in report['rows'] for id in row['ids']},
                         {'012-6921:V8','012-6921:V9','012-6921:V14',
                          '012-6921:V15','012-6921:V16','012-6921:V17'})

    def test_wrong_rectifier_capacitance_fails(self):
        case=diode.CASES[1]
        line=diode.model_line(case['name'])
        changed=line.replace('CJO=40p','CJO=200p')
        self.assertNotEqual(changed,line)
        result=diode.compare(case,changed)
        self.assertFalse(result['checks']['capacitance'])
        self.assertFalse(result['passed'])


if __name__=='__main__':
    unittest.main()
