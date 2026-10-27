import json,lzma,shutil,tempfile,unittest
from pathlib import Path
import resolver_widths as probe
ROOT=probe.HERE/'reports/resolver-widths'

class ResolverWidths(unittest.TestCase):
    def test_retained_native_replay(self):
        self.assertEqual(probe.review_all(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_single_input_pull_changes_repeated_write_behavior(self):
        for width in probe.WIDTHS:
            lines=probe.output_text(ROOT/('width-'+str(width)),'baseline').splitlines()
            for core,byte in ((1,'55'),(2,'dd')):
                self.assertIn(f'RES_VALUE 4 {core} '+byte*width,lines)
                self.assertIn(f'RES_VALUE 5 {core} '+byte*width,lines)
            self.assertIn('RES_VALUE 4 0 '+'00'*width,lines)
            self.assertFalse(any(l.startswith('RES_VALUE 5 0 ') for l in lines))
    def test_independent_resolution_and_clipped_partial(self):
        self.assertEqual(probe.resolve([bytes([0x66,0]),bytes([0xee,0xee])]),bytes([0xe6,0xee]))
        for width in probe.WIDTHS:
            value=bytes([0]*(width-1)+[0xee])
            self.assertEqual(probe.tree([value],0x55),[bytes([0x55]*(width-1)+[0xee])])
    def reject_output(self,mode,old,new):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'width';shutil.copytree(ROOT/'width-9',root)
            text=probe.output_text(root,mode);self.assertIn(old,text)
            (root/(mode+'.stdout')).write_text(text.replace(old,new,1))
            with self.assertRaises(ValueError):probe.review(root)
    def test_original_output_tampering_rejected(self):
        self.reject_output('baseline','RES_VALUE 5 1 555555555555555555','RES_VALUE 5 1 000000000000000000')
    def test_leaf_cache_loss_rejected(self):
        self.reject_output('corrupt','VRS_SLOT 0 0 -','VRS_SLOT 0 1 00')
    def test_restoration_required(self):
        self.reject_output('corrupt','RSM_RESTORED','RSM_NOT_RESTORED')

if __name__=='__main__':unittest.main()
