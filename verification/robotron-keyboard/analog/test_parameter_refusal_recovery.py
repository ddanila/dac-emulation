import json,shutil,tempfile,unittest
from pathlib import Path
import parameter_refusal_recovery as subject
class Recovery(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)/'report';shutil.copytree(subject.HERE/'reports/parameter-refusal-recovery',self.root)
 def test_complete_replay_and_runtime(self):
  self.assertEqual(subject.review(self.root),json.loads((self.root/'assessment.json').read_text()))
  self.assertEqual(json.loads((self.root/'build.json').read_text()),json.loads((subject.HERE/'reports/parameter-lifecycle/build.json').read_text()))
 def test_missing_stale_entry_refusal(self):
  p=self.root/'binary-enabled.stdout';p.write_text(p.read_text().replace('STALE_REFUSED 1 0 3\n',''))
  with self.assertRaisesRegex(ValueError,'Missing recovery'):subject.review(self.root)
 def test_lost_recovered_null(self):
  p=self.root/'string-enabled.stdout';s=p.read_text();self.assertIn('VPM_BYTES 47005200',s);p.write_text(s.replace('VPM_BYTES 47005200','VPM_BYTES 47205200',1))
  with self.assertRaisesRegex(ValueError,'embedded-null'):subject.review(self.root)
 def test_recovery_changes_original_name(self):
  p=self.root/'real-enabled.stdout';s=p.read_text();a=s.index('IMAGE recovered1');b=s.index('VPM_NAME 5000',a);p.write_text(s[:b]+s[b:].replace('VPM_NAME 5000','VPM_NAME 5100',1))
  with self.assertRaisesRegex(ValueError,'recovery/restoration'):subject.review(self.root)
if __name__=='__main__':unittest.main()
