import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import t3_g1_polarity_filter as sign


class T3G1PolarityTests(unittest.TestCase):

    def test_reversed_v14_breaks_source_path(self):
        with tempfile.TemporaryDirectory() as directory:
            xml = Path(directory)/'horizontal-output.xml'
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                            'kicadxml', '-o', str(xml), str(sign.SHEET)],
                           check=True, capture_output=True)
            tree = ET.parse(xml)
            refs = {component.get('ref') for component in tree.findall('./components/comp')
                    if any(field.get('name') == 'SourceId' and field.text == '012-6921:V14'
                           for field in component.findall('./fields/field'))}
            self.assertEqual(len(refs), 1)
            nodes = [node for node in tree.findall('./nets/net/node')
                     if node.get('ref') in refs]
            self.assertEqual(len(nodes), 2)
            for node in nodes:
                node.set('pin', '2' if node.get('pin') == '1' else '1')
            tree.write(xml)
            path = sign.check_path(json.loads(sign.READ.read_text()),
                                   json.loads(sign.TRANSCRIPTION.read_text()),
                                   json.loads(sign.TARGETS.read_text()), xml)
            self.assertFalse(path['checks']['v14_cathode_at_x2_6'])
            self.assertFalse(path['checks']['v14_anode_at_c18'])


if __name__ == '__main__':
    unittest.main()
