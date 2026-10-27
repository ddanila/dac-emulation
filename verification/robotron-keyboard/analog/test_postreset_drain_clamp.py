import json
import shutil
import tempfile
import unittest
from pathlib import Path
import postreset_drain_clamp as clamp
ROOT=clamp.HERE/'reports/postreset-drain-clamp'

class ClampEvidence(unittest.TestCase):
    def test_retained_source_and_callbacks(self):
        result=clamp.review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(len(result['witnesses']),8)
        self.assertFalse(result['convergenceEstablished'])
        self.assertLess(result['maximumAbsoluteCrossingResidualSeconds'],2.4e-15)

    def test_source_change_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root';shutil.copytree(ROOT,root)
            with (root/'vpi.c').open('a') as f:f.write('\n/* changed */\n')
            with self.assertRaisesRegex(ValueError,'source binding'):clamp.review(root)

    def test_following_target_must_match_clamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            local=Path(tmp)/'local';shutil.copytree(clamp.LOCAL,local)
            path=local/'events/fine.json';data=json.loads(path.read_text())
            data['events'][283]['target']='0.0010780017205'
            path.write_text(json.dumps(data))
            manifest=local/'manifest.json';m=json.loads(manifest.read_text())
            m['files']['events/fine.json']=clamp.sha(path);manifest.write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError,'Following callbacks'):clamp.review(ROOT,local=local)

if __name__=='__main__':unittest.main()
