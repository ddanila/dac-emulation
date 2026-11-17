import copy
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import electrothermal
import lab
import reference
import steady_supply as steady
import transformer_candidates as tc
from test_frames import capture


class SteadySupplyTests(unittest.TestCase):
    def test_one_original_static_field_and_blank_rejection(self):
        c=capture(); original=copy.deepcopy(c);r=steady.select(c)
        self.assertEqual(r['status'],'complete')
        self.assertEqual(r['period_ticks'],3600000)
        self.assertEqual(r['selection']['render_start_tick'],360100)
        self.assertEqual(c,original)
        self.assertFalse(r['monitor_lock_verified'])
        self.assertIn('assumed',r['initialization_history'])
        blank=copy.deepcopy(c)
        for e in blank['events']:e[1]=0
        self.assertEqual(steady.select(blank)['status'],'incomplete')
        self.assertEqual(steady.select(blank,require_video=False)['status'],'complete')
        changing=copy.deepcopy(c)
        for e in changing['events']:e[3]=(e[0]//3600000)%2
        self.assertEqual(steady.select(changing)['status'],'incomplete')

    def test_heater_dc_branch_closes_actual_passive_heat_balance(self):
        result=steady.heater_equilibrium();h,c=result['temperature_rise_k']
        p=electrothermal.parameters();r=p['heater_cold_ohm']*(1+p['heater_alpha']*h)
        actual=(12/(15+r))**2*r
        loss=electrothermal.heat_losses(h,c)
        self.assertAlmostEqual(actual,result['heater_power_w'],places=10)
        self.assertAlmostEqual(loss[0],actual,places=10)
        self.assertAlmostEqual(loss[1],0,places=10)
        self.assertFalse(result['electrical_replay_verified'])

    def test_output_sheet_has_correct_potentiometer_and_series_feed(self):
        table=json.loads((ROOT/'reference/k7222-11/horizontal-output-transcription.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);xml=out/'sheet.xml'
            lab.run_command(['kicad-cli','sch','export','netlist','--format','kicadxml','-o',str(xml),
                str(ROOT/'circuits/k7222-11-horizontal-output.kicad_sch')],out,out/'export.log')
            inv=json.loads((ROOT/'reference/k7222-11/inventory.json').read_text())
            parts=reference.source_connectivity(xml,inv,'012-6921',steady.OUTPUT_CONTRACTS)
            canonical=lambda ps:sorted((p['source_id'],p['reference'],tuple(p['nodes']),p['value']) for p in ps)
            self.assertEqual(canonical(parts),canonical(table['components']))
            by_id={p['source_id']:p for p in parts}
            self.assertEqual(len(parts),37)
            self.assertEqual(by_id['012-6921:R29']['nodes'],['h_g2raw','h_divtop'])
            self.assertEqual(float(by_id['012-6921:R29']['value']),2700)
            self.assertEqual(by_id['012-6921:R28']['value'],'HORIZONTAL_BRIGHTNESS')
            self.assertEqual(by_id['012-6921:R28']['nodes'],['h_g1raw','ug1','0'])
            self.assertEqual(by_id['012-6921:C21']['nodes'],['h_feed','h_boost'])
            self.assertNotIn('hy1',by_id['012-6921:L4:1']['nodes'])

    def test_tapped_flux_backend_preserves_sections_and_bounds(self):
        graph=json.loads((ROOT/'reference/k7222-11/t3-winding-hypothesis.json').read_text())
        params=json.loads((ROOT/'reference/k7222-11/t3-initial-parameters.json').read_text())
        candidates=tc.enumerate_candidates(graph)
        for candidate in candidates:
            model,meta=tc.compile_model(graph,candidate,params,backend='flux')
            self.assertEqual(len(meta['sections']),15)
            self.assertEqual(len(meta['ports']),20)
            self.assertIn('Cflux flux_b',model)
            self.assertFalse(meta['full_monitor_qualified'])
        ac=json.loads((ROOT/'reference/k7222-11/t3-ac-loss-parameters.json').read_text())
        for backend in ('flux','xspice'):
            model,meta=tc.compile_model(graph,candidates[0],ac,backend=backend)
            self.assertIn('Rskin0',model)
            self.assertIn('skin_fraction',meta['sections'][0]['parameters'])
        invalid=copy.deepcopy(ac);invalid['groups']['drive'][0]['skin_fraction']['maximum']=1
        with self.assertRaises(ValueError):tc.compile_model(graph,candidates[0],invalid,backend='flux')
        bad=copy.deepcopy(params);bad['groups']['drive'][0]['turns']['value']=1e8
        with self.assertRaises(ValueError):tc.compile_model(graph,candidates[0],bad,backend='flux')
        with self.assertRaises(ValueError):tc.compile_model(graph,candidates[0],params,backend='invented')

    def test_tuning_and_solver_controls_stay_bounded(self):
        selection=steady.select(capture())
        assembly=dict(parameters={})
        result=steady.tune(assembly,selection,{'vertical_trim':22000})
        self.assertFalse(result['lock_verified'])
        self.assertEqual(assembly['parameters']['vertical_trim'],22000)
        for changes in ({'yoke_horizontal_l':1.},{'horizontal_tank_l':float('nan')},{'invented':1}):
            with self.assertRaises(ValueError):steady.tune(assembly,selection,changes)
        graph=json.loads((ROOT/'reference/k7222-11/t3-winding-hypothesis.json').read_text())
        assembly.update(parameters={k:v[0] for k,v in steady.signal_path.BOUNDS.items()},components=[],models=[])
        candidate=tc.enumerate_candidates(graph)[0]
        text,meta=steady.deck(assembly,selection,candidate,linear_solver='klu',reltol=.001,abstol=1e-8)
        self.assertIn('.options klu reltol=0.001 abstol=1e-08',text)
        self.assertEqual(meta['linear_solver'],'klu')
        with self.assertRaises(ValueError):steady.deck(assembly,selection,candidate,linear_solver='unknown')
        with self.assertRaises(ValueError):steady.deck(assembly,selection,candidate,abstol=1.)

    def test_raw_parser_rejects_partial_or_nonfinite_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'raw'
            h=b'Title: test\nFlags: real\nNo. Variables: 2\nNo. Points: 2\nVariables:\n0 time time\n1 v(x) voltage\nBinary:\n'
            data=struct.pack('=4d',0,1,.01,2)
            p.write_bytes(h+data)
            self.assertEqual(list(steady.raw_rows(p))[-1],{'time':.01,'v(x)':2})
            for raw in (h+data[:-1],h.replace(b'Points: 2',b'Points: 0')+data,h+struct.pack('=4d',0,1,.01,math.nan)):
                p.write_bytes(raw)
                with self.assertRaises(ValueError):list(steady.raw_rows(p))

    def test_settling_requires_phase_lock_not_just_stable_averages(self):
        names=('time','v(eht)','v(g2)','v(g4)','v(cathode)',
               'i(lhorizontal)','i(lvertical)','v(x1136.xshared.flux_b)',
               'v(h_hot)','v(vertical_pulse)','v(p10_7)','i(v.xcrt.vheater)')
        thermal=steady.heater_equilibrium();period=.02;line=50e-6
        metadata=dict(period_s=period,simulated_fields=4,thermal=thermal)
        selection=dict(line_period_ticks=50,clock_hz=1000000)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'trace.raw'
            def solve(line_ticks):
                rows=[]
                for tick in range(80001):
                    t=tick*1e-6;hphase=(tick%line_ticks)/line_ticks;vphase=(tick%20000)/20000
                    rows.append((t,12000,350,200,40,math.sin(2*math.pi*hphase),
                        math.sin(2*math.pi*vphase),.1*math.sin(2*math.pi*hphase),
                        400 if hphase<.1 else 0,0 if vphase<.01 else 10,
                        11,thermal['heater_power_w']/11))
                header='Title: acceptance fixture, not circuit output\nFlags: real\nNo. Variables: 12\nNo. Points: '+str(len(rows))+'\nVariables:\n'
                header+=''.join(f'{i} {name} voltage\n' for i,name in enumerate(names))+'Binary:\n'
                path.write_bytes(header.encode()+b''.join(struct.pack('=12d',*r) for r in rows))
                return steady.assess(path,metadata,selection)
            good=solve(50)
            self.assertTrue(good['accepted'],good['failures'])
            self.assertFalse(good['numerical_refinement_verified'])
            drift=solve(51)
            self.assertFalse(drift['accepted'])
            self.assertIn('horizontal phase drift exceeds 0.01 line',drift['failures'])

    def test_deck_repeats_constant_channels_with_explicit_endpoint(self):
        selection=steady.select(capture());selection['events']=[[e[0],0,e[2],1] for e in selection['events']]
        graph=json.loads((ROOT/'reference/k7222-11/t3-winding-hypothesis.json').read_text())
        p={k:v[0] for k,v in steady.signal_path.BOUNDS.items()}
        text,meta=steady.deck(dict(parameters=p,components=[],models=[]),selection,tc.enumerate_candidates(graph)[0])
        period=meta['period_s']
        self.assertIn(f'Vlogic_video logic_video computer_return PWL(0 0 {period:.15g} 0) r=0',text)
        self.assertIn('Lhorizontal h_winding hy2 {yoke_horizontal_l}',text)
        self.assertNotIn('Vg2 ',text)
        self.assertNotIn('PULSE(',text)
        self.assertIn('Vholdh',text)
        self.assertEqual(meta['simulated_fields'],4)
        with self.assertRaises(ValueError):steady.deck(dict(parameters=p),selection,{},fields=65)

if __name__=='__main__':unittest.main()
