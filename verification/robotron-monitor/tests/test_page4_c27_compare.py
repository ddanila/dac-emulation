"""Keep the source-visible collector capacitor connection separate from C30."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page4_c27_compare as check


class Page4C27CompareTests(unittest.TestCase):
    def test_source_branch_matches_and_miswired_c27_fails(self):
        pdf = ROOT.parents[1]/'build/monitor/phase-a/sources/older.pdf'
        report = check.run(pdf)
        saved = report
        self.assertTrue(report['passed'])
        self.assertTrue(report['model_c30_parallel_to_c27'])
        self.assertFalse(report['c30_source_placement_verified'])

        with tempfile.TemporaryDirectory() as directory:
            xml = Path(directory)/'output.xml'
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                            'kicadxml', '-o', str(xml), str(check.SHEET)],
                           check=True, capture_output=True)
            tree = ET.parse(xml)
            c27 = next(node for node in tree.findall('./nets/net/node')
                       if node.get('ref') == 'C1108' and node.get('pin') == '1')
            original_net = next(net for net in tree.findall('./nets/net')
                                if c27 in net.findall('node'))
            original_net.remove(c27)
            different_net = next(net for net in tree.findall('./nets/net')
                                 if net.get('name') == '/h_feed')
            different_net.append(c27)
            tree.write(xml)
            changed = check.compare(json.loads(check.SOURCE.read_text()),
                                    json.loads(check.TRANSCRIPTION.read_text()), xml)
            self.assertFalse(changed['passed'])
            self.assertFalse(changed['checks']['c27_between_collector_and_return'])


if __name__ == '__main__':
    unittest.main()
