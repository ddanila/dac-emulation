import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page18_board_cable_pin_compare as cables
import reference
import steady_supply


class Page18BoardCablePinCompareTests(unittest.TestCase):
    def test_all_four_cables_match_and_swapped_main_pin_fails(self):
        pdf = ROOT.parents[1]/'build/monitor/phase-a/sources/older.pdf'
        report = cables.run(pdf)
        saved = json.loads((ROOT/'reference/k7222-11/page18-board-cable-pin-comparison.json').read_text())
        self.assertEqual(report, saved)
        self.assertTrue(report['passed'])
        self.assertEqual(report['cable_pairs_checked'], 18)
        self.assertEqual(report['labelled_connector_pins_checked'], 36)
        self.assertEqual(report['functional_board_nets_both_present'], 15)
        self.assertEqual(len(report['functional_model_scope_gaps']), 3)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'assembly'
            model = steady_supply.assemble(output)
            exports = {connector: output/(stem+'.xml')
                       for connector, stem in cables.SHEETS.items()}
            xml = exports['012-6921:X6']
            tree = ET.parse(xml)
            nodes = {node.get('pin'): node for node in tree.findall('./nets/net/node')
                     if node.get('ref') == 'J960'}
            self.assertEqual(set(nodes), {'2', '3'})
            nodes['2'].set('pin', '3')
            nodes['3'].set('pin', '2')
            tree.write(xml)
            changed = cables.compare(json.loads(cables.SOURCE.read_text()),
                                     json.loads(cables.ASSEMBLY.read_text()),
                                     exports, model['components'],
                                     pdf_sha256=report['source_pdf_sha256'])
            self.assertFalse(changed['passed'])
            self.assertEqual({row['pin'] for row in changed['pin_misses']
                              if row['connector'] == '012-6921:X6'}, {'2', '3'})
            inventory = json.loads((ROOT/'reference/k7222-11/inventory.json').read_text())
            with self.assertRaisesRegex(ValueError, 'source connector pins differ'):
                reference.source_connectivity(xml, inventory, '012-6921')


if __name__ == '__main__':
    unittest.main()
