import json,shutil,tempfile,unittest
from pathlib import Path
import memory_growth as subject
from array_family_probe import review as families
from memory_metadata import review as metadata
class Growth(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)/'report';shutil.copytree(subject.HERE/'reports/memory-growth',self.root)
 def test_replay_and_runtime_regressions(self):
  for directory,review in [(self.root,subject.review),(self.root/'array-families',families),(self.root/'native-layout',metadata)]:
   self.assertEqual(json.loads(json.dumps(review(directory))),json.loads((directory/'assessment.json').read_text()))
   self.assertEqual(json.loads((self.root/'build.json').read_text()),json.loads((directory/'build.json').read_text()))
 def test_lost_high_payload_bit(self):
  p=self.root/'enabled.stdout';s=p.read_text();needle='VAR_WORD 0 '+'1'+'3'*79
  self.assertIn(needle,s);p.write_text(s.replace(needle,needle[:-1]+'0',1))
  with self.assertRaisesRegex(ValueError,'array value'):subject.review(self.root)
 def test_missing_lazy_cache(self):
  p=self.root/'enabled.stdout';s=p.read_text();a=s.index('IMAGE cached1_0\n');b=s.index('IMAGE_END',a)
  before=s[s.index('IMAGE after1_0\n')+len('IMAGE after1_0\n'):s.index('IMAGE_END',s.index('IMAGE after1_0\n'))]
  p.write_text(s[:a]+'IMAGE cached1_0\n'+before+s[b:])
  with self.assertRaisesRegex(ValueError,'lazy word cache'):subject.review(self.root)
 def test_missing_allocation(self):
  p=self.root/'disabled.stdout';p.write_text(p.read_text().replace('ADDED 2 1\n',''))
  with self.assertRaisesRegex(ValueError,'Missing growth'):subject.review(self.root)
if __name__=='__main__':unittest.main()
