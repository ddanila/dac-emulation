import copy,json,unittest
from pathlib import Path
import resolver_board as board
ROOT=Path(__file__).resolve().parent/'reports/resolver-board-budget'

class ResolverBoard(unittest.TestCase):
    def state(self):
        return (board.graph_parse((ROOT/'before.txt').read_text().splitlines()),
                board.parse((ROOT/'types-before.txt').read_text().splitlines()),
                board.parse_resolver((ROOT/'resolver-before.txt').read_text().splitlines()),
                (ROOT/'board.vvp').read_text())
    def test_retained(self):
        result=board.review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        self.assertGreater(result['projection']['resolverLogBytesAtInitialState'],result['resolverImageBytes']*result['projection']['normalSnapshotCalls'])
    def test_missing_and_foreign_objects(self):
        graph,types,state,compiled=self.state();bad=copy.deepcopy(state);bad['nodes'].pop()
        with self.assertRaisesRegex(ValueError,'Missing'):board.bind_resolver(graph,types,bad,compiled)
        for key in ('node','fun','kind'):
            bad=copy.deepcopy(state);bad['nodes'][0][key]=123456
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'binding'):board.bind_resolver(graph,types,bad,compiled)
    def test_allocation_bounds_and_identity(self):
        graph,types,state,compiled=self.state()
        for key in ('slots','ports','values','output'):
            bad=copy.deepcopy(state);bad['nodes'][0][key]=123456
            with self.subTest(key=key),self.assertRaises(ValueError):board.bind_resolver(graph,types,bad,compiled)
        bad=copy.deepcopy(state);bad['nodes'][1]['allocation']=bad['nodes'][1]['values']=bad['nodes'][0]['allocation']
        with self.assertRaisesRegex(ValueError,'aliased'):board.bind_resolver(graph,types,bad,compiled)
        bad=copy.deepcopy(state);bad['nodes'][0]['vectors'].pop()
        with self.assertRaisesRegex(ValueError,'bounds'):board.bind_resolver(graph,types,bad,compiled)
    def test_compiled_pull_and_family(self):
        graph,types,state,compiled=self.state();bad=copy.deepcopy(state);bad['nodes'][0]['pull']=0x55
        with self.assertRaisesRegex(ValueError,'ports/pulls'):board.bind_resolver(graph,types,bad,compiled)
        bad['nodes'][0]['pull']=0xee
        with self.assertRaisesRegex(ValueError,'pull'):board.bind_resolver(graph,types,bad,compiled)
        with self.assertRaisesRegex(ValueError,'Unaudited'):board.bind_resolver(graph,types,state,compiled+'\nextra .resolv unknown, a, b;\n')
    def test_class_admission(self):
        graph,types,state,compiled=self.state()
        next(n for n in types['nodes'] if n['funClass']=='resolv_tri')['funClass']='ExtraResolver'
        with self.assertRaises(ValueError):board.bind_resolver(graph,types,state,compiled)
    def test_time_binding(self):
        graph,types,state,compiled=self.state();state['tick']+=1
        with self.assertRaisesRegex(ValueError,'time mismatch'):board.bind_resolver(graph,types,state,compiled)

if __name__=='__main__':unittest.main()
