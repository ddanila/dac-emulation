import ctypes
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
HERE=Path(__file__).resolve().parent
class PostCapTests(unittest.TestCase):
    def test_retained_producers_and_assessment_agree(self):
        root=HERE/'reports/host-postcap-additions'
        manifest=json.loads((root/'manifest.json').read_text())
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        for name,digest in manifest['files'].items():self.assertEqual(sha(root/name),digest,name)
        summary=json.loads((root/'assessment.json').read_text())
        for mode,row in summary['runs'].items():
            report=json.loads((root/mode/'report.json').read_text())
            control=json.loads((root/mode/'postcap-control.json').read_text())
            self.assertEqual(row['reportSha256'],sha(root/mode/'report.json'))
            self.assertEqual(control['reportSha256'],row['reportSha256'])
            self.assertEqual(row['completed'],report['completed'])
            self.assertEqual(row['solverDiagnostic'],report['solverDiagnostic'])
        self.assertTrue(summary['disabledControlPassed'])
        self.assertFalse(summary['qualified'])

    def test_small_late_stamp_is_restored_with_ground_excluded(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);(p/'check.c').write_text('''#include "mpfr_linear_solver.h"
#include "capacitor_assembly.h"
#include "postcap_additions.h"
double check(int ground) {
 double before[4]={1e16,1e16,-1e16,-1e16},after[4]={1e16,1e16,-1e16,-1e16};
 cap_used=0;
 if(RobotronPostCapAdd(1,ground?0:2,1,before,after))return NAN;
 if(cap_used!=(ground?1:4))return NAN;
 if(!ground && mpq_get_d(cap_entries[2].value)!=-1)return NAN;
 RobotronMpfr s={0};robotron_mpfr_init(&s,2,256);robotron_mpfr_reset(&s);
 robotron_mpfr_set(&s,0,0,1e16);robotron_cap_apply(&s);
 mpfr_sub_d(s.sum,s.cells[0],1e16,MPFR_RNDN);double x=mpfr_get_d(s.sum,MPFR_RNDN);
 robotron_mpfr_destroy(&s);return x;
}
''')
            flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','mpfr','gmp'],text=True))
            subprocess.run(['cc','-shared','-fPIC','-O2','-I'+str(HERE/'engine-patches'),str(p/'check.c'),*flags,'-o',str(p/'check.so')],check=True)
            lib=ctypes.CDLL(str(p/'check.so'));lib.check.argtypes=[ctypes.c_int];lib.check.restype=ctypes.c_double
            self.assertEqual(lib.check(0),1.);self.assertEqual(lib.check(1),1.)
if __name__=='__main__':unittest.main()
