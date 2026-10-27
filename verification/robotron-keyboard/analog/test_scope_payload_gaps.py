import json,shutil,tempfile,unittest
from pathlib import Path
from scope_payload_gaps import HERE,review,parse
from scope_payload_contract import assess
from retained_evidence import check
ROOT=HERE/'reports/scope-payload-gaps'

class ScopePayloadGapTests(unittest.TestCase):
    def test_retained_gap_controls(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_missing_mutation_restoration_or_continuation_rejects(self):
        for old,new in (('PARAMETER 3 2','PARAMETER 3 3'),('IMAGE memory1','IMAGE parameter1'),('IMAGE restored2','IMAGE restored1'),('CONTINUE -6 -6 3 5','CONTINUE -6 10 3 5')):
            with self.subTest(old=old),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'enabled.stdout';s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(root)
    def test_truncated_witness_sections_reject(self):
        text=(ROOT/'enabled.stdout').read_text();a=text.index('VSM_BEGIN ');b=text.index('IMAGE_END',a);lines=text[a:b].splitlines()
        for i,line in enumerate(lines):
            if '_BEGIN ' in line or '_END ' in line:
                with self.subTest(i=i),self.assertRaises((ValueError,IndexError)):parse(lines[:i])
    def test_source_contract_replays_when_archive_available(self):
        archive=Path('/private/tmp/k7658-icarus-pinned.tar.gz')
        if not archive.is_file():self.skipTest('Pinned source archive unavailable')
        self.assertEqual(assess(archive),json.loads((ROOT/'source-contract.json').read_text()))

if __name__=='__main__':unittest.main()
