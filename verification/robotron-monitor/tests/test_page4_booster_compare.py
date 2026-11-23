"""Keep the scanned page-4 booster taps aligned with the model."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page4_booster_compare as check


class Page4BoosterCompareTests(unittest.TestCase):
    def test_source_taps_match_and_reversed_taps_fail(self):
        pdf = ROOT.parents[1] / 'build/monitor/phase-a/sources/older.pdf'
        report = check.run(pdf)
        saved = report
        self.assertTrue(report['passed'])

        with tempfile.TemporaryDirectory() as directory:
            xml = Path(directory) / 'output.xml'
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                            'kicadxml', '-o', str(xml), str(check.SHEET)],
                           check=True, capture_output=True)
            tree = ET.parse(xml)
            nodes = {node.get('pin'): node for net in tree.findall('./nets/net')
                     for node in net.findall('node') if node.get('ref') == 'X1136'}
            nets = {node.get('pin'): net for net in tree.findall('./nets/net')
                    for node in net.findall('node') if node.get('ref') == 'X1136'}
            ports = json.loads(check.TRANSCRIPTION.read_text())['ports']
            pin10 = str(ports.index('X2_10') + 1)
            pin13 = str(ports.index('X2_13') + 1)
            nets[pin10].remove(nodes[pin10])
            nets[pin13].remove(nodes[pin13])
            nets[pin10].append(nodes[pin13])
            nets[pin13].append(nodes[pin10])
            tree.write(xml)
            changed = check.compare(json.loads(check.SOURCE.read_text()),
                                    json.loads(check.TRANSCRIPTION.read_text()), xml)
            self.assertFalse(changed['passed'])
            self.assertFalse(changed['checks']['v16_c26_to_x2_13'])
            self.assertFalse(changed['checks']['c21_to_x2_10'])


if __name__ == '__main__':
    unittest.main()
