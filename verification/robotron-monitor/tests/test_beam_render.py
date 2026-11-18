import copy,csv,json,math,struct,sys,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import beam_render,phosphor,trajectory


def row(time,beam=20e-6,ih=0.,iv=0.,offset=0.):
    return (time,11000+offset,350+offset,175+offset,offset,ih,iv,beam)


class PhosphorTests(unittest.TestCase):
    def test_energy_decay_clipping_and_fixed_exposure(self):
        s=phosphor.Surface(dict(width=32,height=24))
        s.deposit(0,0,0,1e-6)
        linear,display=s.snapshot(0)
        initial=sum(s.energy);self.assertAlmostEqual(initial,8e-8)
        s.snapshot(s.p['tau_s'])
        self.assertAlmostEqual(sum(s.energy),initial/math.e)
        self.assertAlmostEqual(s.emitted_j+sum(s.energy),s.deposited_j)
        s.deposit(s.time,.5,0,1e-6);self.assertAlmostEqual(s.clipped_j,8e-8)
        a=phosphor.Surface(dict(width=32,height=24));b=phosphor.Surface(dict(width=32,height=24))
        a.deposit(0,0,0,1e-5);b.deposit(0,0,0,2e-5)
        la,da=a.snapshot(0);lb,db=b.snapshot(0)
        self.assertAlmostEqual(sum(lb),2*sum(la));self.assertGreater(max(db),max(da))
        with self.assertRaises(ValueError):s.snapshot(0)
        with self.assertRaises(ValueError):s.deposit(s.time,0,0,-1)

    def test_square_pixels_letterboxing_and_resolution(self):
        s=phosphor.Surface(dict(width=64,height=48));s.deposit(0,0,.01,1e-6)
        s.deposit(0,.01,0,1e-6)
        # Actual screen rectangle is letterboxed, not stretched to the canvas.
        self.assertEqual(s.scale,64/.210)
        self.assertTrue(all(v==0 for v in s.energy[:64]))
        r=phosphor.Surface(dict(width=128,height=96));r.deposit(0,0,0,1e-6)
        q=phosphor.Surface(dict(width=64,height=48));q.deposit(0,0,0,1e-6)
        self.assertAlmostEqual(sum(r.energy),sum(q.energy))
        for change in ({'efficiency':2},{'width':True},{'tau_s':0},{'other':1}):
            with self.assertRaises(ValueError):phosphor.Surface(change)
        narrow=phosphor.Surface(dict(width=8,height=2048))
        narrow.deposit(0,0,0,1e-6)
        self.assertAlmostEqual(sum(narrow.energy),8e-8)

    def test_pixel_area_integration_is_conservative_under_refinement(self):
        import image_acceptance
        coarse=phosphor.Surface(dict(width=64,height=48))
        fine=phosphor.Surface(dict(width=128,height=96))
        events=[(0,-.104999,0,1e-6),(1e-7,.00123,.00456,2e-6),
                (2e-7,.104999,.07,3e-6),(3e-7,.105001,0,4e-6)]
        for event in events:
            coarse.deposit(*event);fine.deposit(*event)
        a,_=coarse.snapshot(1e-6);b,_=fine.snapshot(1e-6)
        projected=image_acceptance.project(b,fine,coarse)
        self.assertLess(image_acceptance.error(a,projected,coarse.areas),1e-7)
        self.assertAlmostEqual(coarse.deposited_j,6e-6*.08)
        self.assertAlmostEqual(coarse.clipped_j,4e-6*.08)
        self.assertAlmostEqual(fine.deposited_j,coarse.deposited_j)


