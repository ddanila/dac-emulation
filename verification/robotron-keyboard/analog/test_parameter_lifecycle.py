import json,shutil,tempfile,unittest
from pathlib import Path
import parameter_lifecycle as subject
from parameter_growth import review as growth
from parameter_class import review as classes
from memory_lifecycle import review as memory
from array_family_probe import review as arrays
class Lifecycle(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)/'report';shutil.copytree(subject.HERE/'reports/parameter-lifecycle',self.root)
 def test_replay_and_same_runtime_regressions(self):
  for name,review in [('',subject.review),('parameter-growth',growth),('parameter-classes',classes),('memory-lifecycle',memory),('array-families',arrays)]:
   r=self.root/name
   self.assertEqual(json.loads(json.dumps(review(r))),json.loads((r/'assessment.json').read_text()))
   self.assertEqual(json.loads((self.root/'build.json').read_text()),json.loads((r/'build.json').read_text()))
 def test_missing_refusal(self):
  p=self.root/'enabled.stdout';p.write_text(p.read_text().replace('REFUSED 1 0 3\n',''))
  with self.assertRaisesRegex(ValueError,'Missing destruction'):subject.review(self.root)
 def test_reused_identity(self):
  p=self.root/'enabled.stdout';s=p.read_text()
  for prefix in ('VPM_PARAM','VSM_OBJECT','VSMR_OBJECT'):s=s.replace(prefix+' 10 ',prefix+' 5 ')
  p.write_text(s)
  with self.assertRaisesRegex(ValueError,'fresh identities'):subject.review(self.root)
 def test_lost_embedded_null(self):
  p=self.root/'enabled.stdout';s=p.read_text();self.assertIn('VPM_BYTES 47005200',s);p.write_text(s.replace('VPM_BYTES 47005200','VPM_BYTES 47205200',1))
  with self.assertRaisesRegex(ValueError,'embedded-null'):subject.review(self.root)
if __name__=='__main__':unittest.main()
