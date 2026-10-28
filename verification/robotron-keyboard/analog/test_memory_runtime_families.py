import json,shutil,tempfile,unittest
from pathlib import Path
from memory_runtime_families import review,HERE
ROOT=HERE/'reports/memory-runtime-array-families'

class MemoryRuntimeFamilies(unittest.TestCase):
    def test_retained_same_runtime_controls(self):
        result=review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(result['unsupportedProfilesRefused'],['alias','net','real','string'])
        self.assertTrue(result['disabledContinuationExactlyEqual'])

    def test_wrong_runtime_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root)
            p=root/'build.json';d=json.loads(p.read_text());d['outputs']['vvp/libvvp.so']='changed';p.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError,'Different memory'):review(root)

    def test_partial_inventory_refusal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root)
            p=root/'real-compact.stdout';p.write_text(p.read_text()+'VAC_BEGIN 1 1000\n')
            with self.assertRaisesRegex(ValueError,'partially emitted'):review(root)

if __name__=='__main__':unittest.main()
