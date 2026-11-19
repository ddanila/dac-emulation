import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import service_probe
import service_score
import phase_a_gates


class ServiceProbeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('ngspice'),'ngspice is required')
    def test_control_deck_wrdata_is_a_valid_loaded_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            deck=root/'run.cir'
            deck.write_text('Control-block stage with service output\n'
                'Vsrc src 0 PULSE(0 5 0 1u 1u 5u 10u)\n'
                'Rsrc src y1 100000\n'
                '.control\nset noaskquit\nset wr_singlescale\nset wr_vecnames\n'
                'tran 0.1u 40u 0 0.01u\nlinearize v(y1)\n'
                'wrdata samples.txt v(y1)\nquit\n.endc\n.end\n')
            process=subprocess.run(['ngspice','-n','-b','run.cir'],
                                   cwd=root,capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stdout+process.stderr)
            baseline=root/'samples.txt'
            self.assertTrue(baseline.is_file())
            manifest=service_probe.run(deck,baseline,root/'probe',[8])
            loaded=service_probe.validate(manifest,baseline)[8]
            self.assertEqual(loaded.name,'samples.txt')
            result=service_score.score(baseline,required={8},
                                       probe_manifest=manifest,stimulus='grid')
            point=next(p for p in result['points'] if p['test_point']==8)
            self.assertEqual(point['instrument_model_status'],
                             'circuit probe load and bandwidth applied')
            self.assertEqual(result['qualification'],
                             'probe-and-bandwidth-modeled grid comparison; manual values are guidelines')
            diagnostic=service_score.score(baseline,required={8},probe_manifest=manifest)
            self.assertEqual(diagnostic['qualification'],
                             'diagnostic-only; grid stimulus not established')

    @unittest.skipUnless(shutil.which('ngspice'),'ngspice is required')
    def test_loaded_solve_changes_a_high_impedance_node_and_is_reproducible(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            deck=root/'run.cir'
            deck.write_text('High impedance service node\n'
                'Vsrc src 0 PULSE(0 70 0 1n 1n 10u 62.5u)\n'
                'Rsrc src h_feedback 1000000\n'
                '.save time v(h_feedback)\n'
                '.tran 0.1u 250u 0 0.1u\n.end\n')
            process=subprocess.run(['ngspice','-n','-b','-r','base.raw','-o','base.log','run.cir'],
                                   cwd=root,capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stdout+process.stderr)
            manifest=service_probe.run(deck,root/'base.raw',root/'probe',[14])
            self.assertEqual(set(service_probe.validate(manifest,root/'base.raw')),{14})
            result=service_score.score(root/'base.raw',required={14},
                                       probe_manifest=manifest,stimulus='grid')
            point=next(p for p in result['points'] if p['test_point']==14)
            self.assertGreater(point['raw_measured']['peak_to_peak_v'],60)
            self.assertLess(point['loaded_unfiltered_measured']['peak_to_peak_v'],
                            point['raw_measured']['peak_to_peak_v']/2)
            self.assertEqual(point['instrument_model_status'],
                             'circuit probe load and bandwidth applied')
            self.assertEqual(result['instrument_loading_status'],'required points circuit-loaded')
            self.assertEqual(result['stimulus'],'grid')
            self.assertIn('probe-and-bandwidth-modeled',result['qualification'])
            self.assertTrue(phase_a_gates.verify_service_score(result))
            case=json.loads(manifest.read_text())['cases'][0]
            self.assertEqual(Path(case['deck']).read_text().count('Rserviceprobe '),1)
            self.assertEqual(Path(case['deck']).read_text().count('Cserviceprobe '),1)
            loaded=Path(case['deck'])
            loaded.write_text(loaded.read_text().replace('1000000','2000000'))
            with self.assertRaisesRegex(ValueError,'probe trace or circuit differs'):
                service_probe.validate(manifest,root/'base.raw')
            with self.assertRaisesRegex(ValueError,'probe trace or circuit differs'):
                phase_a_gates.verify_service_score(result)


if __name__=='__main__':unittest.main()
