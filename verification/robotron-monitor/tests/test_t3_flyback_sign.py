import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import t3_flyback_sign as sign


class T3FlybackSignTests(unittest.TestCase):

    def test_reversed_damper_pin_breaks_source_path(self):
        with tempfile.TemporaryDirectory() as directory:
            xml = Path(directory)/'horizontal-output.xml'
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                            'kicadxml', '-o', str(xml), str(sign.SHEET)],
                           check=True, capture_output=True)
            tree = ET.parse(xml)
            nodes = [node for node in tree.findall('./nets/net/node')
                     if node.get('ref') == 'D1129']
            self.assertEqual(len(nodes), 2)
            for node in nodes:
                node.set('pin', '2' if node.get('pin') == '1' else '1')
            tree.write(xml)
            read = json.loads(sign.READ.read_text())
            graph = json.loads(sign.GRAPH.read_text())
            transcription = json.loads(sign.TRANSCRIPTION.read_text())
            path = sign.source_checks(read, graph, transcription, xml)
            self.assertFalse(path['checks']['damper_anode_is_ground'])
            self.assertFalse(path['checks']['damper_cathode_shares_drive_pin_7'])


if __name__ == '__main__':
    unittest.main()
