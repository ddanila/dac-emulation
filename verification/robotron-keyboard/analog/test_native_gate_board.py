"""Board gates require complete class, inversion, width and allocation bindings."""
import copy,json,unittest
from pathlib import Path
import native_gate_board as board
ROOT=Path(__file__).resolve().parent/'reports/gate-board-budget'

class GateBoard(unittest.TestCase):
    def state(self):
        return (board.graph_parse((ROOT/'before.txt').read_text().splitlines()),
                board.parse((ROOT/'types-before.txt').read_text().splitlines()),
                board.parse_gates((ROOT/'gates-before.txt').read_text().splitlines()),
                (ROOT/'board.vvp').read_text())
    def test_retained(self):
        result=board.review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        self.assertGreater(result['projection']['gateLogBytesAtInitialState'],result['gateImageBytes']*result['projection']['normalSnapshotCalls'])
    def test_missing_or_foreign_binding(self):
        graph,types,gates,compiled=self.state();bad=copy.deepcopy(gates);bad['gates'].pop()
        with self.assertRaisesRegex(ValueError,'Missing'):board.bind_gates(graph,types,bad,compiled)
        for key in ('node','fun','pending'):
            bad=copy.deepcopy(gates);bad['gates'][0][key]=4
            with self.subTest(key=key),self.assertRaises(ValueError):board.bind_gates(graph,types,bad,compiled)
    def test_wrong_inversion_width_or_class(self):
        graph,types,gates,compiled=self.state()
        bad=copy.deepcopy(gates);next(g for g in bad['gates'] if g['kind']==1)['invert']^=1
        with self.assertRaisesRegex(ValueError,'variants/widths'):board.bind_gates(graph,types,bad,compiled)
        bad=copy.deepcopy(gates);bad['gates'][0]['inputs']=[v+'0' for v in bad['gates'][0]['inputs']]
        with self.assertRaisesRegex(ValueError,'variants/widths'):board.bind_gates(graph,types,bad,compiled)
        bad=copy.deepcopy(types);next(n for n in bad['nodes'] if n['funClass']=='vvp_fun_and')['funClass']='ExtraAnd'
        with self.assertRaisesRegex(ValueError,'Missing'):board.bind_gates(graph,bad,gates,compiled)
    def test_clock_and_compiled_population(self):
        graph,types,gates,compiled=self.state();gates['tick']+=1
        with self.assertRaisesRegex(ValueError,'time mismatch'):board.bind_gates(graph,types,gates,compiled)
        gates['tick']-=1
        with self.assertRaisesRegex(ValueError,'variants/widths'):board.bind_gates(graph,types,gates,compiled+'\nextra .functor NAND 1, a, b, c, d;\n')

if __name__=='__main__':unittest.main()
