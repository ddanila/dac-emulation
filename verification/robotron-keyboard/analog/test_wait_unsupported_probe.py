import shutil,tempfile,unittest
from pathlib import Path
from wait_unsupported_probe import review
SOURCE=Path(__file__).resolve().parent/'reports/wait-unsupported'

class UnsupportedWait(unittest.TestCase):
    def test_native_refusal_control(self):
        self.assertTrue(review(SOURCE)['unsupportedStateRejectedBeforeContinuation'])

    def test_false_success_changed_disabled_and_partial_baseline_rejected(self):
        for mode,mutation in [('enabled',lambda s:s+'VWM_DONE 0\n'),('corrupt',lambda s:s+'CONTINUED 1000\n'),('disabled',lambda s:s.replace('5a','00')),('baseline',lambda s:s.replace('RESULT 7000 5a','RESULT 7000 00'))]:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d)/'evidence';shutil.copytree(SOURCE,root)
                p=root/(mode+'.stdout');p.write_text(mutation(p.read_text()))
                with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
