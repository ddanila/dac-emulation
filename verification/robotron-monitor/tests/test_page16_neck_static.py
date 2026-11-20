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
        normal=report['state_voltages']['bright_video_normal_is']['volts']
        self.assertGreater(dark['collector']-bright['collector'],30)
        self.assertEqual(report['state_voltages']['bright_video']['intensity_mode'],
                         'intensive')
        self.assertEqual(report['state_voltages']['bright_video_normal_is']['intensity_mode'],
                         'normal')
        self.assertGreater(normal['cathode']-bright['cathode'],3)
        source=json.loads(page16_neck_compare.SOURCE.read_text())
        self.assertEqual(source['signal_polarity'],
                         {'IS_low':'intensive','IS_high':'normal'})
        meter=json.loads((ROOT/'reference/k7222-11/page16-meter-cable-source-read.json').read_text())
        self.assertIn('X3:1',source['nets']['SUK_DRIVE'])
        self.assertIn('R4:1',source['nets']['SUK_DRIVE'])
        self.assertIn('X3:2',source['nets']['SUK'])
        self.assertIn('R4:2',source['nets']['SUK'])
        for state,expected_mv in meter['neck_board']['direct_x3_difference_in_existing_fixed_20ua_bench_mv'].items():
            volts=report['state_voltages'][state]['volts']
            self.assertAlmostEqual(1000*abs(volts['cathode']-volts['brightness']),
                                   expected_mv,places=6)
        changed=copy.deepcopy(source)
        changed['nets']['SUG2'].remove('R2:2')
        changed['nets']['UG2_INPUT'].append('R2:2')
        self.assertIn('SUG2',page16_neck_static.dc_paths(changed)['unreachable_nets'])


if __name__=='__main__':unittest.main()
