import copy,json,unittest
from pathlib import Path
import reduction_board as board
ROOT=Path(__file__).resolve().parent/'reports/reduction-board-budget'

class ReductionBoard(unittest.TestCase):
    def state(self):
        return (board.graph_parse((ROOT/'before.txt').read_text().splitlines()),
                board.parse((ROOT/'types-before.txt').read_text().splitlines()),
                board.parse_reduction((ROOT/'reduction-before.txt').read_text().splitlines()),
                (ROOT/'board.vvp').read_text())
    def test_retained(self):
        result=board.review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        self.assertGreater(result['observedCacheWidths']['0'],0)
        self.assertGreater(result['projection']['reductionLogBytesAtInitialState'],result['reductionImageBytes']*result['projection']['normalSnapshotCalls'])
    def test_missing_or_foreign_binding(self):
        graph,types,state,compiled=self.state();bad=copy.deepcopy(state);bad['nodes'].pop()
        with self.assertRaisesRegex(ValueError,'Missing'):board.bind_reduction(graph,types,bad,compiled)
        for key in ('node','fun','kind'):
            bad=copy.deepcopy(state);bad['nodes'][0][key]=123456
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'binding'):board.bind_reduction(graph,types,bad,compiled)
    def test_class_admission(self):
        graph,types,state,compiled=self.state()
        bad=copy.deepcopy(types);next(n for n in bad['nodes'] if n['funClass']=='vvp_reduce_nor')['funClass']='ExtraNor'
        with self.assertRaisesRegex(ValueError,'Missing'):board.bind_reduction(graph,bad,state,compiled)
    def test_clock_and_compiled_population(self):
        graph,types,state,compiled=self.state();state['tick']+=1
        with self.assertRaisesRegex(ValueError,'time mismatch'):board.bind_reduction(graph,types,state,compiled)
        state['tick']-=1
        with self.assertRaisesRegex(ValueError,'families differ'):board.bind_reduction(graph,types,state,compiled+'\nextra .reduce/nor a;\n')
        with self.assertRaisesRegex(ValueError,'Unadmitted'):board.bind_reduction(graph,types,state,compiled+'\nextra .reduce/custom a;\n')

if __name__=='__main__':unittest.main()
