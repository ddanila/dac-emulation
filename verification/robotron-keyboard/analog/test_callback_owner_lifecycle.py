import json,shutil,tempfile,unittest
from pathlib import Path
from callback_owner_lifecycle import HERE,review
from retained_evidence import check
ROOT=HERE/'reports/callback-owner-lifecycle'


class CallbackOwnerLifecycle(unittest.TestCase):
    def test_retained_native_owner_lifecycle(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))

    def tamper(self,name,change):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/(name+'.stdout');old=p.read_text();new=change(old);self.assertNotEqual(old,new);p.write_text(new)
            with self.assertRaises(ValueError):review(root)

    def test_reference_owner_removal_cannot_be_omitted(self):
        def change(s):
            lines=s.splitlines();i=next(i for i,l in enumerate(lines) if l.startswith('VLD_DROP '));del lines[i];return '\n'.join(lines)+'\n'
        self.tamper('early-enabled',change)

    def test_reincarnation_must_use_same_address(self):
        self.tamper('late-enabled',lambda s:'\n'.join('OWN_BIND 0 2 0x1' if l.startswith('OWN_BIND 0 2 ') else l for l in s.splitlines())+'\n')

    def test_generation_cannot_be_reused(self):
        self.tamper('early-enabled',lambda s:s.replace('OWN_BIND 0 2 ','OWN_BIND 0 1 ',1))

    def test_destroyed_owner_cannot_remain_active(self):
        self.tamper('late-enabled',lambda s:s.replace('OWN_DROP 0 1\n','',1))

    def test_native_constructor_unknown_value_preserved(self):
        self.tamper('early-baseline',lambda s:s.replace('OWN_VALUE 1 1 9 xxxxxxxxx','OWN_VALUE 1 1 9 000000000',1))

    def test_native_filter_write_preserved(self):
        self.tamper('late-disabled',lambda s:s.replace('OWN_VALUE 0 1 1 1','OWN_VALUE 0 1 1 0',1))

    def test_later_width_and_hiz_constructor_preserved(self):
        self.tamper('late-enabled',lambda s:s.replace('OWN_VALUE 0 2 80 ','OWN_VALUE 0 2 79 ',1))


if __name__=='__main__':unittest.main()
