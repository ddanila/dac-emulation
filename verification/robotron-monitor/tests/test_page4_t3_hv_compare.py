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
import page4_t3_hv_compare as hv


class Page4T3HvCompareTests(unittest.TestCase):
    def test_source_hv_edges_match_fresh_export_and_reversed_v21_fails(self):
        pdf = ROOT.parents[1]/'build/monitor/phase-a/sources/older.pdf'
        report = hv.run(pdf)
        saved = report
        self.assertTrue(report['passed'])
        self.assertEqual(len(report['source_edges']), 3)
        self.assertIn('X1:3-to-X2:3', report['unresolved'][0])
        source = json.loads(hv.SOURCE.read_text())
        transcription = json.loads(hv.TRANSCRIPTION.read_text())
        graph = json.loads(hv.GRAPH.read_text())
        with tempfile.TemporaryDirectory() as directory:
            xml = Path(directory)/'output.xml'
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                            'kicadxml', '-o', str(xml), str(hv.SHEET)],
                           check=True, capture_output=True)
            tree = ET.parse(xml)
            diode_nodes = [node for node in tree.findall('./nets/net/node')
                           if node.get('ref') == 'D1132']
            self.assertEqual(len(diode_nodes), 2)
            first, second = diode_nodes
            first.set('pin', '2' if first.get('pin') == '1' else '1')
            second.set('pin', '2' if second.get('pin') == '1' else '1')
            tree.write(xml)
            changed = hv.compare(source, transcription, graph, xml,
                                 pdf_sha256=report['source_pdf_sha256'])
            self.assertFalse(changed['passed'])
            self.assertFalse(changed['checks']['anode_shares_winding_pin'])
            self.assertFalse(changed['checks']['cathode_is_eht'])
            bad_graph = copy.deepcopy(graph)
            bad_graph['groups'][2]['taps'][0] = 'X1_2'
            with self.assertRaisesRegex(ValueError, 'wrapper ports differ'):
                hv.compare(source, transcription, bad_graph, xml,
                           pdf_sha256=report['source_pdf_sha256'])


if __name__ == '__main__':
    unittest.main()
