import json,shutil,tempfile,unittest
from pathlib import Path
from callback_delta_budget import HERE,review
from retained_evidence import check
ROOT=HERE/'reports/callback-delta-board-budget'


class CallbackDeltaBudget(unittest.TestCase):
    def test_retained_actual_bridge_compact_budget(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))

    def tamper(self,name,change):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/name;old=p.read_text();new=change(old);self.assertNotEqual(old,new);p.write_text(new)
            with self.assertRaises(ValueError):review(root)

    def test_missing_owner_reference_rejected(self):
        self.tamper('callback-reference.txt',lambda s:'\n'.join(l for l in s.splitlines() if not l.startswith('VLD_ROW 1 '))+'\n')

    def test_unchanged_frame_must_cover_owner_population(self):
        self.tamper('callback-delta-before.txt',lambda s:s.replace(' 1573 ', ' 1574 ',1))

    def test_changed_frame_cannot_claim_stable_budget(self):
        self.tamper('callback-delta-after.txt',lambda s:s.replace('VLD_BEGIN D 0 ', 'VLD_BEGIN D 1 ',1))

    def test_callback_binding_is_still_enforced(self):
        def change(s):
            lines=s.splitlines();a=lines[0].split();a[-1]='0x1';lines[0]=' '.join(a);return '\n'.join(lines)+'\n'
        self.tamper('bindings.txt',change)

    def test_extra_compact_records_rejected(self):
        self.tamper('callback-reference.txt',lambda s:s+'VLD_END 0 0\n')

    def test_compiled_time_precision_required_for_projection(self):
        self.tamper('io.vvp',lambda s:'\n'.join(l for l in s.splitlines() if not l.startswith(':vpi_time_precision '))+'\n')


if __name__=='__main__':unittest.main()
