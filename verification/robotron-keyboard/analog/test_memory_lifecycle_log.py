import json,shutil,tempfile,unittest
from pathlib import Path
from memory_lifecycle_log import review
ROOT=Path(__file__).resolve().parent/'reports/memory-lifecycle-log'
class LifecycleLog(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)/'report';shutil.copytree(ROOT,self.root)
 def test_replay(self):
  self.assertEqual(review(self.root),json.loads((self.root/'assessment.json').read_text()))
 def test_stale_reuse_in_each_stream(self):
  p=self.root/'compact.txt';original=p.read_text()
  for tag in ('VMMD','VSMD','VSMRD'):
   with self.subTest(stream=tag):
    lines=original.splitlines();starts=[i for i,line in enumerate(lines) if line.startswith(tag+'_BEGIN ')]
    # Second frame creates an object; reusing the prior body must not hide it.
    a=starts[1];b=lines.index(tag+'_END',a);fields=lines[a].split();fields[4]='0';fields[5]=lines[starts[0]].split()[5]
    p.write_text('\n'.join(lines[:a]+[' '.join(fields)]+lines[b:])+'\n')
    with self.assertRaises(ValueError):review(self.root)
 def test_missing_reference_stream(self):
  p=self.root/'compact.txt';lines=p.read_text().splitlines();a=next(i for i,line in enumerate(lines) if line.startswith('VSMRD_BEGIN '));b=lines.index('VSMRD_END',a);p.write_text('\n'.join(lines[:a]+lines[b+1:])+'\n')
  with self.assertRaises(ValueError):review(self.root)
 def test_changed_logger(self):
  p=self.root/'logger.h';p.write_text(p.read_text()+'\n')
  with self.assertRaisesRegex(ValueError,'Logger differs'):review(self.root)
if __name__=='__main__':unittest.main()
