import copy,json,shutil,tempfile,unittest
from pathlib import Path
from scope_signals import HERE,review
from scope_payload_gaps import review as gap_review
from scope_signals_board_budget import review as board_review,bindings
from scope_metadata_bindings import parse as joined_parse
from net_probe import parse as graph_parse
from retained_evidence import check
ROOT=HERE/'reports/scope-signals'

class ScopeSignalTests(unittest.TestCase):
    def test_retained_native_regression_and_initialized_board(self):
        check(ROOT)
        for root,fn in ((ROOT,review),(ROOT/'old-gaps',gap_review),(ROOT/'board-budget',board_review)):
            self.assertEqual(fn(root),json.loads((root/'assessment.json').read_text()))
        self.assertEqual(board_review(ROOT/'board-budget')['additionalScopeSignals'],633)
    def test_missing_refusal_or_restoration_reject(self):
        for old,new in (('REFUSED missing-owner\n',''),('IMAGE restored1','IMAGE before1'),('CONTINUE -6 -6','CONTINUE -6 10')):
            with self.subTest(old=old),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'enabled.stdout';s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(root)
    def test_board_omission_wrong_owner_and_net_reject(self):
        root=ROOT/'board-budget'
        lines=[l for n in ('metadata-before.txt','metadata-references-before.txt','handle-scopes.txt') for l in (root/n).read_text().splitlines()]
        lines += [l.replace('VSA_','VSH_',1) for l in (root/'scope-signals-before.txt').read_text().splitlines()]
        state=joined_parse(lines);graph=graph_parse((root/'handle-graph.txt').read_text().splitlines())
        for mutate in (lambda s:s['signals']['rows'].pop(),lambda s:s['signals']['rows'][0].update(scope=1),lambda s:s['signals']['rows'][0].update(nodeId=999999)):
            bad=copy.deepcopy(state);mutate(bad)
            with self.assertRaises(ValueError):bindings(bad,graph)
    def test_board_changed_image_and_nonfinite_cost_reject(self):
        for filename,old,new in (('scope-signals-after.txt','VSA_BEGIN 1 0','VSA_BEGIN 1 1'),('scope-signals-budget.txt','SCOPE_SCAN scope-signals 64 ','SCOPE_SCAN scope-signals 64 nan ')):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'evidence';shutil.copytree(ROOT/'board-budget',root);p=root/filename;s=p.read_text();self.assertIn(old,s);
                if filename.endswith('budget.txt'):
                    words=s.split();words[3]='nan';p.write_text(' '.join(words)+'\n')
                else:p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):board_review(root)

if __name__=='__main__':unittest.main()
