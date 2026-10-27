import copy,json,shutil,tempfile,unittest
from pathlib import Path
import resolver_strength_delta as probe
from resolver_delta_probe import block,reconstruct,separate
ROOT=probe.HERE/'reports/resolver-strength-delta'

class ResolverStrengthDelta(unittest.TestCase):
    def test_retained_native_replay(self):
        self.assertEqual(probe.review_all(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def frames(self,width):
        lines=probe.dense.output_text(ROOT/('width-'+str(width)),'corrupt').splitlines()
        frames=[];i=0
        while i<len(lines):
            if lines[i].startswith('VRX_BEGIN '):frame,i=block(lines,i);frames.append(frame)
            else:i+=1
        return lines,frames
    def test_reconstruction_for_every_width(self):
        for width in probe.WIDTHS:
            lines,frames=self.frames(width)
            self.assertGreater(separate(lines)[1],0)
            self.assertTrue(any(f['rows'] for f in frames[1:]))
    def test_reference_reset_rejected(self):
        lines,_=self.frames(1);i=next(i for i,l in enumerate(lines) if l.startswith('VRX_BEGIN R'));_,end=block(lines,i)
        with self.assertRaisesRegex(ValueError,'reset'):separate(lines[:end]+lines[i:end]+lines[end:])
    def test_splice_outside_reference_rejected(self):
        for width in probe.WIDTHS:
            _,frames=self.frames(width);reference=frames[0]['rows'];frame=copy.deepcopy(next(f for f in frames[1:] if f['rows']));key=next(iter(frame['rows']));frame['rows'][key]=(len(reference[key])+1,0,'')
            with self.subTest(width=width),self.assertRaisesRegex(ValueError,'exceeds'):reconstruct(reference,frame)
    def test_original_raw_hiz_output_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'width';shutil.copytree(ROOT/'width-9',root)
            text=probe.dense.output_text(root,'baseline');old='RES_VALUE 10 0 '+'88'*9;self.assertIn(old,text)
            (root/'baseline.stdout').write_text(text.replace(old,'RES_VALUE 10 0 '+'00'*9,1))
            with self.assertRaises(ValueError):probe.review(root)

    def test_partial_first_initialization_remains_exact(self):
        for width in probe.WIDTHS:
            lines,_=self.frames(width);dense_lines=separate(lines)[0]
            self.assertIn('RES_VALUE 1 0 '+'00'*(width-1)+'66',dense_lines)
            self.assertIn('RES_VALUE 10 0 '+'88'*width,dense_lines)
            self.assertIn('RES_VALUE 11 0 '+'00'*width,dense_lines)

if __name__=='__main__':unittest.main()
