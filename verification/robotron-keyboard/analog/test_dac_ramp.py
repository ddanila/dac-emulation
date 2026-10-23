import hashlib,json,subprocess,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
class DacRampTests(unittest.TestCase):
 def test_actual_dac_boundary_and_control(self):
  fixture=HERE/'fixtures/ngspice-47';original=(fixture/'dac_bridge.mod').read_text()
  self.assertEqual(hashlib.sha256(original.encode()).hexdigest(),json.loads((fixture/'dac-source.json').read_text())['sha256'])
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/'src/xspice/icm/digital/dac_bridge/cfunc.mod';p.parent.mkdir(parents=True);p.write_text(original)
   for patched in (False,True):
    if patched:subprocess.run(['patch','-d',str(root),'-p1','-i',str(HERE/'engine-patches/dac-ramp-breakpoint.patch')],check=True,capture_output=True)
    code=p.read_text();start=code.index('        /* Multiple single-bit conversions. */');end=code.index('\n        break;\n\n    default:',start)
    harness=(HERE/'fixtures/dac_ramp_harness.c').read_text().replace('/* SINGLE_BIT_EVALUATOR */',code[start:end])
    (root/'test.c').write_text(harness);subprocess.run(['cc','-std=gnu11','-O2',str(root/'test.c'),'-lm','-o',str(root/'test')],check=True)
    subprocess.run([str(root/'test'),str(int(patched))],check=True,capture_output=True)
if __name__=='__main__':unittest.main()
