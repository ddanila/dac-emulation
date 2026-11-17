"""Independent Python oracle comparison, including misses and integration refinement."""
import math
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import beam_render
import trajectory
import trajectory_native


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.backend=trajectory_native.Backend()

    def test_python_oracle_across_fields_steps_and_interceptions(self):
        for inputs in ((11000,350,175,0,0),(11000,350,175,.2,-.1),
                       (8000,280,90,-.7,.5),(11000,350,175,30,0),
                       (80,350,175,0,0),(11000,-350,-175,0,0)):
            for step in (.0002,.0001):
                with self.subTest(inputs=inputs,step=step):
                    a=trajectory.bundle(*inputs,step_m=step)
                    b=self.backend.bundle(*inputs,step_m=step)
                    for ar,br in zip(a['rays'],b['rays']):
                        self.assertEqual(ar.keys(),br.keys())
                        self.assertEqual(ar['reason'],br['reason'])
                        self.assertEqual(ar['landed'],br['landed'])
                        self.assertEqual(len(ar['points']),len(br['points']))
                        for key in ('flight_s','impact_energy_ev','energy_error_ev','x_m','y_m'):
                            if key in ar:self.assertAlmostEqual(ar[key],br[key],delta=max(1e-8 if key.endswith('_ev') else 1e-15,abs(ar[key])*1e-7))
                        for x,y in zip(ar['points'],br['points']):
                            for u,v in zip(x,y):self.assertAlmostEqual(u,v,delta=1e-12)

    def test_render_energy_and_linear_image_agree(self):
        rows=[(0,11000,350,175,0,.2,.1,20e-6),(2e-7,11000,350,175,0,.2,.1,0)]
        renderers=[beam_render.Renderer(surface=dict(width=32,height=24),backend=b) for b in ('python','compiled')]
        for r in renderers:r.render(rows,[0,2e-7])
        a,b=renderers
        self.assertEqual(a.frames[-1]['display'],b.frames[-1]['display'])
        for x,y in zip(a.frames[-1]['linear'],b.frames[-1]['linear']):self.assertAlmostEqual(x,y,delta=max(1e-20,abs(x)*1e-6))
        for key,x in a.report()['energy'].items():self.assertAlmostEqual(x,b.report()['energy'][key],delta=max(1e-25,abs(x)*1e-8))
        self.assertIn('-fno-fast-math',b.report()['backend_build']['flags'])


if __name__=='__main__':unittest.main()
