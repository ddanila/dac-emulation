import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import beam_render
import lab
import lock_scan
import scan_diagnostics
import steady_acceptance
import steady_supply
import trajectory
import yoke_profile
import sync_lock
import horizontal_isolation


class ReferenceTests(unittest.TestCase):
    def test_lock_interval_does_not_bridge_failed_or_single_samples(self):
        entries=[dict(trim=i/10,accepted=v) for i,v in enumerate((True,False,True,True,True,False,True))]
        interval=lock_scan.midpoint(entries)
        self.assertEqual(interval['lower'],.2);self.assertEqual(interval['upper'],.4)
        self.assertAlmostEqual(interval['midpoint'],.3)
        self.assertIsNone(lock_scan.midpoint(entries[:2]))

    def test_trim_update_preserves_tank_and_is_atomic(self):
        selection=dict(line_period_ticks=625,period_ticks=195000,clock_hz=10000000)
        assembly=dict(parameters={})
        steady_supply.tune(assembly,selection,{'horizontal_tank_l':.001532})
        steady_supply.tune(assembly,selection,{'horizontal_trim_fraction':.4})
        self.assertEqual(assembly['parameters']['horizontal_tank_l'],.001532)
        before=dict(assembly['parameters'])
        with self.assertRaises(ValueError):
            steady_supply.tune(assembly,selection,{'horizontal_trim_fraction':.6,'invented':1})
        self.assertEqual(assembly['parameters'],before)

    def test_native_sync_rejects_average_frequency_without_tracking(self):
        # Deliberately nonuniform source: nominal-frequency free run must fail.
        events=[[0,0,1,0]]
        edges=[100*i+(3 if i%2 else 0) for i in range(1,10)]
        for edge in edges:events.extend([[edge,0,0,0],[edge+10,0,1,0]])
        selection=dict(events=events,period_ticks=1000,line_period_ticks=100,clock_hz=100000)
        source=[k*.01+t/100000 for k in range(3) for t in edges]
        self.assertTrue(sync_lock.compare([t+.0001 for t in source],selection,0,.03)['accepted'])
        free=[i*.001+.0001 for i in range(30)]
        self.assertFalse(sync_lock.compare(free,selection,0,.03)['accepted'])
        self.assertFalse(sync_lock.compare(source[:10]+source[11:],selection,0,.03)['accepted'])
        self.assertFalse(sync_lock.compare([],selection,0,.03)['accepted'])

    def test_boundary_refinement_only_extends_with_measured_passes(self):
        trials=[dict(trim=x,accepted=.21<=x<=.69) for x in (.1,.3,.5,.7)]
        def trial(value,name):return dict(trim=value,accepted=.21<=value<=.69)
        bracket=lock_scan.refine_bracket(trials,trial,time.monotonic()+60)
        self.assertGreaterEqual(bracket['lower'],.21)
        self.assertLess(bracket['lower'],.22)
        self.assertLessEqual(bracket['upper'],.69)
        self.assertGreater(bracket['upper'],.68)
        self.assertLess(bracket['lower_outside'],.21)
        self.assertGreater(bracket['upper_outside'],.69)

    def test_lock_scan_preserves_override_and_checks_independent_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);capture=root/'capture.json';capture.write_text('{}')
            selection=dict(status='complete',line_period_ticks=625,period_ticks=195000,clock_hz=10000000)
            assembly=dict(parameters={},magnetic_graph={})
            calls=[]
            def deck(a,selection,candidate,**options):
                calls.append((dict(a['parameters']),options))
                return 'fixture',dict(parameters=dict(a['parameters']))
            def solve(text,path,runtime,timeout_s):
                path.mkdir(parents=True)
                self.assertGreater(timeout_s,0)
                return dict(status='complete')
            def assess(path,meta,selection):
                return dict(accepted=meta['parameters']['horizontal_trim_fraction']>=.1)
            with mock.patch.object(lab,'parse_capture',return_value=dict(qualification='schematic-derived-logical')), \
                 mock.patch.object(steady_supply,'select',return_value=selection), \
                 mock.patch.object(steady_supply,'assemble',return_value=assembly), \
                 mock.patch.object(lock_scan.transformer_candidates,'enumerate_candidates',return_value=[dict(id='fixture')]), \
                 mock.patch.object(steady_supply,'deck',side_effect=deck), \
                 mock.patch.object(steady_supply,'solve',side_effect=solve), \
                 mock.patch.object(steady_supply,'assess',side_effect=assess), \
                 mock.patch.object(steady_acceptance,'compare',return_value=dict(accepted=False)) as comparison:
                report=lock_scan.run(capture,root/'scan',root/'runtime','fixture',hours=.01,
                    settings=dict(parameters=dict(horizontal_tank_l=.001532)),workers=3)
            self.assertEqual(report['status'],'blocked')
            self.assertIsNone(report['selected_trim'])
            comparison.assert_called_once()
            self.assertTrue(all(p['horizontal_tank_l']==.001532 for p,o in calls))
            self.assertNotEqual(calls[-2][1].get('initial_voltages',{}),calls[-1][1]['initial_voltages'])
            self.assertLess(len(report['trials']),14)
            self.assertEqual(report['validation_reserved_s'],12)

    def test_isolation_stimuli_are_explicitly_retimed_not_connected_lock(self):
        rows=[{'time':i*1e-6,'v(sync_c)':10 if i%64<8 else 0,
               'v(h_hot)':400 if i%63<8 else 0,'v(h_feedback)':60+(60 if i%63<8 else 0)}
              for i in range(1001)]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'raw';path.write_bytes(b'fixture')
            with mock.patch.object(steady_supply,'raw_rows',return_value=iter(rows)):
                result=horizontal_isolation.recorded_cycles(path)
        self.assertFalse(result['connected_lock_verified'])
        self.assertEqual(len(result['waveforms']['sync']),256)
        self.assertAlmostEqual(result['original_periods_s']['sync'],64e-6)
        self.assertAlmostEqual(result['original_periods_s']['feedback'],63e-6)
        self.assertEqual(result['isolation_period_s'],62.5e-6)
        deck,meta=horizontal_isolation.make_deck({'horizontal_tank_l':.001532},4)
        self.assertIn('Vcontrol h_control 0 4',deck)
        self.assertFalse(meta['full_monitor_qualified'])
        with self.assertRaises(ValueError):horizontal_isolation.make_deck({},30)

    def test_expired_diagnostic_budget_does_not_substitute_old_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with mock.patch.object(steady_acceptance,'optical_worker') as worker:
                r=steady_acceptance.diagnostic_frame(root/'new-trial',{},root/'diagnostic',
                    dict(accepted=False,failures=['unlocked']),time.monotonic()-1)
            self.assertEqual(r['status'],'blocked')
            self.assertEqual(r['outputs'],{})
            self.assertFalse(r['accepted_warmed_frame'])
            worker.assert_not_called()

    def test_sparse_source_is_not_a_collapsed_raster(self):
        selection=dict(period_ticks=400,line_period_ticks=100,clock_hz=10000,
                       events=[[0,0,1,0],[310,1,1,0],[320,0,1,0]])
        report,pixels=scan_diagnostics.source_summary(selection,width=100)
        self.assertEqual(report['active_lines'],[3])
        self.assertAlmostEqual(report['active_video_s'],.001)
        self.assertEqual(sum(v>0 for v in pixels),10)
        selection['events']=[[0,0,1,0]]
        report,pixels=scan_diagnostics.source_summary(selection,width=100)
        self.assertEqual(report['active_lines'],[]);self.assertFalse(any(pixels))
        with tempfile.TemporaryDirectory() as tmp:
            trace=Path(tmp)/'field.csv'
            trace.write_text(','.join(beam_render.FIELDS)+'\n0,11000,350,175,0,0,0,0\n.001,11000,350,175,0,0,0,0\n')
            with self.assertRaises(ValueError):list(scan_diagnostics.phase_samples(trace,64,expected_period=.02))

    def test_cathode_common_mode_is_subtracted_once(self):
        renderer=beam_render.Renderer(backend='compiled')
        row=(0,11000,350,175,10,.1,.05,1e-5)
        shifted=(0,11100,450,275,110,.1,.05,1e-5)
        a,b=renderer.bundle(row),renderer.bundle(shifted)
        self.assertEqual(a,b)

    def test_deflection_against_independent_small_angle_impulse(self):
        # After the gun, energy is constant. The symmetric field envelope has
        # integral length and centroid start+length/2. Integrate Lorentz impulse
        # and free drift independently of the trajectory RK integrator.
        p=trajectory.DEFAULTS;current=.001;voltage=11000
        gamma=1+(voltage+p['initial_energy_ev'])/trajectory.REST_EV
        momentum=trajectory.M*trajectory.C*math.sqrt(gamma*gamma-1)
        expected=trajectory.E/momentum*current*p['horizontal_tesla_per_amp']*p['yoke_length_m']*(p['screen_z_m']-p['yoke_start_m']-p['yoke_length_m']/2)
        a=trajectory.ray(voltage,350,175,current,0,step_m=.0001)
        b=trajectory.ray(voltage,350,175,-current,0,step_m=.0001)
        v=trajectory.ray(voltage,350,175,0,current,step_m=.0001)
        self.assertTrue(a['landed'])
        self.assertAlmostEqual(a['x_m']/expected,1,delta=.001)
        self.assertAlmostEqual(a['x_m'],-b['x_m'],places=12)
        self.assertAlmostEqual(a['x_m'],v['y_m'],places=12)
        self.assertAlmostEqual(a['y_m'],0,places=12)
        fast=trajectory.ray(22000,350,175,current,0,step_m=.0001)
        self.assertLess(fast['x_m'],a['x_m'])

    def test_l4_preserves_shorted_winding_and_passivity(self):
        parts=json.loads((ROOT/'reference/k7222-11/horizontal-output-transcription.json').read_text())['components']
        lines,expanded=steady_supply.compensation_network(parts,.95)
        self.assertEqual(len(expanded),3)
        self.assertIn('LL4_3 l4_internal_3 h_outbase {horizontal_compensation_l}',lines)
        self.assertEqual(sum(line.startswith('KL4_') for line in lines),3)
        # Unit diagonal/equal mutual k has eigenvalues 1-k,1-k,1+2k.
        for k in (0,.5,.95,.999):
            for currents in ((1,-1,0),(1,1,-2),(1,1,1)):
                energy=sum(x*x for x in currents)+2*k*sum(currents[a]*currents[b] for a,b in ((0,1),(0,2),(1,2)))
                self.assertGreater(energy,0)
        with self.assertRaises(ValueError):steady_supply.compensation_network(parts,1.)

    def test_l4_coupled_impedance_matches_three_winding_equations(self):
        parts=json.loads((ROOT/'reference/k7222-11/horizontal-output-transcription.json').read_text())['components']
        lines,_=steady_supply.compensation_network(parts,.95)
        deck='L4 independent impedance check\n.param horizontal_compensation_r=.2 horizontal_compensation_l=100u\nVreturn h_outbase 0 0\nItest 0 h_outputbase AC 1\n'+'\n'.join(lines)+"""
.control
set wr_singlescale
set wr_vecnames
set numdgt=15
ac dec 3 1k 1meg
let zr=real(v(h_outputbase))
let zi=imag(v(h_outputbase))
wrdata samples.txt zr zi
quit
.endc
.end
"""
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);(out/'run.cir').write_text(deck)
            lab.run_command(['ngspice','-b','run.cir'],out,out/'solver.log')
            rows=[list(map(float,r.split())) for r in (out/'samples.txt').read_text().splitlines()[1:]]
        for f,re,im in rows:
            a=.2+2j*math.pi*f*100e-6;m=2j*math.pi*f*95e-6
            expected=(a+m)/2-m*m/a
            self.assertLess(abs(complex(re,im)-expected)/abs(expected),1e-8)
            self.assertGreater(re,0)

    def test_shared_yoke_remains_explicitly_uncalibrated(self):
        p=yoke_profile.read()
        self.assertEqual(p['electrical']['yoke_horizontal_l'],.004)
        self.assertEqual(p['field']['vertical_tesla_per_amp'],.0012)
        self.assertFalse(p['inductance_field_relationship_verified'])
        self.assertGreater(p['effective_energy_volume_m3']['vertical'],p['effective_energy_volume_m3']['horizontal'])
        with tempfile.TemporaryDirectory() as tmp:
            raw=json.loads(yoke_profile.DEFAULT.read_text());raw['vertical']['tesla_per_amp']=-1
            path=Path(tmp)/'bad.json';path.write_text(json.dumps(raw))
            with self.assertRaises(ValueError):yoke_profile.read(path)

    def test_failed_refinement_cannot_publish_an_accepted_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def failed(deck,out,runtime,timeout_s):
                Path(out).mkdir(parents=True)
                return dict(status='failed',timeout=False)
            metadata=dict(max_step_s=2e-7,reltol=.005,abstol=1e-6,simulated_fields=4)
            coupling=dict(converged=True,accepted=True,load={},trial=str(root/'trial'),metadata=metadata,settling={'accepted':True})
            with mock.patch.object(steady_supply,'deck',return_value=('test',{})), \
                 mock.patch.object(steady_supply,'solve',side_effect=failed), \
                 mock.patch('beam_feedback.run',return_value=coupling), \
                 mock.patch('energy_validation.run',return_value={'accepted':True}), \
                 mock.patch.object(steady_acceptance,'optical_worker') as optical:
                result=steady_acceptance.finish({}, {}, {},metadata,root/'trial',root/'acceptance',root/'runtime',{},time.monotonic()+60)
            self.assertFalse(result['accepted_warmed_frame'])
            self.assertIn('refinement solver failed',result['blockers'])
            optical.assert_not_called()
            self.assertFalse(list((root/'acceptance').rglob('*.png')))

    def test_acceptance_status_requires_every_gate(self):
        # Orchestration only: these fixtures are never physical acceptance evidence.
        metadata=dict(max_step_s=2e-7,reltol=.005,abstol=1e-6,simulated_fields=4,period_s=.02)
        assembly=dict(yoke={'field':{},'inductance_field_relationship_verified':True})
        for failed_gate in (None,'coupling','energy','optical'):
            with self.subTest(failed_gate=failed_gate),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                coupling=dict(converged=True,accepted=failed_gate!='coupling',load={},trial=str(root/'trial'),metadata=metadata,settling={'accepted':True})
                def solve(text,path,*args,**kwargs):
                    Path(path).mkdir();return {'status':'complete'}
                with mock.patch('beam_feedback.run',return_value=coupling), \
                     mock.patch('energy_validation.run',return_value={'accepted':failed_gate!='energy'}), \
                     mock.patch.object(steady_supply,'deck',return_value=('fixture',metadata)), \
                     mock.patch('electrical_cache.solve',side_effect=solve), \
                     mock.patch.object(steady_acceptance,'compare',return_value={'accepted':True}), \
                     mock.patch.object(steady_acceptance.steady_trace,'export',return_value={}), \
                     mock.patch.object(steady_acceptance,'optical_worker',return_value={'status':'complete'}), \
                     mock.patch('periodic_frame.compare',return_value={'accepted':failed_gate!='optical'}):
                    result=steady_acceptance.finish(assembly, {}, {}, metadata,root/'trial',root/'acceptance',root/'runtime',{},time.monotonic()+60)
                self.assertEqual(result['accepted_warmed_frame'],failed_gate is None)
                self.assertEqual(result['status'],'accepted-experiment' if failed_gate is None else 'blocked')
                self.assertFalse(result['full_monitor_qualified']);self.assertFalse(result['specimen_validated'])

    def test_waveform_comparison_rejects_scaling_and_truncation(self):
        names=('time',*steady_acceptance.NAMES)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def write(name,gain=1,points=401):
                rows=[(i*1e-5,10000,350,200,10,gain*math.sin(i*.1),.1,.01,1e-5) for i in range(points)]
                header=f'Title: acceptance fixture\nFlags: real\nNo. Variables: 9\nNo. Points: {points}\nVariables:\n'
                header+=''.join(f'{i} {n} voltage\n' for i,n in enumerate(names))+'Binary:\n'
                p=root/name;p.write_bytes(header.encode()+b''.join(struct.pack('=9d',*r) for r in rows));return p
            a=write('a');b=write('b',gain=1.2);m=dict(period_s=.001,simulated_fields=4)
            self.assertTrue(steady_acceptance.compare(a,a,m,sample_hz=100000)['accepted'])
            self.assertFalse(steady_acceptance.compare(a,b,m,sample_hz=100000)['accepted'])
            with self.assertRaises(ValueError):steady_acceptance.compare(a,write('short',points=350),m,sample_hz=100000)


if __name__=='__main__':unittest.main()
