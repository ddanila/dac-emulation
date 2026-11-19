import copy
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import page16_neck_compare
import page16_neck_static


class Page16NeckStaticTests(unittest.TestCase):
    def test_source_dc_paths_and_stage_operating_points(self):
        pdf=ROOT.parents[1]/'build/monitor/phase-a/sources/older.pdf'
        report=page16_neck_static.run(pdf)
        saved=json.loads((ROOT/'reference/k7222-11/page16-neck-static.json').read_text())
        self.assertEqual(report,saved)
        self.assertTrue(report['passed'])
        self.assertEqual(report['source_dc_paths']['unreachable_nets'],[])
        dark=report['state_voltages']['dark_video']['volts']
        bright=report['state_voltages']['bright_video']['volts']
        self.assertGreater(dark['collector']-bright['collector'],30)
        source=json.loads(page16_neck_compare.SOURCE.read_text())
        changed=copy.deepcopy(source)
        changed['nets']['SUG2'].remove('R2:2')
        changed['nets']['UG2_INPUT'].append('R2:2')
        self.assertIn('SUG2',page16_neck_static.dc_paths(changed)['unreachable_nets'])


if __name__=='__main__':unittest.main()
