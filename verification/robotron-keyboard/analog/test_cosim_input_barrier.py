"""Replay output-triggered truncation/LTE rejection through real d_cosim code."""
import hashlib,subprocess,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
class InputBarrierTests(unittest.TestCase):
 def test_upstream_failure_and_candidate(self):
  original=(HERE/'fixtures/ngspice-47/d_cosim.mod').read_text()
  self.assertEqual(hashlib.sha256(original.encode()).hexdigest(),'aa31bc8cf686914b3f667c9790aae4b79115a6f3b0e786732358a63df9340207')
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp);source=out/'src/xspice/icm/digital/d_cosim/cfunc.mod';source.parent.mkdir(parents=True);source.write_text(original)
   for patched in (False,True):
    if patched:subprocess.run(['patch','-d',str(out),'-p1','-i',str(HERE/'engine-patches/cosim-input-barrier.patch')],check=True,capture_output=True)
    text=source.read_text();scheduler=text[text.index('static int advance('):text.index('/* Check whether an input value has changed.')]
    # ARGS expansion in the harness has no trailing argument.
    scheduler=scheduler.replace(', XSPICE_ARG','').replace(', ARGS','')
    harness=(HERE/'fixtures/cosim_order_harness.c').read_text().replace('/* SCHEDULER */',scheduler)
    (out/'test.c').write_text(harness)
    subprocess.run(['cc','-std=c11','-O2',str(out/'test.c'),'-o',str(out/'test')],check=True)
    result=subprocess.run([str(out/'test'),str(int(patched))],capture_output=True,text=True,check=True)
    print(result.stdout.strip())
if __name__=='__main__':unittest.main()
