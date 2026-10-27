import json,shutil,tempfile,unittest
from pathlib import Path
from scope_metadata_compact_budget import review
from retained_evidence import check
ROOT=Path(__file__).resolve().parent/'reports/scope-metadata-compact-board-budget'

class ScopeMetadataCompactBudgetTests(unittest.TestCase):
    def test_retained_board_reconstruction_and_cost(self):
        check(ROOT);r=review(ROOT);self.assertEqual(r,json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(sum(v['records'] for v in r['compactMeasurements'].values()),128)
        self.assertEqual(sum(v['compactBytes'] for v in r['compactMeasurements'].values()),106546)
    def mutate(self,name,change):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'evidence';shutil.copytree(ROOT,out);p=out/name;s=p.read_text();new=change(s);self.assertNotEqual(s,new);p.write_text(new)
            with self.assertRaises(ValueError):review(out)
    def test_lost_record_rejected(self):
        self.mutate('metadata-compact.txt',lambda s:s.replace('VSMD_BEGIN 1 0 2 0 40308\nVSMD_END\n',''))
    def test_changed_dense_state_rejected(self):
        self.mutate('metadata-compact-after.txt',lambda s:s.replace('VSM_BEGIN 1 0','VSM_BEGIN 1 1'))
    def test_compact_payload_must_match_dense(self):
        self.mutate('metadata-compact.txt',lambda s:s.replace('VSM_TIME 0 0 0','VSM_TIME 1 0 0',1))
    def test_invalid_cost_rejected(self):
        def change(s):
            lines=s.splitlines();a=lines[0].split();a[-1]='nan';lines[0]=' '.join(a);return '\n'.join(lines)+'\n'
        self.mutate('metadata-compact-budget.txt',change)

if __name__=='__main__':unittest.main()
