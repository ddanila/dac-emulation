import copy,json,unittest
from pathlib import Path
import arithmetic_board as board
ROOT=Path(__file__).resolve().parent/'reports/arithmetic-board-budget'

class ArithmeticBoard(unittest.TestCase):
    def state(self):
        return (board.graph_parse((ROOT/'before.txt').read_text().splitlines()),
                board.parse((ROOT/'types-before.txt').read_text().splitlines()),
                board.parse_arithmetic((ROOT/'arithmetic-before.txt').read_text().splitlines()),
                (ROOT/'board.vvp').read_text())
    def test_retained(self):
        result=board.review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        self.assertGreater(result['projection']['arithmeticLogBytesAtInitialState'],result['arithmeticImageBytes']*result['projection']['normalSnapshotCalls'])
    def test_missing_or_foreign_binding(self):
        graph,types,state,compiled=self.state();bad=copy.deepcopy(state);bad['nodes'].pop()
        with self.assertRaisesRegex(ValueError,'Missing'):board.bind_arithmetic(graph,types,bad,compiled)
        for key in ('node','fun','kind'):
            bad=copy.deepcopy(state);bad['nodes'][0][key]=123456
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'binding'):board.bind_arithmetic(graph,types,bad,compiled)
    def test_width_fallback_and_class(self):
        graph,types,state,compiled=self.state()
        bad=copy.deepcopy(state);bad['nodes'][0]['width']+=1
        with self.assertRaisesRegex(ValueError,'width'):board.bind_arithmetic(graph,types,bad,compiled)
        bad=copy.deepcopy(state);bad['nodes'][0]['vectors'][2]='0'*bad['nodes'][0]['width']
        with self.assertRaisesRegex(ValueError,'fallback'):board.bind_arithmetic(graph,types,bad,compiled)
        bad=copy.deepcopy(types);next(n for n in bad['nodes'] if n['funClass']=='vvp_arith_sum')['funClass']='ExtraSum'
        with self.assertRaisesRegex(ValueError,'Missing'):board.bind_arithmetic(graph,bad,state,compiled)
    def test_clock_and_compiled_population(self):
        graph,types,state,compiled=self.state();state['tick']+=1
        with self.assertRaisesRegex(ValueError,'time mismatch'):board.bind_arithmetic(graph,types,state,compiled)
        state['tick']-=1
        with self.assertRaisesRegex(ValueError,'variants/widths'):board.bind_arithmetic(graph,types,state,compiled+'\nextra .arith/sum 1, a, b;\n')
        with self.assertRaisesRegex(ValueError,'Unadmitted'):board.bind_arithmetic(graph,types,state,compiled+'\nextra .arith/div 1, a, b;\n')

if __name__=='__main__':unittest.main()
