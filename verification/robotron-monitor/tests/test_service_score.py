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
                for i in range(1201):
                    t=i*.00005
                    vertical=0. if ((t-.001) % .019)<.0005 else 10.
                    feedback=70. if (t % .0000625)<.000006 else 0.
                    writer.writerow((t,vertical,feedback))
            result=service_score.score(path,required={5,14})
            points={p['test_point']:p for p in result['points']}
            self.assertEqual(points[5]['status'],'pass-numeric')
            self.assertEqual(points[14]['status'],'pass-numeric')
            self.assertEqual(points[16]['status'],'missing-probe')
            self.assertEqual(result['required_failures'],[])
            result=service_score.score(path,required={5,16})
            self.assertEqual(result['required_failures'],[16])

    def test_bad_amplitude_is_reported_without_fitting(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'samples.txt'
            path.write_text('time v(h_feedback)\n0 0\n0.000001 10\n0.000002 0\n')
            result=service_score.score(path,required={14})
            point=next(p for p in result['points'] if p['test_point']==14)
            self.assertEqual(point['status'],'fail-numeric')
            self.assertEqual(result['required_failures'],[14])


if __name__=='__main__':unittest.main()
