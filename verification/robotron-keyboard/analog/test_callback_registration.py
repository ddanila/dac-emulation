import json
import shutil
import tempfile
import unittest
from pathlib import Path
from callback_registration import HERE, review
from retained_evidence import check

ROOT = HERE / 'reports/callback-registration'


class CallbackRegistration(unittest.TestCase):
    def test_retained_native_registration(self):
        check(ROOT)
        self.assertEqual(review(ROOT), json.loads((ROOT / 'assessment.json').read_text()))

    def tamper(self, mode, change):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'report'; shutil.copytree(ROOT, root)
            p = root / (mode + '.stdout'); old = p.read_text(); new = change(old)
            self.assertNotEqual(old, new); p.write_text(new)
            with self.assertRaises(ValueError):
                review(root)

    def test_new_callback_cannot_run_in_current_traversal(self):
        self.tamper('baseline', lambda s: s.replace('CALLBACK 2000 A 1 0', 'CALLBACK 2000 A 1 0\nCALLBACK 2000 B 1 0', 1))

    def test_return_from_dispatch_does_not_admit_caller(self):
        self.tamper('enabled', lambda s: s.replace('REG_UNADMITTED_REFUSED\n', '', 1))

    def test_active_guard_survives_registration(self):
        self.tamper('enabled', lambda s: s.replace('REG_ACTIVE_AFTER_ADD_REFUSED\n', '', 1))

    def test_retired_lifetime_cannot_be_reused(self):
        def change(s):
            lines=s.splitlines();a=next(line.split()[2] for line in lines if line.startswith('REG_ADMIT A '))
            i=next(i for i,line in enumerate(lines) if line.startswith('REG_ADMIT D '));lines[i]='REG_ADMIT D '+a
            return '\n'.join(lines)+'\n'
        self.tamper('enabled', change)

    def test_cancelled_nodes_remain_visible_until_deletion(self):
        def change(s):
            head,tail=s.split('REG_STAGE 6\n',1);lines=tail.splitlines()
            i=next(i for i,line in enumerate(lines) if line.startswith('VCL_CALLBACK '));fields=lines[i].split();fields[5]='0x1234';lines[i]=' '.join(fields)
            return head+'REG_STAGE 6\n'+'\n'.join(lines)+'\n'
        self.tamper('enabled', change)

    def test_callback_order_must_match_native_execution(self):
        self.tamper('disabled', lambda s: s.replace('CALLBACK 4000 B 2 0\nCALLBACK 4000 A 2 0', 'CALLBACK 4000 A 2 0\nCALLBACK 4000 B 2 0', 1))


if __name__ == '__main__':
    unittest.main()
