import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import calibration_contract as contract
import inventory_audit
import phase_a_review
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
                                          'circuit_hashes':contract._current_circuit_hashes(),
                                          'settling':{
                                              'format':'dac-steady-supply-settling-v1',
                                              'complete':True,'accepted':True,'failures':[],
                                              'native_sync_lock':{'accepted':True},
                                              'waveform_relative_rms_error':{
                                                  name:.001 for name in contract.SETTLING_PROBES}},
                                          'eht_mean_v':11500,'horizontal_retrace_us':16,
                                          'horizontal_yoke_swing_a':2.,
                                          'retrace_method':'shorter-extrema-arc-of-line-averaged-yoke-current',
                                          'line_count':312,'phase_bins':256,
                                          'grid_geometry':{'picture_width_mm':210.,'picture_height_mm':145.,
                                              'horizontal_linearity':.04,'vertical_linearity':.04,
                                              'horizontal_center_mm':0.,'vertical_center_mm':0.,
                                              'beam_launch_peak_ua':1.,'beam_launch_emitting_fraction':.05,
                                              'beam_launch_marker_fraction':1.,
                                              'beam_launch_threshold_ua':.01,
                                              'stripe_rows':5,'horizontal_marker_rows':9,'marker_count':54,
                                              'method':'source-grid-markers-through-connected-electrodes-yoke-and-central-ray'}},
                     'candidate_id':'t3-test',
                     'assumptions':{key:('t3-test' if key=='t3_candidate' else {}) for key in contract.ASSUMPTION_KEYS},
                     'trims':contract.trim_record_template(),
                     'targets':{'eht_v':11500,'horizontal_retrace_us':16,
                                'picture_width_mm':210,'picture_height_mm':145}}
        for item in self.freeze['trims'].values():
            item.update(setting=.5,observation='Observed on the calibration grid.')
        self.freeze['freeze_sha256']=contract.digest(self.freeze)
        self.score={'format':'dac-monitor-service-score-v1',
                    'input_sha256':'c'*64,
                    'register_sha256':hashlib.sha256(service_scoring.REGISTER.read_bytes()).hexdigest(),
                    'points':[{'test_point':n,'status':'pass-numeric'} for n in range(1,18)]}
        reviews=phase_a_gates.waveform_review_template(self.score)
        for review in reviews['points'].values():
            review.update(shape='agrees',operating_conditions='agrees',
                          notes='Compared the waveform with the manual under the stated conditions.',
                          reviewer='Test reviewer',reviewed_at='2026-11-18')
        self.evidence={'format':'dac-monitor-phase-a-gate-evidence-v1',
                       'electrical_trace_sha256':'c'*64,'native_capture_sha256':'d'*64,
                       'source_review':{
                           'format':'dac-monitor-phase-a-source-review-gate-v1',
                           'passed':True,'inventory_entries':260,
                           'machine_confirmed':260,'human_marked':0,
                           'open_parts':[],'open_schematics':[],
                           'source_pdf_sha256':phase_a_review.source_hash(),
                           'inventory_sha256':hashlib.sha256(
                               inventory_audit.INVENTORY.read_bytes()).hexdigest(),
                           'kicad_tree_sha256':phase_a_review.kicad_tree_hash(),
                           'ocr_audit_sha256':'0'*64,'marks_sha256':'1'*64},
                       'waveform_reviews':reviews,
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
                       'optical_refinement':{'integration_verified':True,'spatial_verified':True,
                                             'relative_error':.01},
                       'readability':{'source_kind':'native-firmware-logical-timing-reference',
                                      'logical_capture_sha256':'d'*64,
                                      'one_global_affine_fit':True,'fit_applied_to_render':False,
                                      'correlation':.8}}

    def test_all_eight_gates_are_blocking(self):
        result=phase_a_gates.evaluate(self.evidence,self.score,self.freeze)
        self.assertTrue(result['accepted'])
        self.assertTrue(result['prerequisite_a1']['passed'])
        self.assertEqual([g['gate'] for g in result['blocking']],
                         ['G1','G1b','G2','G3','G4','G5','G6','G7','G8'])
        evidence=copy.deepcopy(self.evidence)
        evidence['horizontal_lock']['maximum_adjacent_jitter_s']=40e-9
        evidence['signed_energy_ledger']={'status':'pass'}
        result=phase_a_gates.evaluate(evidence,self.score,self.freeze)
        self.assertFalse(result['accepted'])
        self.assertFalse(next(g['passed'] for g in result['blocking'] if g['gate']=='G1b'))
        evidence=copy.deepcopy(self.evidence)
        evidence['optical_refinement']['spatial_verified']=False
        result=phase_a_gates.evaluate(evidence,self.score,self.freeze)
        self.assertFalse(next(g['passed'] for g in result['blocking'] if g['gate']=='G7'))

    def test_a1_review_is_required_even_if_g1_through_g8_pass(self):
        for change in ({'passed':False,'open_parts':['012-6931:R4']},
                       {'kicad_tree_sha256':'0'*64},
                       {'machine_confirmed':259}):
            with self.subTest(change=change):
                evidence=copy.deepcopy(self.evidence)
                evidence['source_review'].update(change)
                result=phase_a_gates.evaluate(evidence,self.score,self.freeze)
                self.assertFalse(result['accepted'])
                self.assertFalse(result['prerequisite_a1']['passed'])
                self.assertTrue(all(g['passed'] for g in result['blocking']))
        evidence=copy.deepcopy(self.evidence)
        del evidence['source_review']
        self.assertFalse(phase_a_gates.evaluate(evidence,self.score,self.freeze)['accepted'])

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
        del evidence['waveform_reviews']['points']['14']
        del evidence['waveform_reviews']['points']['1']
        result=phase_a_gates.evaluate(evidence,self.score,self.freeze)
        self.assertFalse(next(g['passed'] for g in result['blocking'] if g['gate']=='G3'))
        self.assertFalse(next(g['passed'] for g in result['blocking'] if g['gate']=='G4'))

    def test_waveform_review_is_bound_to_exact_trace_register_and_score_window(self):
        for key,value in (('electrical_trace_sha256','0'*64),
                          ('register_sha256','0'*64),
                          ('service_score_sha256','0'*64)):
            with self.subTest(key=key):
                evidence=copy.deepcopy(self.evidence)
                evidence['waveform_reviews'][key]=value
                result=phase_a_gates.evaluate(evidence,self.score,self.freeze)
                self.assertFalse(next(g['passed'] for g in result['blocking'] if g['gate']=='G3'))
                self.assertFalse(next(g['passed'] for g in result['blocking'] if g['gate']=='G4'))
        evidence=copy.deepcopy(self.evidence)
        evidence['waveform_reviews']['points']['14']['reviewed_at']='2026-99-99'
        self.assertFalse(next(g['passed'] for g in phase_a_gates.evaluate(
            evidence,self.score,self.freeze)['blocking'] if g['gate']=='G3'))

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

    def test_g3_electrical_measurements_must_reproduce_from_native_trace(self):
        with tempfile.TemporaryDirectory() as temp:
            trace=Path(temp)/'trace.raw';trace.write_bytes(b'fixture')
            score=self.score|{'input':str(trace),'requested_window_s':[.0585,.078]}
            actual={'eht_mean_v':11500.,'horizontal_retrace_us':16.}
            with mock.patch.object(phase_a_gates.calibration_measurements,'measure',return_value=actual) as measure:
                self.assertTrue(phase_a_gates.verify_calibration_measurements(self.evidence,score))
                measure.assert_called_once_with(trace,start_s=.0585,end_s=.078,line_s=62.5e-6)
                changed=copy.deepcopy(self.evidence)
                changed['calibration_measurements']['eht_v']=11700
                with self.assertRaisesRegex(ValueError,'differ from the electrical trace'):
                    phase_a_gates.verify_calibration_measurements(changed,score)
                changed['calibration_measurements']['electrical_trace_sha256']='0'*64
                with self.assertRaisesRegex(ValueError,'different electrical trace'):
                    phase_a_gates.verify_calibration_measurements(changed,score)

    def test_native_frame_trace_must_use_archived_full_text_capture(self):
        manifest=json.loads((phase_a_gates.NATIVE_ARCHIVE/'manifest.json').read_text())
        with tempfile.TemporaryDirectory() as temp:
            trace=Path(temp)/'trace.raw';trace.write_bytes(b'fixture')
            metadata_path=trace.with_name('metadata.json')
            names={name for name,_,_ in phase_a_gates.steady_supply.assembly_sheets()}
            self.assertEqual(len(names),10)
            archived={'circuits/'+name:hashlib.sha256(
                (ROOT/'circuits'/name).read_bytes()).hexdigest() for name in names}
            experiment={'capture_sha256':manifest['capture_sha256'],
                        'source_content_sha256':manifest['source_content_sha256'],
                        'source_kind':'schematic-derived-logical',
                        'assembly_hashes':archived}
            metadata_path.write_text(json.dumps({'experiment':experiment}))
            score=self.score|{'input':str(trace)}
            evidence=self.evidence|{'native_capture_sha256':manifest['capture_sha256']}
            self.assertTrue(phase_a_gates.verify_native_capture(evidence,score))
            changed=evidence|{'native_capture_sha256':'0'*64}
            with self.assertRaisesRegex(ValueError,'capture or logical reference mismatch'):
                phase_a_gates.verify_native_capture(changed,score)
            experiment['assembly_hashes']=archived|{
                'circuits/k7222-11-horizontal-output.kicad_sch':'0'*64}
            metadata_path.write_text(json.dumps({'experiment':experiment}))
            with self.assertRaisesRegex(ValueError,'stale or missing assembled schematic'):
                phase_a_gates.verify_native_capture(evidence,score)
            experiment['assembly_hashes']=archived
            experiment['source_content_sha256']='0'*64
            metadata_path.write_text(json.dumps({'experiment':experiment}))
            with self.assertRaisesRegex(ValueError,'different native source'):
                phase_a_gates.verify_native_capture(evidence,score)

    def test_final_trace_overrides_claimed_lock_and_periodicity(self):
        evidence=copy.deepcopy(self.evidence)
        evidence.pop('horizontal_lock')
        evidence.pop('periodicity')
        lock=copy.deepcopy(self.evidence['horizontal_lock'])
        lock['maximum_adjacent_jitter_s']=50e-9
        actual={'complete':True,'native_sync_lock':lock,
                'waveform_relative_rms_error':{probe:.005 for probe in phase_a_gates.PERIODIC_PROBES.values()}}
        with mock.patch.object(phase_a_gates.steady_supply,'assess',return_value=actual):
            phase_a_gates.verify_settling_evidence(evidence,{'input':'trace.raw'},'selection','metadata')
            self.assertEqual(evidence['horizontal_lock']['maximum_adjacent_jitter_s'],50e-9)
            self.assertFalse(next(g['passed'] for g in phase_a_gates.evaluate(evidence,self.score,self.freeze)['blocking']
                                  if g['gate']=='G1b'))
            claimed=copy.deepcopy(evidence)
            claimed['periodicity']['relative_errors']['eht']=0.
            with self.assertRaisesRegex(ValueError,'reported periodicity differs'):
                phase_a_gates.verify_settling_evidence(claimed,{'input':'trace.raw'},'selection','metadata')

    def test_g6_requires_independent_unchanged_circuit_trials(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            base=root/'base'/'trace.raw';base.parent.mkdir();base.write_bytes(b'base')
            base_meta={'period_s':.0195,'simulated_fields':4,'source_kind':'schematic-derived-logical',
                       'candidate':{'id':'t3-test'},'parameters':{'yoke_horizontal_l':.004},
                       'yoke':{'profile':'test'},'max_step_s':100e-9,'initial_voltage_guesses':{},
                       'experiment':{'capture_sha256':'a'*64,'source_content_sha256':'b'*64,
                                     'assembly_hashes':{'sheet':'c'*64}}}
            def variant(name,step,initial):
                path=root/name/'trace.raw';path.parent.mkdir();path.write_bytes(name.encode())
                metadata=copy.deepcopy(base_meta)
                metadata['max_step_s']=step;metadata['initial_voltage_guesses']=initial
                deck=b'completed test deck';(path.parent/'run.cir').write_bytes(deck)
                sha=hashlib.sha256(deck).hexdigest()
                metadata['experiment']['deck_sha256']=sha
                (path.parent/'metadata.json').write_text(json.dumps(metadata))
                (path.parent/'solve.json').write_text(json.dumps({'status':'complete','deck_sha256':sha}))
                return path,metadata
            half,_=variant('half',50e-9,{})
            second,second_meta=variant('second',100e-9,{'h_hot':100.})
            evidence={'electrical_refinement':{'half_timestep_trace':str(half),
                                               'second_initialization_trace':str(second)}}
            score={'input':str(base)}
            comparison={'relative_rms_error':{name:.005 for name in phase_a_gates.steady_acceptance.NAMES}}
            with mock.patch.object(phase_a_gates.steady_acceptance,'compare',return_value=comparison) as compare:
                phase_a_gates.verify_electrical_refinement(evidence,score,base_meta)
                self.assertEqual(compare.call_count,2)
                self.assertEqual(evidence['electrical_refinement']['half_timestep_relative_error'],.005)
                second_meta['initial_voltage_guesses']={}
                (second.parent/'metadata.json').write_text(json.dumps(second_meta))
                with self.assertRaisesRegex(ValueError,'repeats the same initialization'):
                    phase_a_gates.verify_electrical_refinement(evidence,score,base_meta)
                second_meta['initial_voltage_guesses']={'h_hot':100.}
                second_meta['parameters']['yoke_horizontal_l']=.008
                (second.parent/'metadata.json').write_text(json.dumps(second_meta))
                with self.assertRaisesRegex(ValueError,'changes the source or circuit'):
                    phase_a_gates.verify_electrical_refinement(evidence,score,base_meta)

    def test_g7_requires_optical_input_from_scored_electrical_field(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            directories={name:root/name for name in ('base','fine','spatial')}
            for path in directories.values():path.mkdir()
            field=b'time,anode\n0,11000\n.0195,11000\n'
            field_sha=hashlib.sha256(field).hexdigest()
            (directories['base']/'frame.json').write_text(json.dumps({'hashes':{'input.csv':field_sha}}))
            evidence={'optical_refinement':{'base_archive':str(directories['base']),
                                            'integration_archive':str(directories['fine']),
                                            'spatial_archive':str(directories['spatial'])}}
            score={'input':'base/trace.raw','input_sha256':'a'*64}
            metadata={'period_s':.0195,'simulated_fields':4}
            def export(_source,output,**_kwargs):
                output.write_bytes(field)
                return {'raw_sha256':score['input_sha256'],'trace_sha256':field_sha}
            comparisons=[{'scope':'optical-integration-refinement','accepted':True,'relative_l2_error':.01},
                         {'scope':'spatial-refinement','accepted':True,'relative_l2_error':.015}]
            with mock.patch.object(phase_a_gates.steady_trace,'export',side_effect=export), \
                 mock.patch.object(phase_a_gates.periodic_frame,'compare',side_effect=comparisons) as compare:
                phase_a_gates.verify_optical_refinement(evidence,score,metadata)
                self.assertEqual(compare.call_count,2)
                self.assertEqual(evidence['optical_refinement']['relative_error'],.015)
            (directories['base']/'frame.json').write_text(json.dumps({'hashes':{'input.csv':'0'*64}}))
            with mock.patch.object(phase_a_gates.steady_trace,'export',side_effect=export):
                with self.assertRaisesRegex(ValueError,'optical input differs'):
                    phase_a_gates.verify_optical_refinement(evidence,score,metadata)

    def test_g8_recomputes_claimed_correlation(self):
        evidence=copy.deepcopy(self.evidence)
        evidence['optical_refinement']['base_archive']='render/archive'
        computed={'source_kind':'native-firmware-logical-timing-reference',
                  'source_content_sha256':'e'*64,'one_global_affine_fit':True,
                  'fit_applied_to_render':False,'correlation':.64}
        with mock.patch.object(phase_a_gates.readability_score,'score',return_value=computed):
            with self.assertRaisesRegex(ValueError,'reported G8 readability differs'):
                phase_a_gates.verify_readability(evidence,'selection')
            evidence['readability'].pop('correlation')
            phase_a_gates.verify_readability(evidence,'selection')
            self.assertFalse(next(g['passed'] for g in phase_a_gates.evaluate(evidence,self.score,self.freeze)['blocking']
                                  if g['gate']=='G8'))


if __name__=='__main__':unittest.main()
