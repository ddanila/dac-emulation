import copy,json,shutil,tempfile,unittest
from pathlib import Path
from callback_delta import HERE,block,reconstruct,separate,review
from retained_evidence import check
ROOT=HERE/'reports/callback-delta'


class CallbackDelta(unittest.TestCase):
    def test_retained_native_dense_equivalence(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))

    def frames(self):
        lines=(ROOT/'lists/enabled.stdout').read_text().splitlines();frames=[]
        for i,line in enumerate(lines):
            if line.startswith('VLD_BEGIN '):frames.append(block(lines,i)[0])
        return frames

    def test_reference_cannot_reset(self):
        lines=(ROOT/'lists/enabled.stdout').read_text().splitlines();start=next(i for i,l in enumerate(lines) if l.startswith('VLD_BEGIN R '));_,end=block(lines,start)
        with self.assertRaisesRegex(ValueError,'reset'):separate(lines[:end]+lines[start:end]+lines[end:])

    def test_delta_requires_reference(self):
        lines=(ROOT/'lists/enabled.stdout').read_text().splitlines();start=next(i for i,l in enumerate(lines) if l.startswith('VLD_BEGIN R '));_,end=block(lines,start)
        with self.assertRaisesRegex(ValueError,'before reference'):separate(lines[:start]+lines[end:])

    def test_splice_cannot_escape_owner_reference(self):
        ref=self.frames()[0]['rows'];f=copy.deepcopy(self.frames()[1]);identity=next(iter(ref));f['rows'][identity]=(len(ref[identity])+1,0,'')
        with self.assertRaisesRegex(ValueError,'Splice'):reconstruct(ref,f)

    def test_owner_count_cannot_hide_omission(self):
        ref=self.frames()[0]['rows'];f=copy.deepcopy(self.frames()[1]);f['total']+=1
        with self.assertRaisesRegex(ValueError,'lifecycle'):reconstruct(ref,f)

    def test_removed_owner_must_exist_in_reference(self):
        ref=self.frames()[0]['rows'];f=copy.deepcopy(self.frames()[1]);f['removed']=[max(ref)+1]
        with self.assertRaisesRegex(ValueError,'outside reference'):reconstruct(ref,f)

    def test_owner_removal_roundtrip(self):
        ref=self.frames()[0]['rows'];identity=next(iter(ref));f=dict(mode='D',tick=1,total=len(ref)-1,rows={},removed=[identity])
        image=reconstruct(ref,f)
        self.assertFalse(any(l.startswith(f'VCL_OWNER {identity} ') for l in image))

    def test_changed_payload_cannot_claim_exact_dense_pair(self):
        lines=(ROOT/'registration/enabled.stdout').read_text().splitlines()
        i=next(i for i,l in enumerate(lines) if l.startswith('VCL_CALLBACK '));a=lines[i].split();a[7]='0x1';lines[i]=' '.join(a)
        with self.assertRaisesRegex(ValueError,'differs'):separate(lines)

    def test_compact_refusal_evidence_cannot_be_omitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/'nested/enabled.stdout';s=p.read_text();self.assertIn('VLD_REFUSED_EMPTY',s);p.write_text(s.replace('VLD_REFUSED_EMPTY\n','',1))
            with self.assertRaisesRegex(ValueError,'compact refusal'):review(root)


if __name__=='__main__':unittest.main()
