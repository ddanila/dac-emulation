import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page18_yoke_pin_compare as yoke
import reference
import steady_supply
import transformer_candidates


class Page18YokePinCompareTests(unittest.TestCase):
    def test_source_yoke_pins_and_assembled_windings(self):
        pdf = ROOT.parents[1]/'build/monitor/phase-a/sources/older.pdf'
        report = yoke.run(pdf)
        saved = json.loads((ROOT/'reference/k7222-11/page18-yoke-pin-comparison.json').read_text())
        self.assertEqual(report, saved)
        self.assertTrue(report['passed'])
        self.assertEqual(report['board_connector_pins_checked'], 6)
        self.assertEqual(report['yoke_terminals_checked'], 4)
        self.assertEqual([(row['yoke_pin'], row['board_pin']) for row in report['yoke_terminals']],
                         [('1', '6'), ('3', '5'), ('4', '4'), ('6', '3')])

    def test_swapped_connector_pins_and_winding_endpoint_fail(self):
        pdf = ROOT.parents[1]/'build/monitor/phase-a/sources/older.pdf'
        source = json.loads(yoke.SOURCE.read_text())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'assembly'
            assembly = steady_supply.assemble(output)
            selection = {'status': 'complete', 'period_ticks': 3600000,
                         'clock_hz': 179712000, 'events': [[0, 0, 1, 1], [1800000, 1, 0, 1]]}
            candidate = transformer_candidates.enumerate_candidates(assembly['magnetic_graph'])[0]
            deck, _ = steady_supply.deck(assembly, selection, candidate)
            xml = output/'k7222-11-vertical-output.xml'
            changed_deck = deck.replace('Lvertical v_winding y2 ', 'Lvertical v_winding hy2 ', 1)
            wrong_winding = yoke.compare(source, xml, changed_deck, pdf_sha256=yoke.sha(pdf))
            self.assertFalse(wrong_winding['passed'])
            self.assertEqual([row['element'] for row in wrong_winding['winding_misses']], ['Lvertical'])
            tree = ET.parse(xml)
            nodes = {node.get('pin'): node for node in tree.findall('./nets/net/node')
                     if node.get('ref') == 'J920'}
            nodes['3'].set('pin', '4')
            nodes['4'].set('pin', '3')
            tree.write(xml)
            wrong_pins = yoke.compare(source, xml, deck, pdf_sha256=yoke.sha(pdf))
            self.assertFalse(wrong_pins['passed'])
            self.assertEqual({row['pin'] for row in wrong_pins['pin_misses']}, {'3', '4'})
            inventory = json.loads((ROOT/'reference/k7222-11/inventory.json').read_text())
            with self.assertRaisesRegex(ValueError, 'source connector pins differ'):
                reference.source_connectivity(xml, inventory, '012-6931')


if __name__ == '__main__':
    unittest.main()
