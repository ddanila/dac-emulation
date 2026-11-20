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
    def test_source_path_and_two_backends_retain_four_candidates(self):
        sources = ROOT.parents[1]/'build/monitor/phase-a/sources'
        report = sign.run(sources/'older.pdf', sources/'k7222_61.pdf')
        saved = json.loads((ROOT/'reference/k7222-11/t3-g1-polarity-filter.json').read_text())
        self.assertEqual(report, saved)
        self.assertTrue(report['passed'])
        self.assertFalse(report['historical_polarity_verified'])
        self.assertEqual(len(report['accepted_candidate_ids']), 4)
        design = json.loads((ROOT/'reference/k7222-11/design-point.json').read_text())
        self.assertEqual(design['conditional_t3_g1_polarity_screen']['accepted_candidate_ids'],
                         report['accepted_candidate_ids'])

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
