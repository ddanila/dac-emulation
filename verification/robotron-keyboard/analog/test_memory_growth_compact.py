import json,shutil,tempfile,unittest
from pathlib import Path
import memory_growth_compact as subject
class CompactGrowth(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)/'report';shutil.copytree(subject.HERE/'reports/memory-growth-compact',self.root)
 def test_replay(self):
  self.assertEqual(subject.review(self.root),json.loads((self.root/'assessment.json').read_text()))
 def test_changed_packed_value(self):
  p=self.root/'enabled.stdout';s=p.read_text();a=s.index('VAC_WORDS ')+len('VAC_WORDS ');p.write_text(s[:a]+('0' if s[a]!='0' else '1')+s[a+1:])
  with self.assertRaises(ValueError):subject.review(self.root)
 def test_missing_cache_ownership(self):
  p=self.root/'enabled.stdout';s=p.read_text();a=s.index('VAC_CACHE_RUN ');b=s.index('\n',a);p.write_text(s[:a]+s[b+1:])
  with self.assertRaises(ValueError):subject.review(self.root)
if __name__=='__main__':unittest.main()
