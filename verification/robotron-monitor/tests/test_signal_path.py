from pathlib import Path
import copy,json,subprocess,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import lab,signal_path,verify_signal_path,export_signal_path,struct


class SignalCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(['make','build/robotron-signal-pattern','build/robotron-monitor-capture','test-robotron-video-output'],cwd=ROOT.parents[1],check=True,capture_output=True)

    def test_patterns_and_strict_v2_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'input.json'
            for name in ('black','white','alternating','bars','checkerboard','text','highlight','grid','crosshatch'):
                path.write_bytes(subprocess.check_output([str(ROOT.parents[1]/'build/robotron-signal-pattern'),name]))
                data=lab.parse_capture(path)
                self.assertEqual(data['format'],'dac-monitor-input-v2')
                self.assertEqual(data['events'][-1][0],112*8*26*12*13)
                if name=='highlight':
                    self.assertEqual(data['events'][0][1:],[1,1,1])
                    self.assertTrue(any(e[3]==0 for e in data['events']))
            original=copy.deepcopy(data)
            for key,value in [('clock_hz',13824000),('signals',['VIDEO','INTENS','BSYN']),('board_revision','unknown'),('time_origin',{'dot_tick':True})]:
                bad=copy.deepcopy(original);bad[key]=value;path.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):lab.parse_capture(path)

    def test_full_screen_grid_and_crosshatch_match_native_s550_timing(self):
        import steady_supply
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'grid.json'
            for pattern in ('grid','crosshatch'):
                path.write_bytes(subprocess.check_output([str(ROOT.parents[1]/'build/robotron-signal-pattern'),
                    pattern,'--fields','4','--line-characters','108']))
                data=lab.parse_capture(path);selection=steady_supply.select(data)
                self.assertEqual(data['qualification'],'synthetic-test-pattern')
                self.assertEqual(data['pattern'],pattern)
                self.assertEqual(selection['status'],'complete')
                self.assertAlmostEqual(selection['period_ticks']/selection['clock_hz'],.0195)
                self.assertAlmostEqual(selection['line_period_ticks']/selection['clock_hz'],62.5e-6)
                self.assertGreater(sum(e[1] for e in selection['events']),1000)

    def test_stopped_machine_capture_is_complete_and_initial_state_is_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            (d/'rom').write_bytes(bytes([0x76])+bytes(2047));(d/'prom').write_bytes(bytes(256))
            (d/'disk').write_bytes(bytes(819200))
            subprocess.run([str(ROOT.parents[1]/'build/robotron-monitor-capture'),str(d/'rom'),str(d/'prom'),'-',str(d/'disk'),'0','1000',str(d/'capture.json')],check=True,capture_output=True)
            data=lab.parse_capture(d/'capture.json');self.assertEqual(data['events'][-1][0],13000)
            self.assertEqual(data['time_origin']['boot_cpu_ticks'],0)
            capture=dict(format='dac-monitor-input-v1',clock_hz=1000,events=[[0,1,1,0],[1,1,1,0]])
            deck=lab.build_deck([dict(reference='V4',nodes=['a','0'],value='0')],'',.001,1e-6,{},capture)
            self.assertIn('V4 a 0 PWL(0 5)',deck)

    def test_source_faults_preserve_independent_signals(self):
        c={'clock_hz':179712000,'events':[[0,0,1,1],[100,1,0,1],[300,0,1,0],[1000,0,1,0]]}
        missing=signal_path.stimulus(c,'missing-sync')
        self.assertTrue(all(e[2]==1 for e in missing))
        self.assertEqual([e[1] for e in missing],[e[1] for e in c['events']])
        changed=signal_path.stimulus(c,'distorted-sync')
        self.assertEqual(next(e[0] for e in changed if e[0]>100 and e[2]==1),390)
        self.assertEqual(next(e[0] for e in changed if e[3]==0),300)

    def test_export_requires_accepted_matching_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);base=root/'nominal/base';base.mkdir(parents=True)
            payload=bytes(16)
            meta=dict(hashes={'deck':'test'},signal_case='nominal',chunks=[dict(kind='trace',offset=0,bytes=16,sha256=lab.digest(payload))])
            header=json.dumps(meta).encode();(base/'replay.mcrt').write_bytes(b'DACCRT2\n'+struct.pack('<I',len(header))+header+payload)
            accepted=dict(status='accepted-characterization',hashes=meta['hashes'],timestep={'passed':True},cable={'passed':True})
            result=dict(format='dac-monitor-signal-verification-v1',status='complete',nominal_accepted=True,cases={'nominal':accepted},publishable_cases=['nominal'],scope='numerical only')
            verify=root/'verification.json';verify.write_text(json.dumps(result))
            out=root/'accepted.mcrt';export_signal_path.export(verify,'nominal',out)
            self.assertTrue(out.read_bytes().endswith(payload))
            with self.assertRaises(FileExistsError):export_signal_path.export(verify,'nominal',out)
            for mutation in ('withheld','incomplete','hash','payload'):
                bad=copy.deepcopy(result)
                if mutation=='withheld':bad['cases']['nominal']['status']='withheld'
                if mutation=='incomplete':bad['status']='incomplete'
                if mutation=='hash':bad['cases']['nominal']['hashes']={'deck':'different'}
                if mutation=='payload':(base/'replay.mcrt').write_bytes((base/'replay.mcrt').read_bytes()[:-1]+b'1')
                verify.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):export_signal_path.export(verify,'nominal',root/(mutation+'.mcrt'))


class SignalElectricalTests(unittest.TestCase):
    def test_loaded_path_fast_edges_and_fault_localization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cap=root/'input.json'
            subprocess.run(['make','build/robotron-signal-pattern'],cwd=ROOT.parents[1],check=True,capture_output=True)
            cap.write_bytes(subprocess.check_output([str(ROOT.parents[1]/'build/robotron-signal-pattern'),'alternating']))
            base=signal_path.run(cap,root/'base',duration=2e-6,step=2e-10)
            refined=signal_path.run(cap,root/'fine',duration=2e-6,step=1e-10)
            cable=signal_path.run(cap,root/'cable',duration=2e-6,step=2e-10,sections=8)
            for other in (refined,cable):
                check=verify_signal_path.compare(base,other)
                self.assertTrue(check['passed'],check['failures'])
            weak=signal_path.run(cap,root/'weak',duration=2e-6,step=2e-10,case='weak-video')
            self.assertLess(weak['metrics']['monitor_video']['maximum'],base['metrics']['monitor_video']['maximum']*.8)
            self.assertGreater(abs(weak['metrics']['cathode']['mean']-base['metrics']['cathode']['mean']),.05)
            report=json.loads((root/'base/report.json').read_text())
            self.assertFalse(report['coverage']['full_monitor_qualified'])
            self.assertIn('012-6931:C12',{c.get('source_id') for c in report['components']})
            diode=next(c for c in report['components'] if c.get('source_id')=='012-6931:V6')
            self.assertEqual(diode['nodes'],['vertical_trigger','vf_diode'])
            self.assertEqual(report['input']['qualification'],'synthetic-test-pattern')
            self.assertTrue((root/'base/replay.mcrt').read_bytes().startswith(b'DACCRT2\n'))
            for args in [dict(sections=3),dict(step=1e-12),dict(changes={'driver_high':99}),dict(case='flyback')]:
                with self.assertRaises(ValueError):signal_path.run(cap,root/'bad',**args)


if __name__=='__main__':unittest.main()
