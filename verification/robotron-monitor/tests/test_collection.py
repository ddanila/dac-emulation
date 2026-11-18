from pathlib import Path
import json,math,os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import collection,trajectory,trajectory_native,beam_render,electrothermal
import steady_supply

class CollectionTests(unittest.TestCase):
    def test_periodic_arrivals_preserve_charge_and_unresolved_is_rejected(self):
        c=collection.PeriodicCollector(1,bins=16)
        c.add(.99,1.01,2e-9,2e-5,'anode','offscreen-anode')
        r=c.report(2e-9);collection.validate(r)
        self.assertAlmostEqual(sum(r['currents_a']['anode'])/16,2e-9)
        self.assertEqual(r['late_arrival_charge_c'],2e-9)
        self.assertGreater(r['currents_a']['anode'][0],0)
        c.add(.1,.2,1e-9,1e-5,'unresolved','unsupported')
        with self.assertRaisesRegex(ValueError,'unaccepted'):collection.validate(c.report(3e-9))

    def test_current_tampering_and_missing_collector_rejected(self):
        c=collection.PeriodicCollector(1,bins=4);c.add(.1,.2,1,2,'anode','phosphor');r=c.report(1)
        r['currents_a']['anode'][0]=0
        with self.assertRaises(ValueError):collection.validate(r)
        r=c.report(1);del r['currents_a']['anode']
        with self.assertRaises(ValueError):collection.validate(r)

    def test_accounting_cannot_hide_nonfinite_or_unresolved_charge(self):
        c=collection.PeriodicCollector(1,bins=4);c.add(.1,.2,1,2,'anode','phosphor')
        for key in ('emitted_charge_c','integrated_launch_charge_c','charge_relative_error','unresolved_fraction'):
            r=c.report(1);r[key]=float('nan')
            with self.assertRaises(ValueError):collection.validate(r)
        c.add(.1,.2,.1,.2,'unresolved','unsupported');r=c.report(1.1)
        r.update(charge_accepted=True,unresolved_fraction=0)
        with self.assertRaisesRegex(ValueError,'unresolved'):collection.validate(r)

    def test_collector_native_python_parity_and_screen_clipping(self):
        native=trajectory_native.Backend()
        for inputs in ((11000,350,175,.2,0),(11000,350,175,5,0),(80,350,175,0,0)):
            a=trajectory.ray(*inputs);b=native.ray(*inputs)
            self.assertEqual(a['collector'],b['collector']);self.assertEqual(a['collection_surface'],b['collection_surface'])
        r=trajectory.ray(11000,350,175,.2,0,overrides={'screen_width_m':.001})
        self.assertEqual(r['reason'],'screen clipping');self.assertEqual(r['collector'],'anode')

    def test_renderer_accounts_launched_charge_independent_of_visibility(self):
        rows=[(0,11000,350,175,0,.2,0,1e-5),(1e-7,11000,350,175,0,.2,0,2e-5)]
        c=collection.PeriodicCollector(1e-7,bins=16)
        renderer=beam_render.Renderer(surface={'width':16,'height':12,'screen_width_m':.001},field={'screen_width_m':.001},backend='compiled',on_collection=c.add)
        renderer.render(rows,[0,1e-7]);r=c.report(1.5e-12)
        self.assertTrue(r['charge_accepted']);self.assertGreater(r['surface_charge_c']['offscreen-anode'],0)
        self.assertAlmostEqual(r['terminal_kinetic_j'],renderer.incident_j,delta=1e-18)

    def test_feedback_replaces_anode_branch_and_preserves_grid_branch(self):
        c=collection.PeriodicCollector(.02,bins=4);c.add(.01,.010001,1e-8,1e-4,'anode','phosphor');r=c.report(1e-8)
        base=electrothermal.model();coupled=electrothermal.model(collection_report=r)
        self.assertEqual(coupled.count('Bbeam anode'),1)
        self.assertIn('Bbeam anode 0 I={v(collection_current_ua)*1e-6}',coupled)
        self.assertIn('Blaunchload 0 cathode I={v(launch_current_ua)*1e-6}',coupled)
        self.assertEqual([l for l in base.splitlines() if l.startswith('Bg2 ')],[l for l in coupled.splitlines() if l.startswith('Bg2 ')])
        self.assertIn('Blaunch launch_current_ua',coupled)

    @unittest.skipUnless(Path(os.environ.get('MONITOR_RUNTIME','build/monitor/runtime-clean')).exists(),'pinned runtime required')
    def test_real_solver_has_separate_emission_and_arrival_terminal_currents(self):
        c=collection.PeriodicCollector(.001,bins=4)
        for i in range(4):c.add(i*.00025,i*.00025,5e-10,5e-6,'anode','phosphor')
        model=electrothermal.model(initial_rise_k=(800,700),hold_temperature=True,collection_report=c.report(2e-9))
        deck='Collector terminal fixture\n'+model+'''
Vh heater 0 12
Va anode 0 10000
Vc cathode 0 50
Vg1 g1 0 48
Vg2 g2 0 350
Xcrt heater 0 cathode g1 g2 anode th tc CRT_THERMAL
.options reltol=1e-6 abstol=1e-12
.save time i(Va) i(Vc) v(xcrt.launch_current_ua) @b.xcrt.bg2[i] @b.xcrt.bbeam[i]
.tran 1u .001 0 1u
.end
'''
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'solve'
            result=steady_supply.solve(deck,path,Path(os.environ.get('MONITOR_RUNTIME','build/monitor/runtime-clean')),timeout_s=30)
            self.assertEqual(result['status'],'complete')
            row=list(steady_supply.raw_rows(path/'trace.raw'))[-1]
        launch=row['v(xcrt.launch_current_ua)']*1e-6;grid=row['i(@b.xcrt.bg2[i])']
        self.assertGreater(launch,0);self.assertGreater(grid,0)
        self.assertAlmostEqual(row['i(va)'],-2e-6,delta=1e-12)
        self.assertAlmostEqual(row['i(@b.xcrt.bbeam[i])'],2e-6,delta=1e-12)
        self.assertAlmostEqual(row['i(vc)'],launch+grid,delta=1e-12)

if __name__=='__main__':unittest.main()
