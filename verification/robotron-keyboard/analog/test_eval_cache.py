import hashlib,json,re,subprocess,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
class EvalCacheTests(unittest.TestCase):
 def test_real_evaluator(self):
  fixture=HERE/'fixtures/ngspice-47';original=(fixture/'ifeval.c').read_text()
  self.assertEqual(hashlib.sha256(original.encode()).hexdigest(),json.loads((fixture/'ifeval-source.json').read_text())['sha256'])
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'src/spicelib/parser/ifeval.c';source.parent.mkdir(parents=True);source.write_text(original)
   subprocess.run(['patch','-d',str(root),'-p1','-i',str(HERE/'engine-patches/eval-cache.patch')],check=True,capture_output=True)
   evaluator=re.sub(r'^#include .*$', '',source.read_text(),flags=re.M)
   (root/'test.c').write_text((HERE/'fixtures/eval_cache_harness.c').read_text().replace('/* EVALUATOR */',evaluator))
   subprocess.run(['cc','-std=gnu11','-O3',str(root/'test.c'),'-lm','-o',str(root/'test')],check=True)
   for mode in ('off','exact'):subprocess.run([str(root/'test'),mode],check=True,capture_output=True)
if __name__=='__main__':unittest.main()
