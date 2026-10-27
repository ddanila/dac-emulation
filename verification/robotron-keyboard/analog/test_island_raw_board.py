import copy,json,shutil,tempfile,unittest
from pathlib import Path
from island_raw_board import HERE,review,bind_islands,graph_parse,parse_types,parse_raw,parse_snapshot
ROOT=HERE/'reports/island-raw-board-budget'

class IslandRawBoard(unittest.TestCase):
    def state(self):
        return [graph_parse((ROOT/'before.txt').read_text().splitlines()),parse_types((ROOT/'types-before.txt').read_text().splitlines()),parse_raw((ROOT/'island_raw-before.txt').read_text().splitlines()),parse_snapshot((ROOT/'island-legacy-before.txt').read_text().splitlines()),(ROOT/'board.vvp').read_text()]
    def test_retained_budget_replay(self):
        self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_initial_pending_islands_are_preserved(self):
        r=review(ROOT);self.assertEqual(r['pendingIslands'],r['islandBindings']['islands']);self.assertGreater(r['pendingIslands'],0)
    def test_unknown_native_port_class_rejected(self):
        args=self.state();node=next(n for n in args[1]['nodes'] if n['funClass']=='vvp_island_port');node['funClass']='ExtraPort'
        with self.assertRaises(ValueError):bind_islands(*args)
    def test_port_graph_binding_required(self):
        args=self.state();port=args[2]['islands'][0]['ports'][0];key=port['net'];node=next(n for n in args[0]['nodes'] if n['key']==key);typed=next(n for n in args[1]['nodes'] if n['key']==key);node['fun']+=8;typed['fun']+=8
        with self.assertRaises(ValueError):bind_islands(*args)
    def test_compiled_control_polarity_required(self):
        args=self.state();self.assertIn('.tranif1 ',args[4]);args[4]=args[4].replace('.tranif1 ','.tranif0 ',1)
        with self.assertRaises(ValueError):bind_islands(*args)
    def test_unadmitted_partselect_rejected(self):
        args=self.state();args[3]['islands'][0]['branches'][0]['width']=8
        with self.assertRaises(ValueError):bind_islands(*args)
    def test_graph_time_binding_required(self):
        args=self.state();args[0]['tick']=args[1]['tick']=1
        with self.assertRaises(ValueError):bind_islands(*args)
    def test_compact_population_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/'island_raw-delta-after.txt';s=p.read_text();self.assertIn('VIX_BEGIN D 0 2 0',s);p.write_text(s.replace('VIX_BEGIN D 0 2 0','VIX_BEGIN D 0 3 0'))
            with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
