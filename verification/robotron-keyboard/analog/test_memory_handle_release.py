import json,shutil,tempfile,unittest
from pathlib import Path
import memory_handle_release as subject
class Release(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)/'report';shutil.copytree(subject.HERE/'reports/memory-handle-release',self.root)
 def test_replay(self):
  self.assertEqual(subject.review(self.root),json.loads((self.root/'assessment.json').read_text()))
 def test_missing_release(self):
  p=self.root/'none-disabled.stdout';p.write_text(p.read_text().replace('RELEASE 1 test.mem 0 1 SAME\n',''))
  with self.assertRaises(ValueError):subject.review(self.root)
 def test_changed_native_image(self):
  p=self.root/'none-enabled.stdout';p.write_text(p.read_text().replace('IMAGE after1\n','IMAGE after1\nCORRUPT\n'))
  with self.assertRaises(ValueError):subject.review(self.root)
if __name__=='__main__':unittest.main()
