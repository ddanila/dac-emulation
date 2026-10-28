import json,shutil,tempfile,unittest
from pathlib import Path
import memory_lifecycle as subject
from memory_growth import review as growth
from parameter_growth import review as parameters
from array_family_probe import review as families
from memory_metadata import review as metadata
class Lifecycle(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)/'report';shutil.copytree(subject.HERE/'reports/memory-lifecycle',self.root)
 def test_replay_and_same_runtime_regressions(self):
  for name,review in [('',subject.review),('memory-growth',growth),('parameter-growth',parameters),('array-families',families),('native-layout',metadata)]:
   r=self.root/name
   self.assertEqual(json.loads(json.dumps(review(r))),json.loads((r/'assessment.json').read_text()))
   self.assertEqual(json.loads((self.root/'build.json').read_text()),json.loads((r/'build.json').read_text()))
 def test_missing_stale_refusal(self):
  p=self.root/'enabled.stdout';p.write_text(p.read_text().replace('REFUSED 1 0 5\n',''))
  with self.assertRaisesRegex(ValueError,'Missing destruction'):subject.review(self.root)
 def test_reused_object_identity(self):
  p=self.root/'enabled.stdout';s=p.read_text()
  for prefix in ('VMM_MEMORY','VSM_OBJECT','VSMR_OBJECT'):s=s.replace(prefix+' 5 ',prefix+' 2 ')
  p.write_text(s)
  with self.assertRaisesRegex(ValueError,'fresh identities'):subject.review(self.root)
 def test_missing_scope_registration(self):
  p=self.root/'enabled.stdout';s=p.read_text();a=s.index('VSMR_OBJECT 2 ');b=s.index('\n',a);s=s[:a]+s[b+1:];s=s.replace('VSMR_END 2 2','VSMR_END 2 1',1);p.write_text(s)
  with self.assertRaisesRegex(ValueError,'registration'):subject.review(self.root)
 def test_changed_restored_state(self):
  p=self.root/'enabled.stdout';s=p.read_text();a=s.index('IMAGE detached1_0');b=s.index('VMM_NAME ',a)+len('VMM_NAME ');s=s[:b]+'00'+s[b+2:];p.write_text(s)
  with self.assertRaisesRegex(ValueError,'stale state'):subject.review(self.root)
if __name__=='__main__':unittest.main()
