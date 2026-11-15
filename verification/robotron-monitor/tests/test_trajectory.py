import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import trajectory as t


class TrajectoryTests(unittest.TestCase):
    def test_axis_energy_and_flight_time(self):
        r=t.ray(11000,350,175,0,0)
        self.assertTrue(r['landed'])
        self.assertEqual((r['x_m'],r['y_m']),(0,0))
        self.assertLess(r['energy_error_ev'],1)
        self.assertGreater(r['flight_s'],.28/t.C)
        self.assertLess(r['flight_s'],100e-9)
        self.assertFalse(t.ray(0,0,0,0,0)['landed'])

    def test_finite_field_polarity_and_eht(self):
        a=t.ray(11000,350,175,.2,.1)
        b=t.ray(11000,350,175,-.2,-.1)
        c=t.ray(22000,350,175,.2,.1)
        self.assertTrue(a['landed'])
        self.assertGreater(a['x_m'],0);self.assertGreater(a['y_m'],0)
        self.assertAlmostEqual(a['x_m'],-b['x_m'],places=12)
        self.assertLess(abs(c['x_m']),abs(a['x_m']))
        self.assertLess(a['energy_error_ev'],1)
        self.assertTrue(any(abs(x)>0 for z,x,y in a['points'] if .075<z<.115))

    def test_bundle_convergence_and_aperture_clipping(self):
        a=t.bundle(11000,350,175,.2,.1)
        b=t.bundle(11000,350,175,.2,.1,step_m=.0001)
        self.assertEqual(a['landed_fraction'],1)
        self.assertGreater(a['sigma_m'],0)
        self.assertLess(math.hypot(a['x_m']-b['x_m'],a['y_m']-b['y_m']),.210/160*.25)
        self.assertLess(abs(a['sigma_m']-b['sigma_m']),.210/160*.25)
        self.assertFalse(t.ray(11000,350,175,30,0)['landed'])
        self.assertFalse(t.ray(11000,350,175,0,0,origin=(.003,0))['landed'])
        for kw in ({'step_m':0},{'overrides':{'screen_radius_m':.01}},{'overrides':{'extra':1}}):
            with self.assertRaises(ValueError):t.ray(11000,350,175,0,0,**kw)


if __name__=='__main__':unittest.main()
