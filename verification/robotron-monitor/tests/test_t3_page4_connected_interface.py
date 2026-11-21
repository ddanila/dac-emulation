"""Exercise the source-visible T3 interface through the connected assembler."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import steady_supply
import transformer_candidates
from test_frames import capture


class T3Page4ConnectedInterfaceTests(unittest.TestCase):
    def test_connected_deck_uses_checked_twenty_port_export(self):
        with tempfile.TemporaryDirectory() as directory:
            assembly = steady_supply.assemble(
                Path(directory) / 'assembly', t3_interface='page4-visible-20-port')
            graph = assembly['magnetic_graph']
            candidate = transformer_candidates.enumerate_candidates(graph)[0]
            deck, metadata = steady_supply.deck(
                assembly, steady_supply.select(capture()), candidate,
                magnetic_backend='coupled')

            wrapper = json.loads((ROOT / 'reference/k7222-11/page4-t3-visible-wrapper-comparison.json').read_text())
            graph_ports = [port for group in graph['groups'] for port in group['taps']]
            t3 = next(part for part in assembly['components']
                      if part['source_id'] == '012-6921:T3')
            self.assertEqual(t3['nodes'], [wrapper['exported_nodes'][port] for port in graph_ports])
            self.assertEqual(t3['value'], 'T3_PAGE4_INTERFACE')
            self.assertEqual(metadata['candidate']['ports'], graph_ports)
            self.assertEqual(metadata['t3_interface'], 'page4-visible-20-port')
            self.assertIn('.subckt T3_PAGE4_INTERFACE ' + ' '.join(graph_ports), deck)
            self.assertIn('X1136 ' + ' '.join(t3['nodes']) + ' T3_PAGE4_INTERFACE', deck)
            self.assertIn('reference/k7222-11/t3-page4-visible-graph.json', assembly['hashes'])
            self.assertIn('reference/k7222-11/t3-page4-provisional-parameters.json', assembly['hashes'])
            self.assertTrue(any('internal section order' in note for note in metadata['assumptions']))

    def test_unbound_return_variant_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unsupported T3 interface/return combination'):
            steady_supply.deck(
                {'t3_interface': 'page4-visible-20-port',
                 't3_return_variant': 'hv-only-grounded'},
                {'status': 'complete'}, {}, magnetic_backend='coupled')
        with self.assertRaisesRegex(ValueError, 'requires the coupled magnetic backend'):
            steady_supply.deck(
                {'t3_interface': 'page4-visible-20-port'},
                {'status': 'complete'}, {}, magnetic_backend='flux')

    @unittest.skipUnless(shutil.which('ngspice'), 'ngspice is unavailable')
    def test_connected_candidate_runs_short_solver_parse(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assembly = steady_supply.assemble(
                root / 'assembly', t3_interface='page4-visible-20-port')
            candidate = transformer_candidates.enumerate_candidates(
                assembly['magnetic_graph'])[0]
            deck, _ = steady_supply.deck(
                assembly, steady_supply.select(capture()), candidate,
                magnetic_backend='coupled')
            short = '\n'.join(
                '.tran 100n 5us 0 100n' if line.startswith('.tran ') else line
                for line in deck.splitlines()) + '\n'
            path = root / 'connected-page4.cir'
            path.write_text(short)
            result = subprocess.run(
                ['ngspice', '-b', '-r', str(root / 'trace.raw'),
                 '-o', str(root / 'solver.log'), str(path)],
                cwd=root, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, (root / 'solver.log').read_text())
            self.assertIn('No. of Data Rows', (root / 'solver.log').read_text())
            self.assertTrue((root / 'trace.raw').is_file())


if __name__ == '__main__':
    unittest.main()
