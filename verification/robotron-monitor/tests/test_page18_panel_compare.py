import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page18_panel_compare as panel
import steady_supply
import transformer_candidates


class Page18PanelCompareTests(unittest.TestCase):
    def test_source_read_matches_assembled_panel_topology(self):
        pdf = ROOT.parents[1]/'build/monitor/phase-a/sources/older.pdf'
        report = panel.run(pdf)
        saved = report
        self.assertTrue(report['brightness_topology_matches'])
        self.assertTrue(report['contrast_topology_matches'])
        self.assertEqual(report['contrast_model_nodes'], ['contrast_low', 'reference9'])
        self.assertEqual(report['assembled_r4_left_node'], 'reference9')
        self.assertEqual(report['assembled_v1_emitter_node'], 'contrast_low')
        self.assertTrue(report['kra_physical_connector_pin_verified'])
        self.assertTrue(report['krs_physical_connector_pin_verified'])
        self.assertEqual(report['physical_connector_pins_checked'], 6)
        self.assertEqual(report['physical_connector_pin_misses'], [])
        self.assertFalse(report['page18_gate_closed'])

    def test_changed_panel_pin_is_rejected(self):
        source = json.loads(panel.READ.read_text())
        interconnect = json.loads(panel.INTERCONNECT.read_text())
        changed = copy.deepcopy(source)
        changed['controls']['R2']['main_board_pins']['S'] = '6'
        with self.assertRaisesRegex(ValueError, 'panel terminal disagrees'):
            panel.compare(changed, interconnect, '', {}, [], None,
                          pdf_sha256=source['source_pdf_sha256'])

    def test_wrong_contrast_endpoint_is_reported(self):
        source = json.loads(panel.READ.read_text())
        interconnect = json.loads(panel.INTERCONNECT.read_text())
        with tempfile.TemporaryDirectory() as directory:
            assembly = steady_supply.assemble(Path(directory)/'assembly')
            selection = {'status': 'complete', 'period_ticks': 3600000,
                         'clock_hz': 179712000, 'events': [[0, 0, 1, 1], [1800000, 1, 0, 1]]}
            candidate = transformer_candidates.enumerate_candidates(assembly['magnetic_graph'])[0]
            deck, metadata = steady_supply.deck(assembly, selection, candidate)
            wrong = deck.replace('Rcontrast reference9 contrast_low ',
                                 'Rcontrast intens contrast_low ', 1)
            report = panel.compare(source, interconnect, wrong, metadata,
                                   assembly['components'],
                                   Path(directory)/'assembly/k7222-11-input.xml',
                                   pdf_sha256=source['source_pdf_sha256'])
            self.assertFalse(report['contrast_topology_matches'])
            self.assertEqual(len(report['mismatches']), 1)

    def test_wrong_exported_x1_pin_is_reported(self):
        source = json.loads(panel.READ.read_text())
        interconnect = json.loads(panel.INTERCONNECT.read_text())
        with tempfile.TemporaryDirectory() as directory:
            assembly = steady_supply.assemble(Path(directory)/'assembly')
            selection = {'status': 'complete', 'period_ticks': 3600000,
                         'clock_hz': 179712000, 'events': [[0, 0, 1, 1], [1800000, 1, 0, 1]]}
            candidate = transformer_candidates.enumerate_candidates(assembly['magnetic_graph'])[0]
            deck, metadata = steady_supply.deck(assembly, selection, candidate)
            export = Path(directory)/'assembly/k7222-11-input.xml'
            tree = ET.parse(export)
            for net in tree.getroot().findall('./nets/net'):
                for node in net.findall('node'):
                    if node.get('ref') == 'J901' and node.get('pin') == '6':
                        net.set('name', 'wrong_kra_net')
            changed_export = Path(directory)/'changed.xml'
            tree.write(changed_export)
            report = panel.compare(source, interconnect, deck, metadata,
                                   assembly['components'], changed_export,
                                   pdf_sha256=source['source_pdf_sha256'])
            self.assertEqual([row['pin'] for row in report['physical_connector_pin_misses']], ['6'])
            self.assertFalse(report['kra_physical_connector_pin_verified'])


if __name__ == '__main__':
    unittest.main()
