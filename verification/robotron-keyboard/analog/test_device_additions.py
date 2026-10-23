import os,subprocess,tempfile,shlex,unittest,json,hashlib,lzma
from pathlib import Path
HERE=Path(__file__).resolve().parent
class DeviceAdditionsTests(unittest.TestCase):
 def test_retained_evidence(self):
  root=HERE/'reports/host-device-additions'
  manifest=json.loads((root/'manifest.json').read_text())
  for name,digest in manifest['files'].items():
   self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),digest,name)
  for mode,receipt in manifest['retained'].items():
   for name,digest in receipt['compressed'].items():
    self.assertEqual(hashlib.sha256(lzma.decompress((root/mode/(name+'.xz')).read_bytes())).hexdigest(),digest)
  summary=json.loads((root/'assessment.json').read_text())
  self.assertTrue(summary['disabledControlPassed']);self.assertFalse(summary['qualified'])
 def test_accumulation_ground_and_unmapped_guard(self):
  source=r'''#include "mpfr_linear_solver.h"
#include "capacitor_assembly.h"
#include "device_additions.h"
int main(int argc,char **argv) {
 (void)argc;double value=1e16,ground=0,rhs=1e16;
 robotron_device_address(&value,1,1);robotron_device_address(&ground,0,1);
 if(RobotronCapReset()!=1)return 1;
 RobotronDeviceAdd(&value,1,-1);RobotronDeviceAdd(&value,-1e16,-1);
 RobotronDeviceAdd(&rhs,1,1);RobotronDeviceAdd(&rhs,-1e16,1);
 RobotronDeviceAdd(&ground,1,-1);
 RobotronMpfr s={0};robotron_mpfr_init(&s,1,256);robotron_mpfr_reset(&s);
 robotron_mpfr_set(&s,0,0,value);robotron_mpfr_set(&s,0,1,rhs);
 if(robotron_cap_apply(&s)||device_error)return 2;
 double expected=argv[1][0]=='e'?1:0;
 if(mpfr_cmp_d(s.cells[0],expected)||mpfr_cmp_d(s.cells[1],expected))return 3;
 robotron_mpfr_destroy(&s);
 if(expected) { double unknown=0;RobotronDeviceAdd(&unknown,1,-1);if(!device_error)return 4; }
 return 0;
}'''
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'check.c').write_text(source)
   flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','mpfr','gmp'],text=True))
   subprocess.run(['cc','-std=c11','-O2','-I'+str(HERE/'engine-patches'),str(p/'check.c'),*flags,'-o',str(p/'check')],check=True)
   for mode in ('off','exact'):
    subprocess.run([str(p/'check'),mode],env=dict(os.environ,ROBOTRON_DEVICE_ASSEMBLY=mode,ROBOTRON_CAP_ASSEMBLY='exact',ROBOTRON_MPFR_BITS='256'),check=True)
if __name__=='__main__':unittest.main()
