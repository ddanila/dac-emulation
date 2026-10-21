"""Check the experimental C correction ledger against exact arithmetic and MPFR."""
import ctypes
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent

class AssemblyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=tempfile.TemporaryDirectory();p=Path(cls.directory.name)
        (p/'check.c').write_text('''#include "mpfr_linear_solver.h"
#include "capacitor_assembly.h"
double check(int order, int ground, int *error) {
    RobotronMpfr s={0};
    double before[6]={1,1,0,0,0,0}, after[6]={1e16,1e16,-1e16,-1e16,0,0};
    cap_used=0;
    *error=RobotronCapAdd(1,ground?0:2,order,1,1,1e16,-1e16,0,0,before,after);
    if (*error) return 0;
    robotron_mpfr_init(&s,2,256);robotron_mpfr_reset(&s);
    robotron_mpfr_set(&s,0,0,1e16);
    *error=robotron_cap_apply(&s);
    mpfr_sub_d(s.sum,s.cells[0],1e16,MPFR_RNDN);
    double result=mpfr_get_d(s.sum,MPFR_RNDN);
    robotron_mpfr_destroy(&s);
    return result;
}
double history(int order, int negative) {
    double before[6]={0}, after[6]={4,4,-4,-4,0,0};
    cap_used=0;
    if (RobotronCapAdd(1,2,order,2,.5,4,order==1?-4:1,3,2,before,after)) return NAN;
    return mpq_get_d(cap_entries[negative?5:4].value);
}
int entries(void) {return cap_used;}
''')
        flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','mpfr','gmp'],text=True))
        subprocess.run(['cc','-shared','-fPIC','-O2','-I'+str(HERE/'engine-patches'),str(p/'check.c'),*flags,'-o',str(p/'check.so')],check=True)
        cls.lib=ctypes.CDLL(str(p/'check.so'))
        cls.lib.check.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.POINTER(ctypes.c_int)]
        cls.lib.check.restype=ctypes.c_double
        cls.lib.history.argtypes=[ctypes.c_int,ctypes.c_int]
        cls.lib.history.restype=ctypes.c_double

    @classmethod
    def tearDownClass(cls):cls.directory.cleanup()

    def test_small_contribution_reaches_mpfr_without_binary64_roundtrip(self):
        for order in (1,2):
            for ground in (0,1,0):
                error=ctypes.c_int(-1)
                self.assertEqual(self.lib.check(order,ground,ctypes.byref(error)),1.)
                self.assertEqual(error.value,0)
                self.assertEqual(self.lib.entries(),2 if ground else 6)

    def test_history_multiplicity_and_terminal_signs(self):
        for order, expected in [(1,24.),(2,28.)]:
            self.assertEqual(self.lib.history(order,0),expected)
            self.assertEqual(self.lib.history(order,1),-expected)

    def test_unsupported_integration_order_is_rejected(self):
        error=ctypes.c_int(-1)
        self.lib.check(3,0,ctypes.byref(error));self.assertEqual(error.value,1)
        self.assertEqual(self.lib.entries(),0)

if __name__=='__main__':unittest.main()
