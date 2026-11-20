"""Keep the source-read page-9 oscillator-to-ramp diode direction checked."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page9_v12_bridge_compare as bridge


class Page9V12BridgeTests(unittest.TestCase):
    def test_fresh_export_matches_source_and_reversed_diode_fails(self):
        source = json.loads(bridge.SOURCE.read_text())
        saved = json.loads((ROOT/'reference/k7222-11/page9-v12-bridge-comparison.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            paths = []
            for sheet in (bridge.OSCILLATOR, bridge.INTEGRATOR):
                xml = folder/(sheet.stem+'.xml')
                subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                                'kicadxml', '-o', str(xml), str(sheet)],
                               check=True, capture_output=True, text=True)
                paths.append(xml)
            live = bridge.compare(source, *paths)
            self.assertEqual(live, saved)
            self.assertTrue(live['passed'])
            tree = ET.parse(paths[1])
            for net in tree.getroot().findall('./nets/net'):
                for node in net.findall('node'):
                    if node.get('ref') == 'D604':
                        node.set('pin', '2' if node.get('pin') == '1' else '1')
            reversed_xml = folder/'reversed-v12.xml'
            tree.write(reversed_xml)
            reversed_result = bridge.compare(source, paths[0], reversed_xml)
            self.assertFalse(reversed_result['passed'])
            self.assertFalse(reversed_result['checks']['cathode_to_oscillator_pulse'])
            self.assertFalse(reversed_result['checks']['anode_to_a2_positive_input'])
            oscillator_tree = ET.parse(paths[0])
            v11_ref = next(c.get('ref') for c in
                           oscillator_tree.getroot().findall('./components/comp')
                           if any(p.get('name') == 'SourceId' and
                                  p.get('value') == '012-6931:V11'
                                  for p in c.findall('property')))
            for net in oscillator_tree.getroot().findall('./nets/net'):
                for node in net.findall('node'):
                    if node.get('ref') == v11_ref and node.get('pin') in ('1', '3'):
                        node.set('pin', '3' if node.get('pin') == '1' else '1')
            reversed_transistor = folder/'reversed-v11.xml'
            oscillator_tree.write(reversed_transistor)
            reversed_v11 = bridge.compare(source, reversed_transistor, paths[1])
            self.assertFalse(reversed_v11['passed'])
            self.assertFalse(reversed_v11['checks']['cathode_to_oscillator_pulse'])
            self.assertFalse(reversed_v11['checks']['v11_base_and_emitter'])


if __name__ == '__main__':
    unittest.main()
