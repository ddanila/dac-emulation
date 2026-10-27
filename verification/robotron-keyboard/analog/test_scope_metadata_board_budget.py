import json,shutil,tempfile,unittest
from pathlib import Path
from scope_metadata_board_budget import review
from retained_evidence import check
ROOT=Path(__file__).resolve().parent/'reports/scope-metadata-board-budget'

class ScopeMetadataBoardBudgetTests(unittest.TestCase):
    def test_retained_actual_bridge_scan(self):
        check(ROOT);r=review(ROOT)
        self.assertEqual(r,json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(r['bindings'],dict(scopes=32,registeredObjects=1932,boundSignals=18))
    def mutate(self,names,change):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'evidence';shutil.copytree(ROOT,out)
            for name in names:
                p=out/name;s=p.read_text();new=change(s);self.assertNotEqual(s,new);p.write_text(new)
            with self.assertRaises(ValueError):review(out)
    def test_observation_change_rejected(self):
        self.mutate(['metadata-after.txt'],lambda s:s.replace('VSM_BEGIN 1 0','VSM_BEGIN 1 1'))
    def test_cross_observer_address_mismatch_rejected(self):
        def change(s):
            lines=s.splitlines();a=lines[1].split();a[2]='0x1';lines[1]=' '.join(a);return '\n'.join(lines)+'\n'
        self.mutate(['metadata-references-before.txt','metadata-references-after.txt'],change)
    def test_truncated_metadata_rejected(self):
        self.mutate(['metadata-before.txt','metadata-after.txt'],lambda s:'\n'.join(s.splitlines()[:-1])+'\n')
    def test_nonfinite_cost_rejected(self):
        self.mutate(['metadata-budget.txt'],lambda s:'SCOPE_SCAN metadata 64 nan 1 2\n'+s.splitlines()[1]+'\n')

if __name__=='__main__':unittest.main()
