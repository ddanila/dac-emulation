#!/usr/bin/env python3
"""Compile the real correction ledger against the captured two-capacitor loss."""
import ctypes,json,shlex,subprocess,tempfile,unittest
from fractions import Fraction as F
from pathlib import Path
HERE=Path(__file__).parent
class PairedHistoryTest(unittest.TestCase):
 def test_observed_conservation_loss_and_native_correction(self):
  fixture=json.loads((HERE/'fixtures/paired_cap_history.json').read_text())
  raw=sum((F(float.fromhex(v)) for v in fixture['rhs']),F(0))
  self.assertEqual(raw,F(1,2**22))
  statements=['RobotronMpfr s={0}; robotron_mpfr_init(&s,3,256); robotron_mpfr_reset(&s); cap_used=0;']
  for i,v in enumerate(fixture['rhs']):statements.append(f'robotron_mpfr_set(&s,{i},3,{float.fromhex(v).hex()});')
  for i,c in enumerate(fixture['capacitors']):
   for key in ('before','after'):statements.append(f'double {key}{i}[6]={{'+','.join(float.fromhex(v).hex() for v in c[key])+'};')
   statements.append(f'if(RobotronCapPairRhs({c["p"]},{c["n"]},{float.fromhex(c["history"]).hex()},before{i},after{i})) return NAN;')
  statements+=['if(robotron_cap_apply(&s)) return NAN;','for(int i=0;i<3;i++)for(int j=0;j<3;j++)if(!mpfr_zero_p(s.cells[i*4+j]))return NAN;','mpfr_set_zero(s.sum,0);','for(int i=0;i<3;i++) mpfr_add(s.sum,s.sum,s.cells[i*4+3],MPFR_RNDN);','double v=mpfr_get_d(s.sum,MPFR_RNDN);robotron_mpfr_destroy(&s);return v;']
  source='#include "mpfr_linear_solver.h"\n#include "capacitor_assembly.h"\ndouble check(void){'+''.join(statements)+'}\n'
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory);(p/'check.c').write_text(source)
   flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','mpfr','gmp'],text=True))
   subprocess.run(['cc','-shared','-fPIC','-O2','-I'+str(HERE/'engine-patches'),str(p/'check.c'),*flags,'-o',str(p/'check.so')],check=True)
   lib=ctypes.CDLL(str(p/'check.so'));lib.check.restype=ctypes.c_double
   self.assertEqual(lib.check(),0.)
if __name__=='__main__':unittest.main()
