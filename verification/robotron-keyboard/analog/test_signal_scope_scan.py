import json,shutil,tempfile,unittest
from pathlib import Path
from signal_scope_scan import HERE,review,strip
from signal_scope_budget import review as budget_review
from typed_signal_fault_preflight import review as board_review
from retained_evidence import check
ROOT=HERE/'reports/signal-scope-scan'
BUDGET=HERE/'reports/signal-scope-budget'
BOARD=HERE/'reports/signal-scope-preflight'


class SignalScopeScan(unittest.TestCase):
    def test_native_reference_differential_and_continuation(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_actual_board_images_and_cost_replay(self):
        check(BUDGET);self.assertEqual(budget_review(BUDGET),json.loads((BUDGET/'assessment.json').read_text()))
    def test_all_combined_faults_on_optimized_runtime(self):
        check(BOARD);self.assertEqual(json.loads(json.dumps(board_review(BOARD))),json.loads((BOARD/'assessment.json').read_text()))
    def test_partial_failure_output_rejected(self):
        with self.assertRaisesRegex(ValueError,'Partial'):strip('SCOPE_EQ signals -1 1\n')
    def test_missing_automatic_scope_refusal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/'automatic/enabled.stdout';s=p.read_text();self.assertIn('SCOPE_EQ signals -1 0\n',s);p.write_text(s.replace('SCOPE_EQ signals -1 0\n',''))
            with self.assertRaisesRegex(ValueError,'automatic'):review(root)
    def test_byte_exact_board_reference_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(BUDGET,root);p=root/'handles-reference-after.txt';p.write_text(p.read_text().replace('VSH_BEGIN 1 0','VSH_BEGIN 1 1'))
            with self.assertRaisesRegex(ValueError,'images differ'):budget_review(root)
    def test_cost_requires_complete_reference_measurement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(BUDGET,root);p=root/'scope-scan-budget.txt';p.write_text('\n'.join(p.read_text().splitlines()[:2])+'\n')
            with self.assertRaisesRegex(ValueError,'Incomplete'):budget_review(root)


if __name__=='__main__':unittest.main()
