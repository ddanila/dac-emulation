import ast,json,tempfile,unittest
from pathlib import Path
from wire_board_budget_review import budgets
from retained_evidence import check
HERE=Path(__file__).resolve().parent
MODES=('off','observe','wire4-init-corrupt','wire4-driven-corrupt','wire4-propagate-corrupt','wire8-init-corrupt','wire8-driven-corrupt','wire8-propagate-corrupt')

class WireBudgetTests(unittest.TestCase):
    def test_only_capture_limit_changes(self):
        original=(HERE/'wire_board_capture.py').read_text();candidate=(HERE/'wire_board_budget_capture.py').read_text()
        self.assertEqual(candidate.count('logical_limit=12*1024**3'),1)
        self.assertEqual(ast.dump(ast.parse(candidate.replace('logical_limit=12*1024**3','logical_limit=4*1024**3'))),ast.dump(ast.parse(original)))
    def test_retained_failed_receipt(self):
        root=HERE/'reports/wire-budget-failure';check(root);a=json.loads((root/'assessment.json').read_text())
        self.assertFalse(a['completed']);self.assertEqual(a['logicalBytes'],4*1024**3)
        self.assertLess(a['constantBytesPerBoundaryProjection'],a['proposedLogicalLimitBytes'])
        self.assertEqual(a['completeStableBoundaries'],24226)
    def test_limits_completion_and_actual_compressed_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            r=dict(completed=True,captureTimeoutSeconds=3000,log=dict(bytes=100,compressedBytes=4,logicalLimitBytes=12*1024**3,compressedLimitBytes=256*1024**2))
            for mode in MODES:
                p=root/mode;p.mkdir();(p/'ngspice.log.xz').write_bytes(b'test');(p/'run.json').write_text(json.dumps(r))
            self.assertEqual(len(budgets(root)),8)
            for key,value in (('bytes',12*1024**3+1),('compressedBytes',3),('logicalLimitBytes',13*1024**3),('compressedLimitBytes',512*1024**2)):
                bad=json.loads(json.dumps(r));bad['log'][key]=value;(root/'observe/run.json').write_text(json.dumps(bad))
                with self.assertRaises(ValueError):budgets(root)
            bad=dict(r,completed=False);(root/'observe/run.json').write_text(json.dumps(bad))
            with self.assertRaises(ValueError):budgets(root)

if __name__=='__main__':unittest.main()
