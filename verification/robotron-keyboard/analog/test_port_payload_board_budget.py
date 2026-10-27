import copy,json,shutil,tempfile,unittest
from pathlib import Path
from port_payload_board_budget import review,bindings,compiled_ports,parse,metadata_parse,reference_parse,graph_parse
from retained_evidence import check
ROOT=Path(__file__).resolve().parent/'reports/port-payload-board-budget'

class PortPayloadBoardBudgetTests(unittest.TestCase):
    def states(self):
        return [fn((ROOT/name).read_text().splitlines()) for fn,name in ((parse,'port-payload-before.txt'),(metadata_parse,'metadata-before.txt'),(reference_parse,'metadata-references-before.txt'),(graph_parse,'handle-graph.txt'))]+[compiled_ports((ROOT/'io.vvp').read_text())]
    def test_retained_all_board_ports_and_bits(self):
        check(ROOT);r=review(ROOT);self.assertEqual(r,json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(r['portBindings'],dict(ports=317,bits=875,nonNullNetReferences=0,compiledDeclarationsExactlyEqual=True))
    def test_wrong_fields_or_incomplete_families_refuse(self):
        def reorder(s):
            p=next(p for p in s[0]['ports'] if len(p['bits'])>1);p['bits'][0],p['bits'][1]=p['bits'][1],p['bits'][0]
        mutations=[lambda s:s[0]['ports'][0].update(direction=3),lambda s:s[0]['ports'][0].update(index=999),lambda s:s[0]['ports'][0].update(pointer=1),lambda s:s[0]['ports'].pop(),reorder,lambda s:s[4].pop(next(iter(s[4])))]
        base=self.states()
        for i,mutate in enumerate(mutations):
            with self.subTest(mutation=i):
                states=copy.deepcopy(base);mutate(states)
                with self.assertRaises(ValueError):bindings(*states)
    def test_changed_scan_and_invalid_cost_refuse(self):
        for name,change in (('port-payload-after.txt',lambda s:s.replace('VPP_BEGIN 1 0','VPP_BEGIN 1 1')),('port-payload-budget.txt',lambda s:'SCOPE_SCAN ports 64 nan 1 2\n')):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)/'evidence';shutil.copytree(ROOT,out);p=out/name;s=p.read_text();new=change(s);self.assertNotEqual(s,new);p.write_text(new)
                with self.assertRaises(ValueError):review(out)

if __name__=='__main__':unittest.main()
