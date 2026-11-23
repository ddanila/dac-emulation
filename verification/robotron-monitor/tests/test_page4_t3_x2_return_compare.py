import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page4_t3_x2_return_compare as audit


class Page4T3X2ReturnTests(unittest.TestCase):
    def test_wrong_c31_return_is_rejected(self):
        source = json.loads(audit.SOURCE.read_text())
        transcription = json.loads(audit.TRANSCRIPTION.read_text())
        with tempfile.TemporaryDirectory() as directory:
            xml = Path(directory) / 'export.xml'
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                            'kicadxml', '-o', str(xml), str(audit.SHEET)],
                           check=True, capture_output=True, text=True)
            saved = audit.compare(source, transcription, xml)
            self.assertTrue(saved['passed'])
            root = ET.parse(xml).getroot()
            c31 = next(comp.get('ref') for comp in root.findall('./components/comp')
                       if any(field.get('name') == 'SourceId' and
                              field.text == '012-6921:C31'
                              for field in comp.findall('./fields/field')))
            return_net = next(net for net in root.findall('./nets/net')
                              if net.get('name') == '/h_return')
            ground = next(net for net in root.findall('./nets/net')
                          if net.get('name') == '/0')
            c31_pin = next(node for node in return_net.findall('node')
                           if node.get('ref') == c31)
            return_net.remove(c31_pin)
            ground.append(c31_pin)
            ET.ElementTree(root).write(xml)
            changed = audit.compare(source, transcription, xml)
            self.assertFalse(changed['checks']['c31_one_plate_at_x2_4'])
            self.assertFalse(changed['passed'])

    def test_h2_connector_pin_swap_is_rejected(self):
        source = json.loads(audit.SOURCE.read_text())
        transcription = json.loads(audit.TRANSCRIPTION.read_text())
        with tempfile.TemporaryDirectory() as directory:
            xml = Path(directory) / 'export.xml'
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                            'kicadxml', '-o', str(xml), str(audit.SHEET)],
                           check=True, capture_output=True, text=True)
            root = ET.parse(xml).getroot()
            connector = next(comp.get('ref') for comp in root.findall('./components/comp')
                             if any(field.get('name') == 'SourceId' and
                                    field.text == '012-6921:X5'
                                    for field in comp.findall('./fields/field')))
            h2 = next(net for net in root.findall('./nets/net')
                      if net.get('name') == '/hy2')
            pin = next(node for node in h2.findall('node')
                       if node.get('ref') == connector and node.get('pin') == '5')
            pin.set('pin', '4')
            ET.ElementTree(root).write(xml)
            changed = audit.compare(source, transcription, xml)
        self.assertFalse(changed['checks']['h2_reaches_x5_pin5'])
        self.assertFalse(changed['passed'])


if __name__ == '__main__':
    unittest.main()
