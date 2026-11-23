"""Check the page-9 oscillator source comparison and transistor pin polarity."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page9_oscillator_compare as oscillator


class Page9OscillatorTests(unittest.TestCase):
    def test_fresh_export_and_v5_collector_emitter_mutation(self):
        source = json.loads(oscillator.SOURCE.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            xml = Path(tmp)/'oscillator.xml'
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                            'kicadxml', '-o', str(xml), str(oscillator.SHEET)],
                           check=True, capture_output=True, text=True)
            live = oscillator.compare(source, xml)
            saved = live
            self.assertTrue(live['passed'])
            tree = ET.parse(xml)
            v5_ref = next(c.get('ref') for c in
                          tree.getroot().findall('./components/comp')
                          if any(p.get('name') == 'SourceId' and
                                 p.get('value') == '012-6931:V5'
                                 for p in c.findall('property')))
            for net in tree.getroot().findall('./nets/net'):
                for node in net.findall('node'):
                    if node.get('ref') == v5_ref and node.get('pin') in ('1', '3'):
                        node.set('pin', '3' if node.get('pin') == '1' else '1')
            reversed_xml = Path(tmp)/'v5-ce-reversed.xml'
            tree.write(reversed_xml)
            reversed_result = oscillator.compare(source, reversed_xml)
            self.assertFalse(reversed_result['passed'])
            self.assertFalse(reversed_result['checks']['timing'])
            self.assertFalse(reversed_result['checks']['emitter'])


if __name__ == '__main__':
    unittest.main()
