import copy,json,unittest
from pathlib import Path
import concat_board as board
ROOT=Path(__file__).resolve().parent/'reports/concat-board-budget'

class ConcatBoard(unittest.TestCase):
    def state(self):
        return (board.graph_parse((ROOT/'before.txt').read_text().splitlines()),
                board.parse((ROOT/'types-before.txt').read_text().splitlines()),
                board.parse_concat((ROOT/'concat-before.txt').read_text().splitlines()),
                (ROOT/'board.vvp').read_text())
    def test_retained(self):
        result=board.review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        self.assertGreater(result['projection']['concatLogBytesAtInitialState'],result['concatImageBytes']*result['projection']['normalSnapshotCalls'])
    def test_missing_or_foreign_binding(self):
        graph,types,state,compiled=self.state();bad=copy.deepcopy(state);bad['nodes'].pop()
        with self.assertRaisesRegex(ValueError,'Missing'):board.bind_concat(graph,types,bad,compiled)
        for key in ('node','fun','kind'):
            bad=copy.deepcopy(state);bad['nodes'][0][key]=123456
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'binding'):board.bind_concat(graph,types,bad,compiled)
    def test_class_admission(self):
        graph,types,state,compiled=self.state()
        bad=copy.deepcopy(types);next(n for n in bad['nodes'] if n['funClass']=='vvp_fun_concat')['funClass']='ExtraConcat4'
        with self.assertRaisesRegex(ValueError,'Missing'):board.bind_concat(graph,bad,state,compiled)
    def test_widths_and_compiled_population(self):
        graph,types,state,compiled=self.state();bad=copy.deepcopy(state);bad['nodes'][0]['width']+=1
        with self.assertRaisesRegex(ValueError,'width'):board.bind_concat(graph,types,bad,compiled)
        bad=copy.deepcopy(state);bad['nodes'][0]['widths'][0]+=1;bad['nodes'][0]['widths'][1]-=1
        with self.assertRaisesRegex(ValueError,'port widths differ'):board.bind_concat(graph,types,bad,compiled)
        with self.assertRaisesRegex(ValueError,'Unadmitted'):board.bind_concat(graph,types,state,compiled+'\nextra .concat9 [1 0 0 0], a;\n')
    def test_pending_and_event_bindings(self):
        graph,types,state,compiled=self.state();n=state['nodes'][0];n['pending']=n['node']
        with self.assertRaisesRegex(ValueError,'without queued'):board.bind_concat(graph,types,state,compiled)
        e=dict(key=n['event'],id=1,delete=0,slot=0,region='active',ordinal=0);state['events']=[e]
        board.bind_concat(graph,types,state,compiled)
        e['region']='executing';e['slot']=-2
        with self.assertRaisesRegex(ValueError,'executing'):board.bind_concat(graph,types,state,compiled)
        n['pending']=0;board.bind_concat(graph,types,state,compiled)
        e['key']=123456
        with self.assertRaisesRegex(ValueError,'wrapper'):board.bind_concat(graph,types,state,compiled)
    def test_time_binding(self):
        graph,types,state,compiled=self.state();state['tick']+=1
        with self.assertRaisesRegex(ValueError,'time mismatch'):board.bind_concat(graph,types,state,compiled)

if __name__=='__main__':unittest.main()
