#!/usr/bin/env python3
"""Compare the compiled conversion with an independent exact rational oracle."""
import ctypes
from fractions import Fraction
import math
from pathlib import Path
import platform
import random
import subprocess
import tempfile
import unittest
from build_absolute_tick_vpi import instrument
HERE=Path(__file__).resolve().parent


class AbsoluteTicks(unittest.TestCase):
    def test_exact_floor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'probe.c';library=root/'probe.so'
            source.write_text('#include "'+str(HERE/'fixtures/absolute_ticks.h')+'"\nint probe(double t,double u,uint64_t *r){return robotron_absolute_ticks(t,u,r);}\n')
            subprocess.run(['cc','-dynamiclib' if platform.system()=='Darwin' else '-shared','-fPIC',str(source),'-o',str(library)],check=True)
            fn=ctypes.CDLL(str(library)).probe;fn.argtypes=[ctypes.c_double,ctypes.c_double,ctypes.POINTER(ctypes.c_uint64)];fn.restype=ctypes.c_int
            cases=[(0.,1e-12),(math.ulp(0.),math.ulp(0.)),(1.,math.ulp(0.)),(math.ulp(0.),1.),(float(2**64),1.),(math.nextafter(float(2**64),0),1.)]
            for n in (1,10000,1071501280,1096019098,2**53):
                center=n*1e-12
                cases.extend((v,1e-12) for v in (math.nextafter(center,0),center,math.nextafter(center,math.inf)))
            rng=random.Random(2817)
            for _ in range(4000):
                tick=math.ldexp(rng.uniform(.5,1),rng.randint(-1000,900))
                target=math.ldexp(tick*rng.uniform(.5,1),rng.randint(-2,70))
                cases.append((target,tick))
            for target,tick in cases:
                value=ctypes.c_uint64();status=fn(target,tick,ctypes.byref(value));expected=int(Fraction(target)/Fraction(tick))
                if expected>=2**64:self.assertEqual(status,-1)
                else:self.assertEqual((status,value.value),(0,expected),(target,tick))
            for target,tick in [(math.nan,1.),(math.inf,1.),(-1.,1.),(1.,0.),(1.,-1.),(1.,math.nan),(1.,math.inf)]:
                self.assertEqual(fn(target,tick,ctypes.byref(ctypes.c_uint64())),-1)

    def test_guarded_source_boundary(self):
        marker='static PLI_INT32 next_advance_cb(struct t_cb_data *cb);'
        old='        ticks = (uint64_t)\n            ((ctx->cosim_context->vtime - vl_time)  / ctx->tick_length);'
        text=instrument(marker+'\n'+old,'HELPER')
        self.assertIn('getenv("ROBOTRON_ABSOLUTE_TICKS")',text)
        self.assertEqual(text.count(old),1)
        self.assertIn('target_ticks-current_ticks',text)
        with self.assertRaises(ValueError):instrument(marker,'HELPER')


if __name__=='__main__':unittest.main()
