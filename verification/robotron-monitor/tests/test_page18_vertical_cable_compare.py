import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page18_vertical_cable_compare as cable
import reference


class Page18VerticalCableCompareTests(unittest.TestCase):
    def test_fresh_exports_match_source_and_pin_swap_fails(self):
        pdf = ROOT.parents[1]/'build/monitor/phase-a/sources/older.pdf'
        report = cable.run(pdf)
        saved = report
        self.assertTrue(report['passed'])
        self.assertEqual(report['connector_pins_checked'], 12)
        self.assertEqual(report['cable_pairs_checked'], 6)
        source = json.loads(cable.SOURCE.read_text())
        with tempfile.TemporaryDirectory() as directory:
            exports = {}
            for connector, sheet in cable.SHEETS.items():
                xml = Path(directory)/(connector.replace(':', '-')+'.xml')
                subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                                'kicadxml', '-o', str(xml), str(sheet)],
                               check=True, capture_output=True)
                exports[connector] = xml
            changed = copy.deepcopy(source)
            changed['connectors']['012-6921:X4']['3'] = '12P'
            changed['connectors']['012-6931:X3']['3'] = '12P'
            self.assertFalse(cable.compare(changed, exports,
                                           pdf_sha256=report['source_pdf_sha256'])['passed'])
            tree = ET.parse(exports['012-6931:X3'])
            nodes = {node.get('pin'): node for node in tree.findall('./nets/net/node')
                     if node.get('ref') == 'J931'}
            nodes['3'].set('pin', '4')
            nodes['4'].set('pin', '3')
            tree.write(exports['012-6931:X3'])
            changed_report = cable.compare(source, exports, pdf_sha256=report['source_pdf_sha256'])
            self.assertFalse(changed_report['passed'])
            self.assertEqual([row['to_pin'] for row in changed_report['pin_pairs']
                              if row['vertical_board_net'] != row['expected_model_net']], ['3', '4'])
            inventory = json.loads((ROOT/'reference/k7222-11/inventory.json').read_text())
            with self.assertRaisesRegex(ValueError, 'source connector pins differ'):
                reference.source_connectivity(exports['012-6931:X3'], inventory, '012-6931')


if __name__ == '__main__':
    unittest.main()
