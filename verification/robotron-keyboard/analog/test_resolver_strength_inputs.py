import json,shutil,tempfile,unittest
from pathlib import Path
import resolver_strength_inputs as probe
ROOT=probe.HERE/'reports/resolver-strength-inputs'

class ResolverStrengthInputs(unittest.TestCase):
    def test_retained_native_replay(self):
        self.assertEqual(probe.review_all(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_independent_symmetric_oracle_against_original_scalar_table(self):
        values={0,0x88}|{s*17+mask for s in range(1,8) for mask in (0,0x80,0x88)}
        pairs={}
        for line in (probe.HERE/'reports/strength-encoding/baseline.stdout').read_text().splitlines():
            if line.startswith('STRENGTH_RESOLVE '):
                a,b,value=map(int,line.split()[1:]);pairs[a,b]=value
        for a in values:
            for b in values:self.assertEqual(probe.scalar(a,b),pairs[a,b],(a,b))
    def test_no_pull_preserves_raw_hiz_and_pull_beats_weak(self):
        self.assertEqual(probe.tree([b'\x88'],0),[b'\x88'])
        self.assertEqual(probe.tree([b'\x33'],0xdd),[b'\xdd'])
        self.assertEqual(probe.tree([b'\xee'],0x55),[b'\xee'])
        self.assertEqual(probe.tree([b'\xdd'],0x55),[b'\xd5'])
    def test_partial_first_and_raw_input_changes_are_exercised(self):
        for width in probe.WIDTHS:
            lines=probe.output_text(ROOT/('width-'+str(width)),'baseline').splitlines()
            self.assertIn('RES_VALUE 1 0 '+'00'*(width-1)+'66',lines)
            for phase,raw in ((10,'88'),(11,'00'),(12,'88')):self.assertIn(f'RES_VALUE {phase} 0 '+raw*width,lines)
            self.assertFalse(any(l.startswith('RES_VALUE 13 0 ') for l in lines))
    def reject_output(self,mode,old,new):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'width';shutil.copytree(ROOT/'width-9',root)
            text=probe.output_text(root,mode);self.assertIn(old,text)
            (root/(mode+'.stdout')).write_text(text.replace(old,new,1))
            with self.assertRaises(ValueError):probe.review(root)
    def test_raw_normalization_rejected(self):
        self.reject_output('baseline','RES_VALUE 10 0 '+'88'*9,'RES_VALUE 10 0 '+'00'*9)
    def test_cache_loss_rejected(self):
        self.reject_output('corrupt','VRS_SLOT 0 0 -','VRS_SLOT 0 1 00')
    def test_restoration_required(self):
        self.reject_output('corrupt','RSM_RESTORED','RSM_NOT_RESTORED')

if __name__=='__main__':unittest.main()
