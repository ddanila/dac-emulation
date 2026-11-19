import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page18_frame_compare as compare
import steady_supply


class Page18FrameCompareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads(compare.SOURCE.read_text())
        cls.assembly = json.loads(compare.ASSEMBLY.read_text())
        with tempfile.TemporaryDirectory() as directory:
            cls.components = steady_supply.assemble(Path(directory)/'assembly')['components']

    def test_neck_cables_match_source_and_report_export_gaps(self):
        report = compare.compare(self.source, self.assembly, self.components)
        saved = json.loads((ROOT/'reference/k7222-11/page18-frame-comparison.json').read_text())
        self.assertEqual(report, saved)
        self.assertEqual(len(report['cable_pairs']), 8)
        self.assertEqual(report['both_board_nets'], 6)
        self.assertEqual({row['source_signal'] for row in report['missing_board_nets']},
                         {'INTENS', '10.7P'})
        self.assertIn('pin-level gate remains open', report['qualification'])

    def test_changed_cable_signal_or_neck_pin_is_rejected(self):
        source = copy.deepcopy(self.source)
        source['connectors']['012-6921:X6']['2'] = 'UG1'
        with self.assertRaisesRegex(ValueError, 'cable signal mismatch'):
            compare.compare(source, self.assembly, self.components)
        assembly = copy.deepcopy(self.assembly)
        assembly['neck_connectors']['X1']['2'] = 'ug1'
        with self.assertRaisesRegex(ValueError, 'neck model pin differs'):
            compare.compare(self.source, assembly, self.components)


if __name__ == '__main__':
    unittest.main()
