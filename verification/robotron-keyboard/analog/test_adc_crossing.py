#!/usr/bin/env python3
import hashlib,json,subprocess,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
class AdcCrossingTest(unittest.TestCase):
 def test_native_adc_body(self):
  fixture=HERE/'fixtures/ngspice-47';original=(fixture/'adc_bridge.mod').read_text()
  self.assertEqual(hashlib.sha256(original.encode()).hexdigest(),json.loads((fixture/'adc-source.json').read_text())['sha256'])
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/'src/xspice/icm/digital/adc_bridge/cfunc.mod';p.parent.mkdir(parents=True);p.write_text(original)
   # Patch applies both with and without the optional live logging patch.
   subprocess.run(['patch','-d',str(root),'-p1','-i',str(HERE/'engine-patches/adc-crossing-breakpoint.patch')],check=True,capture_output=True)
   source=p.read_text();helper=source[source.index('static Digital_State_t get_out_value'):source.index('void cm_adc_bridge(ARGS)')]
   body=source[source.index('    /* Normal, multiple single-bit conversion output option. */'):].rstrip()
   self.assertTrue(body.endswith('}'));body=body[:-1]
   harness=(HERE/'fixtures/adc_crossing_harness.c').read_text().replace('/* GET_OUT_VALUE */',helper).replace('/* NORMAL_CONVERSION */',body)
   (root/'test.c').write_text(harness)
   subprocess.run(['cc','-std=gnu11','-O2',str(root/'test.c'),'-lm','-o',str(root/'test')],check=True,capture_output=True)
   subprocess.run([str(root/'test')],check=True,capture_output=True)
if __name__=='__main__':unittest.main()
