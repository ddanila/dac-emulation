import json,shutil,tempfile,unittest
from pathlib import Path
from parameter_refusal_recovery import review
from parameter_lifecycle import review as lifecycle
from parameter_class import review as classes
from memory_metadata import review as layout
HERE=Path(__file__).resolve().parent
class RecoveryAPI(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)/'report';shutil.copytree(HERE/'reports/parameter-refusal-api',self.root)
 def test_replay_and_same_runtime_regressions(self):
  for name,check in [('',review),('parameter-lifecycle',lifecycle),('parameter-classes',classes),('native-layout',layout)]:
   r=self.root/name;self.assertEqual(json.loads(json.dumps(check(r))),json.loads((r/'assessment.json').read_text()));self.assertEqual(json.loads((r/'build.json').read_text()),json.loads((self.root/'build.json').read_text()))
 def test_missing_refusal(self):
  p=self.root/'binary-enabled.stdout';p.write_text(p.read_text().replace('STALE_REFUSED 1 0 3\n',''))
  with self.assertRaises(ValueError):review(self.root)
 def test_incomplete_supported_recovery(self):
  p=self.root/'real-disabled.stdout';p.write_text(p.read_text().replace('SUPPORTED 2 1\n',''))
  with self.assertRaises(ValueError):review(self.root)
if __name__=='__main__':unittest.main()
