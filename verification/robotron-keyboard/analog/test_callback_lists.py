import json,shutil,tempfile,unittest
from pathlib import Path
from callback_list_probe import HERE,parse,review
from value_callback_probe import review as legacy_review
from assignment_raw import review as assignment_review
from retained_evidence import check
ROOT=HERE/'reports/callback-lists'

class CallbackLists(unittest.TestCase):
    def test_native_lists_and_regressions(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
        for name,reviewer in [('legacy',legacy_review),('assignments',assignment_review)]:
            root=ROOT/name;self.assertEqual(reviewer(root),json.loads((root/'assessment.json').read_text()))
    def tamper(self,change):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/'enabled.stdout';old=p.read_text();new=change(old);self.assertNotEqual(old,new);p.write_text(new)
            with self.assertRaises(ValueError):review(root)
    def test_missing_admission_guard_rejected(self):
        self.tamper(lambda s:s.replace('LST_UNADMITTED_REFUSED\n','',1))
    def test_missing_active_traversal_guard_rejected(self):
        self.tamper(lambda s:s.replace('LST_ACTIVE_REFUSED\n','',1))
    def test_changed_cancellation_state_rejected(self):
        def change(s):
            lines=s.splitlines();start=lines.index('LST_STAGE 2');i=next(i for i in range(start,len(lines)) if lines[i].startswith('VCL_CALLBACK 2 '));a=lines[i].split();self.assertEqual(int(a[5],16),0);a[5]='0x1234';lines[i]=' '.join(a);return '\n'.join(lines)+'\n'
        self.tamper(change)
    def test_callback_lifetime_rebinding_rejected(self):
        self.tamper(lambda s:s.replace('VCL_CALLBACK 2 ','VCL_CALLBACK 999 ',1))
    def test_unknown_owner_refused_by_parser(self):
        lines=['VCL_BEGIN 1 0','VCL_OWNER 1 0x10 9ExtraWire 0x0 0x0 0 0','VCL_END 1 0 0']
        with self.assertRaises(ValueError):parse(lines)
    def test_nonempty_tail_cannot_be_hidden(self):
        lines=['VCL_BEGIN 1 0','VCL_OWNER 1 0x10 13vvp_wire_vec4 0x20 0x0 0 0','VCL_END 1 0 0']
        with self.assertRaisesRegex(ValueError,'tail'):parse(lines)
    def test_array_word_link_and_fields_parse(self):
        lines=['VCL_BEGIN 1 0','VCL_OWNER 1 0x10 13vvp_wire_vec4 0x0 0x20 0 1','VCL_WORD 1 0x20 0x0 0x30 4','VCL_END 1 0 1']
        row=parse(lines)['owners'][0]['words'][0];self.assertEqual((row['array'],row['word']),(48,4))
        lines[2]=lines[2].replace('0x20 0x0','0x20 0x20')
        with self.assertRaisesRegex(ValueError,'tail'):parse(lines)
    def test_original_callback_order_required(self):
        self.tamper(lambda s:s.replace('CALLBACK 2000 C','CALLBACK 2000 A',1))

if __name__=='__main__':unittest.main()
