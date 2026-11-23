"""Check the corrected external tie and its connected magnetic port mapping."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import t3_page4_upper_bridge_candidate as corrected
import transformer_candidates as tc


class UpperBridgeCandidateTests(unittest.TestCase):
    def test_exported_wire_does_not_short_a_winding_group(self):
        source_pdf = ROOT.parents[1] / 'build/monitor/phase-a/sources/older.pdf'
        with tempfile.TemporaryDirectory() as directory:
            assembly = corrected.assemble(Path(directory) / 'assembly', source_pdf)
            receipt = assembly['upper_bridge_correction']
            self.assertTrue(all(receipt['checks'].values()))
            nodes = receipt['exported_nodes']
            self.assertEqual(nodes['X1_1'], nodes['X1_7'])
            self.assertNotEqual(nodes['X1_1'], nodes['X1_2'])
            self.assertEqual(nodes['X1_2'], nodes['X2_3'])
            graph = assembly['magnetic_graph']
            parameters = assembly['magnetic_parameters']
            ports = [port for group in graph['groups'] for port in group['taps']]
            component = next(part for part in assembly['components'] if part['source_id'] == '012-6921:T3')
            self.assertEqual(component['nodes'], [nodes[p] for p in ports])
            candidates = tc.enumerate_candidates(graph)
            self.assertEqual(len(candidates), 16)
            for candidate in candidates:
                _, model = tc.compile_model(graph, candidate, parameters, backend='coupled')
                self.assertEqual(model['ports'], ports)
                self.assertEqual(len(model['sections']), 15)
                self.assertEqual(len([s for s in model['sections'] if s['group'] == 'high_voltage']), 1)
                self.assertFalse(any(s['terminals'] == ['X1_1', 'X1_2'] for s in model['sections']))
            base = json.loads((ROOT / 'reference/k7222-11/t3-page4-provisional-parameters.json').read_text())
            self.assertEqual(len(base['groups']['high_voltage']), 5)
            self.assertFalse(receipt['a5_qualified'])


if __name__ == '__main__':
    unittest.main()
