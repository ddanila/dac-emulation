import ctypes
import math
from pathlib import Path
import subprocess
import tempfile
import unittest


class RepresentedStepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        root = Path(cls.directory.name)
        header = Path(__file__).parent/'engine-patches/represented_time_step.h'
        source = root/'check.c'
        source.write_text('#include "'+str(header)+'"\n'
                          'int step(double b,double d,double m,double *n,double *e) '
                          '{return robotron_represented_step(b,d,m,n,e);}\n')
        subprocess.run(['cc', '-O2', '-shared', '-fPIC', str(source), '-lm',
                        '-o', str(root/'check.so')], check=True)
        cls.library = ctypes.CDLL(str(root/'check.so'))
        cls.function = cls.library.step
        cls.function.argtypes = [ctypes.c_double]*3 + [ctypes.POINTER(ctypes.c_double)]*2
        cls.function.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def call(self, base, requested, minimum):
        next_time, effective = ctypes.c_double(-1), ctypes.c_double(-2)
        status = self.function(base, requested, minimum,
                               ctypes.byref(next_time), ctypes.byref(effective))
        return status, next_time.value, effective.value

    def test_observed_small_step_uses_represented_interval(self):
        base = 0.001098012248419263
        requested = 7.039865963290375e-19
        status, next_time, effective = self.call(base, requested, 5e-19)
        self.assertEqual(status, 0)
        self.assertEqual(effective, 3*math.ulp(base))
        self.assertEqual(next_time-base, effective)
        self.assertNotEqual(requested, effective)
        self.assertEqual(next_time-effective, base)

    def test_floor_and_no_progress_rounding(self):
        for requested, minimum in [(5e-19, 5e-19), (1e-25, 5e-19)]:
            base = .001098012248419263
            status, next_time, effective = self.call(base, requested, minimum)
            self.assertEqual(status, 0)
            self.assertGreater(next_time, base)
            self.assertEqual(next_time-base, effective)
            self.assertGreaterEqual(effective, min(requested, minimum))
            self.assertLess(effective-min(requested, minimum), math.ulp(next_time))

    def test_ordinary_step_and_breakpoint_below_floor(self):
        self.assertEqual(self.call(0, .25, .5), (0, .25, .25))
        self.assertEqual(self.call(1, .125, .001), (0, 1.125, .125))

    def test_invalid_or_overflow_leaves_outputs_unchanged(self):
        for args in [(math.inf, 1, 1), (math.nan, 1, 1), (-1, 1, 1),
                     (1, 0, 1), (1, -1, 1), (1, math.nan, 1),
                     (1, 1, 0), (1, 1, math.inf), (1e308, 1e308, 1)]:
            self.assertEqual(self.call(*args), (1, -1, -2))


if __name__ == '__main__':
    unittest.main()
