import copy,json,shutil,tempfile,unittest
from pathlib import Path
from scope_metadata_compact import HERE,Decoder,review
from retained_evidence import check
ROOT=HERE/'reports/scope-metadata-compact'

class ScopeMetadataCompactTests(unittest.TestCase):
    def first(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines();a=next(i for i,l in enumerate(lines) if l.startswith('VSMD_BEGIN '));b=lines.index('VSMD_END',a)
        return lines[a:b+1]
    def test_retained_dense_reconstruction(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_missing_reordered_or_truncated_reference_refused(self):
        first=self.first();a=first[0].split();a[3]='2';a[4]='0';repeat=[' '.join(a),'VSMD_END']
        with self.assertRaises(ValueError):Decoder().decode(repeat)
        d=Decoder();dense=d.decode(first)
        self.assertEqual(d.decode(repeat),dense)
        with self.assertRaises(ValueError):d.decode(repeat)
        for size in range(len(first)):
            with self.subTest(size=size),self.assertRaises(ValueError):Decoder().decode(first[:size])
    def test_failure_preserves_decoder_state(self):
        first=self.first();d=Decoder();expected=d.decode(first);saved=copy.deepcopy(d.__dict__)
        a=first[0].split();a[3]='2';a[4]='0';a[5]=str(int(a[5])+1)
        with self.assertRaises(ValueError):d.decode([' '.join(a),'VSMD_END'])
        self.assertEqual(d.__dict__,saved)
        a[5]=first[0].split()[5]
        self.assertEqual(d.decode([' '.join(a),'VSMD_END']),expected)
    def test_payload_change_cannot_reuse_cached_image(self):
        first=self.first();d=Decoder();d.decode(first);a=first[0].split();a[3]='2';a[4]='0'
        with self.assertRaises(ValueError):d.decode([' '.join(a),*first[1:]])
    def test_native_missing_refusal_or_corrupt_body_refused(self):
        for old,new in (('ENCODING_REFUSED\n',''),('VSM_NAME 5 7465737400','VSM_NAME 5 74657374ff'),('CONTINUE 5 2','CONTINUE 3 2')):
            with self.subTest(old=old),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)/'evidence';shutil.copytree(ROOT,out);p=out/'enabled.stdout';s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(out)

if __name__=='__main__':unittest.main()
