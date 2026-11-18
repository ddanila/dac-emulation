import copy
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import calibration_contract as contract
import phase_a_gates
import service_score as service_scoring


class PhaseAGateTests(unittest.TestCase):
    def setUp(self):
        self.freeze={'format':'dac-monitor-calibration-freeze-v1',
                     'fit_points':[14,15,17],'held_out_points':sorted(contract.HELD_OUT_POINTS),
                     'source_kind':'synthetic-test-pattern','image_used_for_selection':False,
                     'source_capture_sha256':'a'*64,'source_pattern':'grid',
                     'calibration_score_sha256':'b'*64,
                     'calibration_trial':{'trace_sha256':'c'*64,'deck_sha256':'e'*64,
                                          'metadata_sha256':'f'*64,'solver_receipt_sha256':'1'*64,
                                          'eht_mean_v':11500,'horizontal_retrace_us':16,
                                          'horizontal_yoke_swing_a':2.,
                                          'retrace_method':'shorter-extrema-arc-of-line-averaged-yoke-current',
                                          'line_count':312,'phase_bins':256,
                                          'grid_geometry':{'picture_width_mm':210.,'picture_height_mm':145.,
                                              'horizontal_linearity':.04,'vertical_linearity':.04,
                                              'horizontal_center_mm':0.,'vertical_center_mm':0.,
                                              'stripe_rows':5,'horizontal_marker_rows':9,'marker_count':54,
                                              'method':'source-grid-markers-through-connected-electrodes-yoke-and-central-ray'}},
                     'candidate_id':'t3-test',
                     'assumptions':{key:('t3-test' if key=='t3_candidate' else {}) for key in contract.ASSUMPTION_KEYS},
                     'trims':{key:{'setting':.5,'procedure_step':'manual'} for key in contract.TRIM_KEYS},
                     'targets':{'eht_v':11500,'horizontal_retrace_us':16,
                                'picture_width_mm':210,'picture_height_mm':145}}
        self.freeze['freeze_sha256']=contract.digest(self.freeze)
        self.score={'format':'dac-monitor-service-score-v1',
                    'input_sha256':'c'*64,
                    'register_sha256':hashlib.sha256(service_scoring.REGISTER.read_bytes()).hexdigest(),
                    'points':[{'test_point':n,'status':'pass-numeric'} for n in range(1,18)]}
        self.evidence={'format':'dac-monitor-phase-a-gate-evidence-v1',
                       'electrical_trace_sha256':'c'*64,'native_capture_sha256':'d'*64,
                       'waveform_reviews':{str(n):{'shape':'agrees','operating_conditions':'agrees',
                                                   'reviewer':'test fixture'} for n in range(1,18)},
                       'horizontal_lock':{'reference_edges':936,'flybacks_in_window':936,'matched_edges':936,
                                          'missing_edges':0,'reused_flybacks':0,'unmatched_flybacks':0,
                                          'phase_variation_lines':.005,'fields':3,'maximum_adjacent_jitter_s':30e-9},
                       'periodicity':{'fields':3,'relative_errors':{name:.005 for name in phase_a_gates.PERIODIC}},
                       'calibration_measurements':{'electrical_trace_sha256':'c'*64,
                                                   'eht_v':11500,'horizontal_retrace_us':16},
                       'grid_geometry':{'source_kind':'synthetic-test-pattern','picture_width_mm':210,
                                        'source_capture_sha256':'a'*64,'picture_height_mm':145,
                                        'electrical_trace_sha256':'c'*64,
                                        'horizontal_linearity':.04,'vertical_linearity':.04},
                       'electrical_refinement':{'half_timestep':True,'second_initialization':True,
                                                'half_timestep_relative_error':.005,
                                                'second_initialization_relative_error':.005},
                       'optical_refinement':{'relative_error':.01},
                       'readability':{'source_kind':'native-firmware-logical-timing-reference',
                                      'logical_capture_sha256':'d'*64,
                                      'one_global_affine_fit':True,'fit_applied_to_render':False,
                                      'correlation':.8}}

    def test_all_eight_gates_are_blocking(self):
        result=phase_a_gates.evaluate(self.evidence,self.score,self.freeze)
        self.assertTrue(result['accepted'])
        self.assertEqual([g['gate'] for g in result['blocking']],
                         ['G1','G1b','G2','G3','G4','G5','G6','G7','G8'])
        evidence=copy.deepcopy(self.evidence)
        evidence['horizontal_lock']['maximum_adjacent_jitter_s']=40e-9
        evidence['signed_energy_ledger']={'status':'pass'}
        result=phase_a_gates.evaluate(evidence,self.score,self.freeze)
        self.assertFalse(result['accepted'])
        self.assertFalse(next(g['passed'] for g in result['blocking'] if g['gate']=='G1b'))

    def test_explained_held_out_miss_still_blocks(self):
        score=copy.deepcopy(self.score)
        score['points'][0]['status']='fail-numeric'
        evidence=copy.deepcopy(self.evidence)
        evidence['held_out_explanations']={'1':'review device model against schematic'}
        result=phase_a_gates.evaluate(evidence,score,self.freeze)
        self.assertFalse(result['accepted'])
        self.assertFalse(next(g['passed'] for g in result['blocking'] if g['gate']=='G4'))

    def test_numeric_match_without_waveform_review_cannot_pass(self):
        evidence=copy.deepcopy(self.evidence)
        del evidence['waveform_reviews']['14']
        del evidence['waveform_reviews']['1']
        result=phase_a_gates.evaluate(evidence,self.score,self.freeze)
        self.assertFalse(next(g['passed'] for g in result['blocking'] if g['gate']=='G3'))
        self.assertFalse(next(g['passed'] for g in result['blocking'] if g['gate']=='G4'))

    def test_frozen_targets_cannot_replace_measured_calibration(self):
        for change in ({'calibration_measurements':{}},
                       {'calibration_measurements':{'electrical_trace_sha256':'c'*64,
                                                    'eht_v':10500,'horizontal_retrace_us':16}},
                       {'calibration_measurements':{'electrical_trace_sha256':'c'*64,
                                                    'eht_v':11500,'horizontal_retrace_us':21}},
                       {'calibration_measurements':{'electrical_trace_sha256':'0'*64,
                                                    'eht_v':11500,'horizontal_retrace_us':16}},
                       {'grid_geometry':self.evidence['grid_geometry'] | {'source_capture_sha256':'0'*64}}):
            with self.subTest(change=change):
                evidence=copy.deepcopy(self.evidence)
                evidence.update(change)
                result=phase_a_gates.evaluate(evidence,self.score,self.freeze)
                self.assertFalse(next(g['passed'] for g in result['blocking'] if g['gate']=='G3'))
        changed=copy.deepcopy(self.evidence)
        changed['grid_geometry']['picture_width_mm']=215
        result=phase_a_gates.evaluate(changed,self.score,self.freeze)
        self.assertFalse(next(g['passed'] for g in result['blocking'] if g['gate']=='G3'))
        self.assertFalse(next(g['passed'] for g in result['blocking'] if g['gate']=='G5'))
        changed=copy.deepcopy(self.evidence)
        changed['grid_geometry']['electrical_trace_sha256']='0'*64
        result=phase_a_gates.evaluate(changed,self.score,self.freeze)
        self.assertFalse(next(g['passed'] for g in result['blocking'] if g['gate']=='G5'))

    def test_stale_or_duplicate_service_score_is_rejected(self):
        score=copy.deepcopy(self.score)
        score['register_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'current manual register'):
            phase_a_gates.evaluate(self.evidence,score,self.freeze)
        score=copy.deepcopy(self.score)
        score['points'][1]['test_point']=1
        with self.assertRaisesRegex(ValueError,'exactly once'):
            phase_a_gates.evaluate(self.evidence,score,self.freeze)

    def test_saved_score_must_reproduce_from_trace(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'samples.csv'
            path.write_text('time,v(sync_gate)\n0,0\n0.00001,-10\n0.00002,0\n')
            score=service_scoring.score(path)
            self.assertTrue(phase_a_gates.verify_service_score(score))
            score['points'][0]['status']='fail-numeric'
            with self.assertRaisesRegex(ValueError,'differs from the electrical trace'):
                phase_a_gates.verify_service_score(score)


if __name__=='__main__':unittest.main()
