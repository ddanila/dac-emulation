import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import service_score
import steady_supply
import json


class ServiceScoreTests(unittest.TestCase):
    def test_every_manual_point_maps_to_an_assembled_node(self):
        with tempfile.TemporaryDirectory() as directory:
            assembly=steady_supply.assemble(Path(directory)/'assembly')
            nodes={node for component in assembly['components'] for node in component['nodes']}
        register=json.loads(service_score.REGISTER.read_text())
        self.assertEqual([w['test_point'] for w in register['waveforms']],list(range(1,18)))
        self.assertFalse([(w['test_point'],w['model_node']) for w in register['waveforms']
                          if w['model_node'] not in nodes])
        self.assertEqual(register['waveforms'][16]['approximate_swing_v'],80)
        self.assertEqual(register['auxiliary_waveforms'][0]['label'],'9a')
        self.assertIn('converter is excluded',register['auxiliary_waveforms'][0]['stage_status'])

    def test_manual_pulse_and_missing_required_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'samples.csv'
            with path.open('w',newline='') as stream:
                writer=csv.writer(stream)
                writer.writerow(('time','v(vertical_pulse)','v(h_feedback)'))
                for i in range(60001):
                    t=i*.000001
                    vertical=0. if ((t-.001) % .019)<.0005 else 10.
                    feedback=70. if (t % .0000625)<.000006 else 0.
                    writer.writerow((t,vertical,feedback))
            result=service_score.score(path,required={5,14})
            points={p['test_point']:p for p in result['points']}
            self.assertEqual(points[5]['status'],'pass-numeric')
            self.assertEqual(points[14]['status'],'pass-numeric')
            self.assertEqual(points[5]['shape_status'],'pass')
            self.assertEqual(points[14]['shape_status'],'pass')
            self.assertEqual(points[16]['status'],'missing-probe')
            self.assertEqual(points[7]['reference']['rise_time_s'],.001)
            self.assertEqual(points[5]['reference']['condition_id'],'service-eo2')
            self.assertEqual(points[5]['reference']['instrument'],'service oscilloscope EO2')
            self.assertIn('Richtwerte',points[5]['reference']['operating_conditions'])
            self.assertEqual(result['required_failures'],[])
            result=service_score.score(path,required={5,16})
            self.assertEqual(result['required_failures'],[16])

    def test_pulse_polarity_and_sampling_resolution_are_checked(self):
        register=json.loads(service_score.REGISTER.read_text())
        wave=next(w for w in register['waveforms'] if w['test_point']==14)
        times=[i*1e-6 for i in range(2001)]
        correct=[70. if t%62.5e-6<6e-6 else 0. for t in times]
        wrong=[70-v for v in correct]
        measured=service_score.measure(times,correct,wave)
        checks,_=service_score.shape_checks(times,correct,wave,measured)
        self.assertTrue(all(checks.values()))
        measured=service_score.measure(times,wrong,wave)
        checks,_=service_score.shape_checks(times,wrong,wave,measured)
        self.assertFalse(checks['pulse_polarity'])
        coarse_times=times[::50]
        coarse_values=correct[::50]
        measured=service_score.measure(coarse_times,coarse_values,wave)
        checks,_=service_score.shape_checks(coarse_times,coarse_values,wave,measured)
        self.assertFalse(checks['sample_resolution'])

    def test_sawtooth_direction_is_checked(self):
        wave={'period_s':1e-4,'polarity':'rising-ramp',
              'shape_descriptor':{'family':'rising-sawtooth'}}
        times=[i*5e-7 for i in range(1001)]
        rising=[(t%1e-4)/1e-4 for t in times]
        falling=[1-v for v in rising]
        measured=service_score.measure(times,rising,wave)
        checks,_=service_score.shape_checks(times,rising,wave,measured)
        self.assertTrue(all(checks.values()))
        measured=service_score.measure(times,falling,wave)
        checks,_=service_score.shape_checks(times,falling,wave,measured)
        self.assertFalse(checks['ramp_direction'])
        one_cycle_times=[i*5e-7 for i in range(200)]
        one_cycle_values=[(t%1e-4)/1e-4 for t in one_cycle_times]
        measured=service_score.measure(one_cycle_times,one_cycle_values,wave)
        checks,_=service_score.shape_checks(one_cycle_times,one_cycle_values,wave,measured)
        self.assertTrue(all(checks.values()))

    def test_bad_amplitude_is_reported_without_fitting(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'samples.txt'
            path.write_text('time v(h_feedback)\n0 0\n0.000001 10\n0.000002 0\n')
            result=service_score.score(path,required={14})
            point=next(p for p in result['points'] if p['test_point']==14)
            self.assertEqual(point['status'],'fail-numeric')
            self.assertEqual(result['required_failures'],[14])


if __name__=='__main__':unittest.main()