class BeamRenderTests(unittest.TestCase):
    def test_chord_integrates_changing_current_and_energy_by_pixel_area(self):
        renderer=beam_render.Renderer(surface=dict(width=8,height=8))
        a=row(0,beam=2e-6);b=row(1e-6,beam=5e-6)
        left=dict(x_m=-.1,y_m=.001,flight_s=0,impact_energy_ev=100)
        right=dict(x_m=.1,y_m=.001,flight_s=0,impact_energy_ev=200)
        renderer._chord(a,b,left,right,1)
        self.assertAlmostEqual(renderer.incident_j,5.5e-10,delta=1e-24)
        actual={}
        for event in renderer.events:
            index=renderer.surface.cell(event[2],event[3])
            actual[index]=actual.get(index,0)+event[-1]
        def integral(f):return 1e-6*(200e-6*f+250e-6*f*f+100e-6*f**3)
        for index,energy in actual.items():
            column=index%8;scale=renderer.surface.scale
            lo=max(0,((column-4)/scale+.1)/.2)
            hi=min(1,((column+1-4)/scale+.1)/.2)
            self.assertAlmostEqual(energy,integral(hi)-integral(lo),delta=1e-24)

    def test_chord_matches_bisection_reference_for_a_moving_beam(self):
        import image_acceptance,periodic_frame
        renderers=[];images=[]
        for mode in ('chord','bisect'):
            renderer=beam_render.Renderer(surface=dict(width=64,height=48),backend='compiled',
                max_dt_s=1e-6,pixel_mode=mode)
            renderer.render([row(0,ih=-.1),row(10e-6,beam=30e-6,ih=.1)],[0,10e-6])
            _,linear,_=periodic_frame.equilibrium(renderer,0,10e-6)
            renderers.append(renderer);images.append(linear)
        self.assertLess(image_acceptance.error(*images,renderers[0].surface.areas),.01)
        self.assertLess(renderers[0].bundles,renderers[1].bundles)
        self.assertAlmostEqual(renderers[0].incident_j/renderers[1].incident_j,1,delta=.001)

    def test_continuation_preserves_phosphor_arrivals_and_energy(self):
        args=dict(surface=dict(width=32,height=24),max_dt_s=2e-8)
        rows=[row(0),row(2e-7),row(4e-7,beam=0)]
        continuous=beam_render.Renderer(**args);continuous.render(rows,[0,2e-7,4e-7])
        first=beam_render.Renderer(**args);first.render(rows[:2],[0,2e-7])
        state=json.loads(json.dumps(first.checkpoint()))
        self.assertTrue(state['arrivals'])
        resumed=beam_render.Renderer(**args,continuation=state)
        resumed.render(rows[1:],[2e-7,4e-7])
        self.assertEqual(continuous.frames[-1]['display'],resumed.frames[-1]['display'])
        self.assertEqual(continuous.frames[-1]['linear'],resumed.frames[-1]['linear'])
        for key,value in continuous.report()['energy'].items():
            self.assertAlmostEqual(value,resumed.report()['energy'][key],delta=max(abs(value)*1e-10,1e-25))
        bad=copy.deepcopy(state);bad['surface']['energy_j'][0]+=1
        with self.assertRaises(ValueError):beam_render.Renderer(**args,continuation=bad)
        bad=copy.deepcopy(state);bad['kinetic_energy']['terminal_j']+=1
        with self.assertRaises(ValueError):beam_render.Renderer(**args,continuation=bad)
        bad=copy.deepcopy(state);bad['model_hashes']['trajectory.py']='0'*64
        with self.assertRaises(ValueError):beam_render.Renderer(**args,continuation=bad)
        with self.assertRaises(ValueError):beam_render.Renderer(**args,continuation=state).render([row(2e-7,beam=0),row(4e-7)],[2e-7,4e-7])

    def test_stream_matches_frames_and_does_not_retain_callback_output(self):
        args=dict(surface=dict(width=32,height=24),max_dt_s=2e-8)
        rows=[row(0),row(2e-7),row(4e-7,beam=0)]
        times=[0,1e-7,3e-7,4e-7]
        normal=beam_render.Renderer(**args);normal.render(rows,times)
        streamed=beam_render.Renderer(**args);frames=[]
        streamed.render_stream((r for r in rows),times,on_frame=frames.append)
        self.assertEqual(frames,normal.frames)
        self.assertEqual(streamed.frames,[])
        self.assertEqual(streamed.checkpoint(),normal.checkpoint())
        for bad in (rows[:-1],rows+[row(5e-7)],rows+[row(float('nan'))]):
            renderer=beam_render.Renderer(**args)
            with self.assertRaises(ValueError):renderer.render_stream(iter(bad),times,on_frame=lambda f:None)
            with self.assertRaises(ValueError):renderer.checkpoint()
        with self.assertRaisesRegex(ValueError,'row budget'):
            beam_render.Renderer(**args).render_stream(iter(rows),times,row_budget=2)

    def test_fail_closed_limits_and_single_use(self):
        for rows,times in (([],[]),([row(-1),row(0)],[-1,0]),
                           ([row(0),row(2)],[0,2]),([row(0),row(.1)],[0,float('nan'),.1])):
            with self.assertRaises(ValueError):beam_render.Renderer(surface=dict(width=8,height=8)).render(rows,times)
        r=beam_render.Renderer(surface=dict(width=8,height=8))
        rows=[row(0,beam=0),row(1e-7,beam=0)]
        r.render(rows,[0,1e-7])
        with self.assertRaises(ValueError):r.render(rows,[0,1e-7])
        with self.assertRaisesRegex(ValueError,'frame budget'):
            beam_render.Renderer(surface=dict(width=1024,height=1024)).render(rows,[1e-7*i/119 for i in range(120)])

    def test_voltage_reference_and_physical_landing(self):
        r=beam_render.Renderer(surface=dict(width=32,height=24),max_dt_s=1e-6)
        a=r.bundle(row(0,ih=.2));b=r.bundle(row(0,ih=.2,offset=100))
        self.assertEqual(a,b)
        self.assertGreater(a['x_m'],0)
        self.assertAlmostEqual(a['rays'][0]['impact_energy_ev'],11020,delta=1)
        self.assertFalse(r.bundle(row(0,ih=30))['landed_fraction'])

    def test_darkness_flight_time_partition_and_refinement(self):
        args=dict(surface=dict(width=32,height=24),max_dt_s=2e-8)
        rows=[row(0),row(2e-7),row(4e-7,beam=0)]
        a=beam_render.Renderer(**args);b=beam_render.Renderer(**args,step_m=.0001)
        a.render(rows,[0,4e-7]);b.render(rows,[0,2e-7,4e-7])
        self.assertFalse(any(a.frames[0]['display']))
        self.assertGreater(sum(a.frames[-1]['linear']),0)
        self.assertLess(abs(sum(a.frames[-1]['linear'])/sum(b.frames[-1]['linear'])-1),.01)
        self.assertLess(abs(a.report()['energy']['deposited_optical_j']/b.report()['energy']['deposited_optical_j']-1),.01)
        dark=beam_render.Renderer(**args);dark.render([row(0,beam=0),row(4e-7,beam=0)],[0,4e-7])
        self.assertFalse(any(dark.frames[-1]['display']))
        flight=trajectory.ray(11000,350,175,0,0)['flight_s']
        early=beam_render.Renderer(**args);early.render([row(0),row(flight/4)],[0,flight/4])
        self.assertEqual(sum(early.frames[-1]['linear']),0)
        self.assertGreater(early.report()['energy']['in_flight_kinetic_j'],0)

    def test_import_export_and_failed_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);trace=root/'trace.csv'
            with trace.open('w') as out:
                writer=csv.writer(out);writer.writerow(beam_render.FIELDS);writer.writerows([row(300),row(300.0000002)])
            report=beam_render.run(trace,root/'good',surface=dict(width=32,height=24),max_dt_s=2e-8)
            self.assertEqual(report['version'],3);self.assertFalse(report['full_monitor_qualified'])
            self.assertEqual(report['qualification'],'experimental-optical-bench')
            self.assertEqual(report['start_time'],300)
            self.assertTrue((root/'good/frame-001.png').read_bytes().startswith(b'\x89PNG'))
            self.assertEqual((root/'good/frame-001.f32').stat().st_size,32*24*4)
            raw=(root/'good/replay.mcrt').read_bytes();size=struct.unpack_from('<I',raw,8)[0]
            meta=json.loads(raw[12:12+size]);payload=raw[12+size:]
            for c in meta['chunks']:self.assertEqual(beam_render.digest(payload[c['offset']:c['offset']+c['bytes']]),c['sha256'])
            with patch.object(phosphor,'png',side_effect=OSError('export failed')):
                with self.assertRaises(OSError):beam_render.run(trace,root/'export-failed',surface=dict(width=8,height=8))
            self.assertFalse((root/'export-failed/replay.mcrt').exists())
            self.assertEqual(json.loads((root/'export-failed/render.json').read_text())['status'],'incomplete')
            trace.write_text('wrong,columns\n1,2\n')
            with self.assertRaises(ValueError):beam_render.run(trace,root/'bad')
            self.assertEqual(json.loads((root/'bad/render.json').read_text())['status'],'incomplete')
            self.assertFalse((root/'bad/replay.mcrt').exists())


if __name__=='__main__':unittest.main()
