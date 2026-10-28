import json,shutil,tempfile,unittest
from pathlib import Path
from memory_growth_log import review
from retained_evidence import check
ROOT=Path(__file__).resolve().parent/'reports/memory-growth-log'

class MemoryGrowthLogTests(unittest.TestCase):
    def test_retained_growth_reconstructs_exactly(self):
        check(ROOT);r=review(ROOT);self.assertEqual(r,json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(r['memoryCounts'],[1,2,2,3,3,3,4,4,5,5]);self.assertEqual(r['fullImages'],5)
    def test_stale_reuse_cannot_hide_new_allocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'compact.txt';frames=p.read_text().split('VMMD_END\n');fields=frames[1].splitlines()[0].split();fields[4]='0';fields[5]=frames[0].splitlines()[0].split()[5];frames[1]=' '.join(fields)+'\n';p.write_text('VMMD_END\n'.join(frames))
            with self.assertRaises(ValueError):review(root)
    def test_changed_logger_or_native_identity_reject(self):
        for filename in ('logger.h','run.json'):
            with self.subTest(filename=filename),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/filename
                if filename=='logger.h':p.write_text(p.read_text()+'\n')
                else:
                    r=json.loads(p.read_text());r['nativeOutputSha256']='0'*64;p.write_text(json.dumps(r))
                with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
