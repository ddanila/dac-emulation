import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page18_panel_compare as panel


class Page18PanelCompareTests(unittest.TestCase):
    def test_source_read_exposes_assembled_contrast_mismatch(self):
        pdf = ROOT.parents[1]/'build/monitor/phase-a/sources/older.pdf'
        report = panel.run(pdf)
        saved = json.loads((ROOT/'reference/k7222-11/page18-panel-topology-comparison.json').read_text())
        self.assertEqual(report, saved)
        self.assertTrue(report['brightness_topology_matches'])
        self.assertFalse(report['contrast_topology_matches'])
        self.assertEqual(report['contrast_model_nodes'], ['contrast_adjust', 'contrast_low', 'intens'])
        self.assertFalse(report['page18_gate_closed'])

    def test_changed_panel_pin_is_rejected(self):
        source = json.loads(panel.READ.read_text())
        interconnect = json.loads(panel.INTERCONNECT.read_text())
        changed = copy.deepcopy(source)
        changed['controls']['R2']['main_board_pins']['S'] = '6'
        with self.assertRaisesRegex(ValueError, 'panel terminal disagrees'):
            panel.compare(changed, interconnect, '', {}, pdf_sha256=source['source_pdf_sha256'])


if __name__ == '__main__':
    unittest.main()
