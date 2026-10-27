import json,shutil,tempfile,unittest
from pathlib import Path
from assignment_raw_native import HERE,review,output
from retained_evidence import check
from assignment_raw import review as production_review
from assignment_probe import review as legacy_review
from island_raw_feedback import review as feedback_review
ROOT=HERE/'reports/assignment-raw-native'

class AssignmentRawNative(unittest.TestCase):
    def test_native_admission_and_nested_replay(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_production_runtime_without_adapter(self):
        for name,reviewer in [('production',production_review),('legacy',legacy_review),('feedback',feedback_review)]:
            root=ROOT/name;self.assertEqual(reviewer(root),json.loads((root/'assessment.json').read_text()))
    def test_previous_runtime_misses_override_execution(self):
        before=ROOT/'before-dispatch-fix'
        with self.assertRaisesRegex(ValueError,'Wrong native admission/refusal'):review(before)
        text=output(before,'family-early-3-observe')
        self.assertIn('AF_OBSERVE 2 0 inner 0\nVAR_BEGIN 1 0\nVAR_END 0',text)
        self.assertIn('AF_OBSERVE 2 0 inner -1\nAF_REFUSED_EMPTY',output(ROOT,'family-early-3-observe'))
    def tamper(self,name,change):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root)
            text=output(root,name);changed=change(text);self.assertNotEqual(text,changed)
            (root/(name+'.stdout')).write_text(changed)
            with self.assertRaises(ValueError):review(root)
    def test_refusal_must_precede_output(self):
        self.tamper('family-early-3-observe',lambda s:s.replace('AF_REFUSED_EMPTY','VAR_BEGIN 1 0\nAF_REFUSED_EMPTY',1))
    def test_late_subclass_must_refuse(self):
        self.tamper('family-late-1-observe',lambda s:s.replace('1 queued -1','1 queued 0',1))
    def test_private_override_output_required(self):
        self.tamper('family-early-2-observe',lambda s:s.replace('3db5b5','b5b5b5',1))
    def test_nested_parent_depth_required(self):
        self.tamper('nested-early-0-observe',lambda s:s.replace('executing 1 ','executing 2 ',1))
    def test_nested_parent_lifetime_required(self):
        def change(text):
            lines=text.splitlines();i=next(i for i,l in enumerate(lines) if 'VAR_EVENT -2 executing 1 ' in l);a=lines[i].split();a[4]='999999';lines[i]=' '.join(a);return '\n'.join(lines)+'\n'
        self.tamper('nested-early-0-observe',change)
    def test_child_removal_preserves_parent(self):
        self.tamper('nested-early-0-observe',lambda s:s.replace('0 outer-after 0','0 settled 0',1))
    def test_nested_unsupported_child_refuses(self):
        self.tamper('nested-early-2-observe',lambda s:s.replace('0 inner -1','0 inner 0',1))

if __name__=='__main__':unittest.main()
