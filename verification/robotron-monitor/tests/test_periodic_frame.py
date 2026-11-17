import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import beam_render
import phosphor
import periodic_frame
from test_beam_render import row


class RecordedRenderer(beam_render.Renderer):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.arrivals=[]

    def _drain(self, time):
        self.arrivals.extend((e[0],e[2],e[3],e[4]) for e in self.events if e[0]<=time)
        super()._drain(time)


class PeriodicFrameTests(unittest.TestCase):
    def test_analytic_equilibrium_matches_long_repeated_deposition_and_flight(self):
        period=2e-7
        renderer=RecordedRenderer(surface=dict(width=32,height=24,tau_s=1e-6),
                                  backend='compiled',max_dt_s=2e-9)
        renderer.render([row(0),row(period)],[0,period])
        state,linear,display=periodic_frame.equilibrium(renderer,0,period)
        self.assertGreater(state['late_arrivals_folded'],0)
        arrivals=renderer.arrivals+[(e[0],e[2],e[3],e[4]) for e in renderer.events]
        repeated=phosphor.Surface(renderer.surface.p)
        stop=120*period
        # Independent continuous history: no modulo folding, no closed-form
        # state initializer. Sort to account for cross-period electron flight.
        history=sorted((t+k*period,x,y,j) for k in range(120) for t,x,y,j in arrivals
                       if t+k*period<=stop)
        for event in history:
            repeated.deposit(*event)
        expected,_=repeated.snapshot(stop)
        error=sum((a-b)**2 for a,b in zip(linear,expected))/sum(v*v for v in expected)
        self.assertLess(error,1e-12)
        ledger=state['energy']
        self.assertEqual(ledger['initial_stored_optical_j'],ledger['final_stored_optical_j'])
        self.assertEqual(ledger['deposited_optical_j'],ledger['emitted_optical_j'])
        self.assertLess(ledger['kinetic_balance_relative_error'],1e-10)
        self.assertGreater(sum(state['energy_j']),sum(renderer.surface.energy))
        with self.assertRaises(ValueError):periodic_frame.equilibrium(renderer,period/2,period)

    def test_exports_one_frame_without_claiming_electrical_equilibrium(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);trace=root/'trace.csv'
            with trace.open('w') as stream:
                writer=csv.writer(stream);writer.writerow(beam_render.FIELDS)
                writer.writerows([row(0),row(2e-7)])
            result=periodic_frame.run(trace,root/'out',surface=dict(width=32,height=24,tau_s=1e-6))
            self.assertEqual(result['status'],'complete')
            self.assertFalse(result['electrical_settling_verified'])
            self.assertFalse(result['thermal_equilibrium_verified'])
            self.assertFalse(result['full_monitor_qualified'])
            self.assertEqual(len(list((root/'out').glob('*.png'))),1)
            self.assertEqual((root/'out/frame.f32').stat().st_size,32*24*4)
            for artifact in result['outputs'].values():
                self.assertEqual(artifact['sha256'],periodic_frame.digest(root/'out'/artifact['path']))
            state=json.loads((root/'out/periodic-state.json').read_text())
            self.assertTrue(state['assumed_periodic_electrical_history'])
            self.assertEqual(state['format'],'dac-periodic-phosphor-state-v1')
            # An analytic optical state must not be mistaken for an electrical
            # or general Renderer continuation checkpoint.
            with self.assertRaises(ValueError):beam_render.Renderer(continuation=state)

    def test_optical_refinement_and_archive_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);trace=root/'trace.csv'
            with trace.open('w') as stream:
                writer=csv.writer(stream);writer.writerow(beam_render.FIELDS)
                writer.writerows([row(0),row(2e-7)])
            surface=dict(width=32,height=24,tau_s=1e-6)
            periodic_frame.run(trace,root/'base',surface=surface)
            periodic_frame.run(trace,root/'fine',surface=surface,step_m=.0001,max_dt_s=1/55296000)
            r=periodic_frame.compare(root/'base',root/'fine')
            self.assertTrue(r['accepted'],r)
            self.assertFalse(r['electrical_settling_verified'])
            with self.assertRaises(ValueError):periodic_frame.compare(root/'base',root/'base')
            with self.assertRaises(ValueError):periodic_frame.compare(root/'base',root/'fine',spatial=True)
            raw=(root/'fine/frame.f32').read_bytes()
            (root/'fine/frame.f32').write_bytes(raw[:-1]+bytes([raw[-1]^1]))
            with self.assertRaises(ValueError):periodic_frame.compare(root/'base',root/'fine')

    def test_optical_cache_keys_settings_and_refuses_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);trace=root/'trace.csv'
            with trace.open('w') as stream:
                writer=csv.writer(stream);writer.writerow(beam_render.FIELDS)
                writer.writerows([row(0),row(2e-7)])
            options=dict(surface=dict(width=32,height=24,tau_s=1e-6))
            a=periodic_frame.cached_run(trace,root/'a',root/'cache',**options)
            b=periodic_frame.cached_run(trace,root/'b',root/'cache',**options)
            self.assertFalse(a['cache']['hit']);self.assertTrue(b['cache']['hit'])
            self.assertFalse(b['electrical_settling_verified'])
            c=periodic_frame.cached_run(trace,root/'c',root/'cache',step_m=.0001,**options)
            self.assertNotEqual(a['cache']['key'],c['cache']['key'])
            artifact=root/'cache'/a['cache']['key']/'frame.f32'
            artifact.write_bytes(b'corrupt')
            with self.assertRaises(ValueError):periodic_frame.cached_run(trace,root/'bad',root/'cache',**options)
            self.assertFalse((root/'bad').exists())

    def test_zero_emission_and_unfinished_window(self):
        renderer=beam_render.Renderer(surface=dict(width=32,height=24),backend='compiled')
        with self.assertRaises(ValueError):periodic_frame.equilibrium(renderer,0,1e-7)
        renderer.render([row(0,beam=0),row(1e-7,beam=0)],[0,1e-7])
        state,linear,display=periodic_frame.equilibrium(renderer,0,1e-7)
        self.assertEqual(sum(linear),0)
        self.assertEqual(sum(display),0)
        self.assertEqual(state['energy']['terminal_kinetic_j'],0)


if __name__=='__main__':unittest.main()
