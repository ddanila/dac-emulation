import json
import shutil
import tempfile
import unittest
from pathlib import Path
from callback_board_budget import HERE, review
from retained_evidence import check

ROOT=HERE/'reports/callback-board-budget'


class CallbackBoardBudget(unittest.TestCase):
    def test_retained_real_bridge_bindings(self):
        check(ROOT)
        self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))

    def tamper(self,name,change):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root)
            p=root/name;old=p.read_text();new=change(old);self.assertNotEqual(old,new);p.write_text(new)
            with self.assertRaises(ValueError):review(root)

    def test_user_port_referent_must_match(self):
        def change(s):
            lines=s.splitlines();a=lines[0].split();a[3]='0x1';lines[0]=' '.join(a);return '\n'.join(lines)+'\n'
        self.tamper('bindings.txt',change)

    def test_missing_callback_binding_rejected(self):
        self.tamper('bindings.txt',lambda s:'\n'.join(s.splitlines()[1:])+'\n')

    def test_prior_output_lifetime_must_match(self):
        self.tamper('outputs.txt',lambda s:s.replace('VW_LINK ','VW_LINK 999 ',1))

    def test_initial_admission_guard_required(self):
        self.tamper('budget.txt',lambda s:s.replace('CB_UNADMITTED_REFUSED\n',''))

    def test_every_scan_must_leave_lists_unchanged(self):
        self.tamper('callbacks-after.txt',lambda s:s.replace('VCL_CALLBACK 1 ','VCL_CALLBACK 999 ',1))

    def test_compiled_interface_binding_required(self):
        self.tamper('io.vvp',lambda s:s.replace('/OUTPUT 1 ', '/OUTPUT 2 ',1))

    def test_nonfinite_measurement_rejected(self):
        def change(s):
            lines=s.splitlines();a=lines[0].split();a[2]='nan';lines[0]=' '.join(a);return '\n'.join(lines)+'\n'
        self.tamper('budget.txt',change)


if __name__=='__main__':unittest.main()
