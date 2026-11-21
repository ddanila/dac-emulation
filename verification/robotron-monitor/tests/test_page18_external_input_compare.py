import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page18_external_input_compare as external
import steady_supply
import transformer_candidates


class Page18ExternalInputCompareTests(unittest.TestCase):
    def test_saved_input_seam_matches_fresh_assembly(self):
        report = external.run()
        saved = json.loads(external.OUTPUT.read_text())
        self.assertEqual(report, saved)
        self.assertEqual([row['source_signal'] for row in report['signal_rows']],
                         ['VIDEO', 'BSYN', 'INTENS'])
        self.assertTrue(report['physical_x9_present'])
        self.assertEqual(report['physical_pins_checked'], 5)

    def test_disconnected_intensity_cable_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'assembly'
            assembly = steady_supply.assemble(output)
            selection = {'status': 'complete', 'period_ticks': 3600000,
                         'clock_hz': 179712000,
                         'events': [[0, 0, 1, 1], [1800000, 1, 0, 1]]}
            candidate = transformer_candidates.enumerate_candidates(
                assembly['magnetic_graph'])[0]
            deck, _ = steady_supply.deck(assembly, selection, candidate)
            broken = deck.replace('Rwire_intens_3 cable_intens_2 rx_intens',
                                  'Rwire_intens_3 cable_intens_2 wrong_node', 1)
            self.assertNotEqual(deck, broken)
            with self.assertRaisesRegex(ValueError,
                                        'X9:5 cable section 3 disconnected'):
                external.compare(json.loads(external.SOURCE.read_text()),
                                 json.loads(external.ASSEMBLY.read_text()),
                                 broken, output / 'k7222-11-input.xml',
                                 source_pdf_sha256=external.sha(external.SOURCE_PDF))
            xml = output / 'k7222-11-input.xml'
            original_xml = xml.read_bytes()
            tree = ET.parse(xml)
            nodes = {node.get('pin'): node for node in tree.findall('./nets/net/node')
                     if node.get('ref') == 'J990'}
            nodes['1'].set('pin', '3')
            nodes['3'].set('pin', '1')
            tree.write(xml)
            with self.assertRaisesRegex(ValueError, 'physical X9 pin nets differ'):
                external.compare(json.loads(external.SOURCE.read_text()),
                                 json.loads(external.ASSEMBLY.read_text()),
                                 deck, xml,
                                 source_pdf_sha256=external.sha(external.SOURCE_PDF))
            xml.write_bytes(original_xml)
            tree = ET.parse(xml)
            components = tree.find('./components')
            connector = next(comp for comp in components.findall('comp')
                             if comp.get('ref') == 'J990')
            components.remove(connector)
            tree.write(xml)
            with self.assertRaisesRegex(ValueError, 'missing physical X9 connector'):
                external.compare(json.loads(external.SOURCE.read_text()),
                                 json.loads(external.ASSEMBLY.read_text()),
                                 deck, xml,
                                 source_pdf_sha256=external.sha(external.SOURCE_PDF))


if __name__ == '__main__':
    unittest.main()
