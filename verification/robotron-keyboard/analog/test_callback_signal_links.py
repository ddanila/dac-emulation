import json,shutil,tempfile,unittest
from pathlib import Path
from callback_signal_links import HERE,review
from retained_evidence import check
ROOT=HERE/'reports/callback-signal-links'


class CallbackSignalLinks(unittest.TestCase):
    def test_native_links_refusals_and_cancellation(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_signal_family_regression_on_new_runtime(self):
        from signal_handle_families import review as replay
        root=ROOT/'family-regression';self.assertEqual(replay(root),json.loads((root/'assessment.json').read_text()))
    def tamper(self,change,mode='enabled'):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/(mode+'.stdout');s=p.read_text();changed=change(s);self.assertNotEqual(s,changed);p.write_text(changed)
            with self.assertRaises(ValueError):review(root)
    def test_foreign_filter_refusal_required(self):self.tamper(lambda s:s.replace('REFUSED foreign-filter\n',''))
    def test_active_traversal_refusal_required(self):self.tamper(lambda s:s.replace('REFUSED active-traversal\n','',1))
    def test_original_native_continuation_required(self):self.tamper(lambda s:s.replace('CALLBACK a 7','CALLBACK a 5'),'baseline')
    def test_callback_owner_lifetime_must_match(self):
        def change(s):
            lines=s.splitlines();i=next(i for i,l in enumerate(lines) if l.startswith('VSL_LINK '));a=lines[i].split();a[5]='99999';lines[i]=' '.join(a);return '\n'.join(lines)+'\n'
        self.tamper(change)
    def test_filter_address_must_match_native_node(self):
        def change(s):
            lines=s.splitlines();i=next(i for i,l in enumerate(lines) if l.startswith('VSL_LINK '));a=lines[i].split();a[7]='0x1';lines[i]=' '.join(a);return '\n'.join(lines)+'\n'
        self.tamper(change)
    def test_native_deletion_required(self):self.tamper(lambda s:s.replace('STATE deleted','STATE missing'))
    def test_unadmitted_signal_refusal_required(self):self.tamper(lambda s:s.replace('REFUSED handles-unadmitted\n',''))


if __name__=='__main__':unittest.main()
