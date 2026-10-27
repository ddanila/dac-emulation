"""Board mux admission and budgets require complete identity and width coverage."""
import copy,json,unittest
from pathlib import Path
import mux_board as board
ROOT=Path(__file__).resolve().parent/'reports/mux-board-budget'

class BoardMux(unittest.TestCase):
    def state(self):
        return (board.graph_parse((ROOT/'before.txt').read_text().splitlines()),
                board.parse((ROOT/'types-before.txt').read_text().splitlines()),
                board.parse_muxes((ROOT/'muxes-before.txt').read_text().splitlines()),
                (ROOT/'board.vvp').read_text())
    def test_retained(self):
        result=board.review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        self.assertGreater(result['projection']['muxLogBytesAtInitialState'],
                           result['projection']['normalSnapshotCalls']*result['muxImageBytes'])
    def test_missing_and_foreign_bindings(self):
        graph,types,muxes,compiled=self.state()
        bad=copy.deepcopy(muxes);bad['muxes'].pop()
        with self.assertRaisesRegex(ValueError,'Missing'):board.bind_muxes(graph,types,bad,compiled)
        for key in ('node','fun','pending'):
            bad=copy.deepcopy(muxes);bad['muxes'][0][key]=4
            with self.subTest(key=key),self.assertRaises(ValueError):board.bind_muxes(graph,types,bad,compiled)
    def test_wrong_width_class_or_time(self):
        graph,types,muxes,compiled=self.state()
        for key in ('aWidth','bWidth'):
            bad=copy.deepcopy(muxes);bad['muxes'][0][key]+=1
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'widths'):board.bind_muxes(graph,types,bad,compiled)
        bad=copy.deepcopy(types)
        next(n for n in bad['nodes'] if n['funClass']=='vvp_fun_muxz')['funClass']='vvp_fun_muxr'
        with self.assertRaisesRegex(ValueError,'class/graph'):board.bind_muxes(graph,bad,muxes,compiled)
        bad=copy.deepcopy(muxes);bad['tick']+=1
        with self.assertRaisesRegex(ValueError,'time mismatch'):board.bind_muxes(graph,types,bad,compiled)
        with self.assertRaisesRegex(ValueError,'Unsupported compiled'):board.bind_muxes(graph,types,muxes,compiled.replace('.functor MUXZ ','.functor MUXR ',1))
        with self.assertRaisesRegex(ValueError,'Compiled mux widths'):board.bind_muxes(graph,types,muxes,compiled+'\nextra .functor MUXZ 1, a, b, c, C4<>;\n')

if __name__=='__main__':unittest.main()
