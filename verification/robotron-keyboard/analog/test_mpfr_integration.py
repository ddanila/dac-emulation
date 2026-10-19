"""Check experimental integration against independent exact binary64-input arithmetic."""
import ctypes
from decimal import Decimal, localcontext
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        p = Path(cls.directory.name)
        (p/'check.c').write_text('#include "mpfr_integration.h"\n'
            'int check(int m,int o,double *a,double *q,double v,double c,double *r)'
            '{return robotron_mpfr_integrate(m,o,a,q,v,c,r);}\n')
        flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','mpfr','gmp'],text=True))
        subprocess.run(['cc','-shared','-fPIC','-O2','-I'+str(HERE/'engine-patches'),
                        str(p/'check.c'),*flags,'-o',str(p/'check.so')],check=True)
        cls.library = ctypes.CDLL(str(p/'check.so'))
        cls.function = cls.library.check
        cls.function.argtypes = [ctypes.c_int,ctypes.c_int,ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),ctypes.c_double,ctypes.c_double,ctypes.POINTER(ctypes.c_double)]
        cls.function.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def calculate(self, method, order, a, q, v, cap):
        output = (ctypes.c_double * 3)(123,456,789)
        code = self.function(method,order,(ctypes.c_double*7)(*a),
                             (ctypes.c_double*7)(*q),v,cap,output)
        return code,list(output)

    def test_orders_cancellation_and_repeated_calls(self):
        # Include a large leading term plus a small history contribution and
        # near-equal flux histories, as encountered when timestep collapses.
        for scale in (1., 1e18, 1e-18):
            a = [2*scale,-scale,.5*scale,-.25*scale,.125*scale,-.0625*scale,.03125*scale]
            q = [1e-8,1e-8+2e-24,1e-8-2e-24,2e-8,3e-8,4e-8,5e-8]
            v,cap = .002,1e-6
            for method in (0,1):
                for order in range(1,(6 if method else 2)+1):
                    with self.subTest(scale=scale,method=method,order=order),localcontext() as ctx:
                        ctx.prec = 200
                        aa,qq = list(map(Decimal,a)),list(map(Decimal,q))
                        history = (-aa[1]*Decimal(v)-aa[0]*qq[1] if method==0 and order==2
                                   else sum(aa[i]*qq[i] for i in range(1,order+1)))
                        expected = list(map(float,[aa[0]*qq[0]+history,history,aa[0]*Decimal(cap)]))
                        code,actual = self.calculate(method,order,a,q,v,cap)
                        self.assertEqual(code,0)
                        self.assertEqual(actual,expected)

    def test_invalid_and_overflow_leave_outputs_untouched(self):
        a,q = [1.]*7,[1.]*7
        for method,order in ((2,1),(0,3),(1,0),(1,7)):
            self.assertEqual(self.calculate(method,order,a,q,1.,1.),(1,[123.,456.,789.]))
        self.assertEqual(self.calculate(0,1,a,q,float('nan'),1.)[0],1)
        a[0]=float('inf')
        self.assertEqual(self.calculate(0,1,a,q,1.,1.)[0],1)
        a[0]=1e308
        self.assertEqual(self.calculate(0,1,a,q,1.,1e308),(2,[123.,456.,789.]))


if __name__ == '__main__':
    unittest.main()
