import json
import shutil
import tempfile
import unittest
from pathlib import Path
from callback_nested import HERE, review
from retained_evidence import check

ROOT = HERE / 'reports/callback-nested'


class CallbackNested(unittest.TestCase):
    def test_retained_native_nested_dispatch(self):
        check(ROOT)
        self.assertEqual(review(ROOT), json.loads((ROOT / 'assessment.json').read_text()))

    def tamper(self, mode, change):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'report'; shutil.copytree(ROOT, root)
            p=root/(mode+'.stdout');old=p.read_text();new=change(old)
            self.assertNotEqual(old,new);p.write_text(new)
            with self.assertRaises(ValueError):review(root)

    def test_inner_return_does_not_end_outer_guard(self):
        self.tamper('enabled',lambda s:s.replace('NEST_REFUSED exit 1\n','',1))

    def test_deepest_callback_is_guarded(self):
        self.tamper('enabled',lambda s:s.replace('NEST_REFUSED enter 3\n','',1))

    def test_shared_result_overwrite_is_preserved(self):
        self.tamper('baseline',lambda s:s.replace('EXIT 2000 B 2 3 0','EXIT 2000 B 2 2 0',1))

    def test_signal_value_is_not_confused_with_shared_result(self):
        self.tamper('disabled',lambda s:s.replace('VALUES 2000  3  2','VALUES 2000  3  3',1))

    def test_native_nesting_depth_matters(self):
        self.tamper('enabled',lambda s:s.replace('ENTER 2000 A 3 3 0','ENTER 2000 A 2 3 0',1))

    def test_quiescent_callback_identity_survives(self):
        def change(s):
            head,tail=s.split('NEST_STAGE 1\n',1)
            return head+'NEST_STAGE 1\n'+tail.replace('VCL_CALLBACK 1 ','VCL_CALLBACK 99 ',1)
        self.tamper('enabled',change)


if __name__=='__main__':unittest.main()
