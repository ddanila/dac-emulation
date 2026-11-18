import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import calibration_contract as contract
import service_score
import transformer_candidates


class CalibrationContractTests(unittest.TestCase):
    def test_only_manual_calibration_set_can_be_frozen(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'grid.csv'
            with path.open('w',newline='') as stream:
                writer=csv.writer(stream)
                writer.writerow(('time','v(h_feedback)','v(h_drivecol)','v(h_sync)'))
                for i in range(1001):
                    t=i*1e-6;phase=t%62.5e-6
                    writer.writerow((t,70. if phase<6e-6 else 0.,
                                     45. if phase<6e-6 else 0.,
                                     0. if phase<6e-6 else 90.))
            score=service_score.score(path,required={14,15,17})
            self.assertEqual(score['required_failures'],[])
            graph=json.loads((ROOT/'reference/k7222-11/t3-winding-hypothesis.json').read_text())
            candidate=transformer_candidates.enumerate_candidates(graph)[0]['id']
            def identified(p):return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            proposal={'format':'dac-monitor-calibration-proposal-v1','source_kind':'synthetic-test-pattern',
                      'source_capture_sha256':'a'*64,'fit_points':[14,15,17],
                      'image_used_for_selection':False,'candidate_id':candidate,
                      'assumptions':{'t3_candidate':candidate,
                                     't3_winding_parameters':identified(ROOT/'reference/k7222-11/t3-initial-parameters.json'),
                                     'yoke_profile':identified(ROOT/'profiles/k7222-11-yoke-geometry.json'),
                                     'l4_coupling':.5,'horizontal_tank_l':.0015},
                      'trims':{key:{'setting':.5,'procedure_step':'manual'} for key in contract.TRIM_KEYS},
                      'targets':{'eht_v':11500,'horizontal_retrace_us':16,
                                 'picture_width_mm':210,'picture_height_mm':145}}
            frozen=contract.freeze(proposal,score)
            self.assertTrue(contract.verify(frozen))
            proposal['fit_points']=[9,14,15,17]
            with self.assertRaisesRegex(ValueError,'fit points'):
                contract.freeze(proposal,score)
            frozen['targets']['eht_v']=12500
            with self.assertRaisesRegex(ValueError,'changed'):
                contract.verify(frozen)


if __name__=='__main__':unittest.main()
