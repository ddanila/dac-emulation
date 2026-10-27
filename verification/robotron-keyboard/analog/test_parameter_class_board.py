import json,shutil,tempfile,unittest
from pathlib import Path
from parameter_class_board import review
from retained_evidence import check
HERE=Path(__file__).resolve().parent
ROOT=HERE/'reports/parameter-class-board'

class ParameterClassBoardTests(unittest.TestCase):
    def test_retained_guarded_board(self):
        check(ROOT);r=review(ROOT);self.assertEqual(r,json.loads((ROOT/'assessment.json').read_text()))
        self.assertTrue(r['matchingNativeGuardControls']);self.assertEqual(r['initializedBoardControls']['bindings']['memories'],3)
        self.assertEqual(r['initializedBoardControls']['priorParameterControls']['bindings']['parameters'],56)
    def test_changed_guard_runtime_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'icarus-build.json';r=json.loads(p.read_text());r['outputs']['vvp/vpi_const.cc']='0'*64;p.write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'different native runtime'):review(root)
    def test_missing_subclass_fault_evidence_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'guard-controls/binary-enabled.stdout';s=p.read_text();self.assertIn('REFUSED 1 binary\n',s);p.write_text(s.replace('REFUSED 1 binary\n','',1))
            with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
