import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import calibration_contract as contract
import service_score
import transformer_candidates


class CalibrationContractTests(unittest.TestCase):
    def test_labelled_grid_can_enter_connected_calibration_without_freeze(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(['make','build/robotron-signal-pattern'],cwd=ROOT.parents[1],
                           check=True,capture_output=True)
            capture=Path(directory)/'grid.json'
            capture.write_bytes(subprocess.check_output(
                [str(ROOT.parents[1]/'build/robotron-signal-pattern'),'grid','--fields','4']))
            output=Path(directory)/'run'
            with mock.patch.object(contract.steady_supply,'assemble',
                                   side_effect=RuntimeError('reached connected assembly')):
                with self.assertRaisesRegex(RuntimeError,'reached connected assembly'):
                    contract.steady_supply.run(capture,output,Path(directory)/'runtime.json')
            report=json.loads((output/'run.json').read_text())
            self.assertEqual(report['source_kind'],'synthetic-test-pattern')
            self.assertEqual(report['source_pattern'],'grid')
            self.assertNotIn('Calibration freeze required before rendering the native frame.',
                             report['blockers'])

    def test_only_manual_calibration_set_can_be_frozen(self):
        with tempfile.TemporaryDirectory() as directory:
            geometry={'picture_width_mm':210.,'picture_height_mm':145.,
                      'horizontal_linearity':.04,'vertical_linearity':.04,
                      'horizontal_center_mm':0.,'vertical_center_mm':0.,
                      'beam_launch_peak_ua':1.,'beam_launch_emitting_fraction':.05,
                      'beam_launch_marker_fraction':1.,
                      'beam_launch_threshold_ua':.01,
                      'stripe_rows':5,'horizontal_marker_rows':9,'marker_count':54,
                      'method':'source-grid-markers-through-connected-electrodes-yoke-and-central-ray'}
            settling={'format':'dac-steady-supply-settling-v1','complete':True,
                      'accepted':True,'failures':[],
                      'native_sync_lock':{'accepted':True},
                      'waveform_relative_rms_error':{
                          name:.001 for name in contract.SETTLING_PROBES}}
            with (mock.patch.object(contract.grid_geometry,'measure',return_value=geometry),
                  mock.patch.object(contract,'_validate_trim_bindings',return_value=True),
                  mock.patch.object(contract.steady_supply,'assess',return_value=settling)):
                self._check_calibration_fixture(Path(directory),geometry,settling)

    def test_trim_record_must_match_model_and_unbound_controls_block_freeze(self):
        parameters={}
        for profile_name in ('horizontal-oscillator','vertical-output','regulator5'):
            profile=contract.reference.read_profile(ROOT/'profiles'/('k7222-11-'+profile_name+'.json'))
            parameters.update({name:entry['nominal'] for name,entry in profile['parameters'].items()})
        parameters.update({name:values[0] for name,values in contract.steady_supply.signal_path.BOUNDS.items()})
        trims={key:{'setting':parameters[parameter],'procedure_step':'manual'}
               for key,parameter in contract.TRIM_PARAMETERS.items()}
        trims.update({key:{'setting':.5,'procedure_step':'manual'}
                      for key in contract.TRIM_KEYS-set(trims)})
        deck='\n'.join(f'.param {name}={value:.15g}' for name,value in parameters.items())+'\n'
        with self.assertRaisesRegex(ValueError,'manual trims lack connected model binding') as error:
            contract._validate_trim_bindings(trims,parameters,deck)
        self.assertIn('picture_width_r5',str(error.exception))
        self.assertIn('centering_horizontal_r4_0126931',str(error.exception))
        self.assertIn('brightness',str(error.exception))
        trims['horizontal_hold_r24']['setting']=.4
        with self.assertRaisesRegex(ValueError,'manual trim was not applied to connected model: horizontal_hold_r24'):
            contract._validate_trim_bindings(trims,parameters,deck)
        trims['horizontal_hold_r24']['setting']=parameters['horizontal_trim_fraction']
        wrong_deck=deck.replace('.param horizontal_trim_fraction=0.5',
                                '.param horizontal_trim_fraction=0.4')
        with self.assertRaisesRegex(ValueError,'manual trim was not applied to connected deck: horizontal_hold_r24'):
            contract._validate_trim_bindings(trims,parameters,wrong_deck)

    def _check_calibration_fixture(self,directory,geometry,settling):
            subprocess.run(['make','build/robotron-signal-pattern'],cwd=ROOT.parents[1],
                           check=True,capture_output=True)
            capture=Path(directory)/'grid.json'
            capture.write_bytes(subprocess.check_output(
                [str(ROOT.parents[1]/'build/robotron-signal-pattern'),'grid',
                 '--fields','4','--line-characters','108']))
            trial=Path(directory)/'trial';trial.mkdir()
            deck=trial/'run.cir';deck.write_text('* connected grid fixture\n.tran 1u .078\n.end\n')
            deck_hash=hashlib.sha256(deck.read_bytes()).hexdigest()
            selected=contract.steady_supply.select(contract.lab.parse_capture(capture))
            graph=json.loads((ROOT/'reference/k7222-11/t3-winding-hypothesis.json').read_text())
            candidate=transformer_candidates.enumerate_candidates(graph)[0]['id']
            magnetic_path=ROOT/'reference/k7222-11/t3-initial-parameters.json'
            yoke_path=ROOT/'profiles/k7222-11-yoke-geometry.json'
            metadata={'period_s':.0195,'simulated_fields':4,
                      'source_kind':'synthetic-test-pattern',
                      'candidate':{'candidate':{'id':candidate}},
                      'parameters':{'l4_coupling':.5,'horizontal_tank_l':.0015},
                      'experiment':{'source_kind':'synthetic-test-pattern',
                                    'capture_sha256':hashlib.sha256(capture.read_bytes()).hexdigest(),
                                    'source_content_sha256':selected['source_content_sha256'],
                                    'deck_sha256':deck_hash,
                                    'assembly_hashes':{
                                        'reference/k7222-11/t3-initial-parameters.json':hashlib.sha256(magnetic_path.read_bytes()).hexdigest(),
                                        'profiles/yoke.json':hashlib.sha256(yoke_path.read_bytes()).hexdigest()}}}
            (trial/'metadata.json').write_text(json.dumps(metadata))
            (trial/'solve.json').write_text(json.dumps(
                {'status':'complete','deck_sha256':deck_hash,'returncode':0,'timeout':False}))
            names=('time','v(h_feedback)','v(h_drivecol)','v(h_sync)','v(eht)','i(lhorizontal)')
            rows=[(0.,0.,0.,80.,11500.,1.)]
            for i in range(58500,78001):
                t=i*1e-6;phase=t%62.5e-6;on=phase<6e-6
                current=(1.-2*phase/16e-6 if phase<16e-6
                         else -1.+2*(phase-16e-6)/46.5e-6)
                rows.append((t,70. if on else 0.,45. if on else 0.,0. if on else 80.,11500.,current))
            header=('Title: connected grid fixture\nFlags: real\nNo. Variables: 6\n'
                    f'No. Points: {len(rows)}\nVariables:\n'
                    +''.join(f'{i} {name} voltage\n' for i,name in enumerate(names))
                    +'Binary:\n')
            path=trial/'trace.raw'
            path.write_bytes(header.encode()+b''.join(struct.pack('=6d',*row) for row in rows))
            score=service_score.score(path,start=.0585,end=.078,required={14,15,17})
            self.assertEqual(score['required_failures'],[])
            def identified(p):return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            proposal={'format':'dac-monitor-calibration-proposal-v1','source_kind':'synthetic-test-pattern',
                      'source_capture_path':str(capture),
                      'source_capture_sha256':hashlib.sha256(capture.read_bytes()).hexdigest(),
                      'fit_points':[14,15,17],
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
            self.assertEqual(frozen['source_pattern'],'grid')
            self.assertEqual(frozen['calibration_trial']['deck_sha256'],deck_hash)
            self.assertEqual(frozen['calibration_trial']['settling'],settling)
            self.assertAlmostEqual(frozen['calibration_trial']['eht_mean_v'],11500.)
            self.assertAlmostEqual(frozen['calibration_trial']['horizontal_retrace_us'],16.,delta=1.)
            self.assertEqual(frozen['calibration_trial']['grid_geometry'],geometry)
            binding=dict(candidate_id=candidate,
                         parameters={'l4_coupling':.5,'horizontal_tank_l':.0015},
                         magnetic_sha256=proposal['assumptions']['t3_winding_parameters']['sha256'],
                         yoke_sha256=proposal['assumptions']['yoke_profile']['sha256'])
            self.assertTrue(contract.verify_run(frozen,**binding))
            self.assertIn('dark_raster_r28',frozen['trims'])
            self.assertIn('max_beam_r4_0126921',frozen['trims'])
            self.assertIn('centering_horizontal_r4_0126931',frozen['trims'])
            self.assertIn('picture_width_r5',frozen['trims'])
            with mock.patch.object(contract.steady_supply,'assess',return_value={
                    **settling,'accepted':False,'failures':['nonperiodic v(eht)']}):
                with self.assertRaisesRegex(ValueError,'not locked and periodic'):
                    contract.freeze(proposal,score)
            unsteady=json.loads(json.dumps(frozen))
            unsteady['calibration_trial']['settling']['accepted']=False
            unsteady['freeze_sha256']=contract.digest({k:v for k,v in unsteady.items()
                                                      if k!='freeze_sha256'})
            with self.assertRaisesRegex(ValueError,'frozen calibration grid is not locked and periodic'):
                contract.verify(unsteady)
            incomplete=json.loads(json.dumps(proposal))
            del incomplete['trims']['max_beam_r4_0126921']
            with self.assertRaisesRegex(ValueError,'missing or extra recorded trim'):
                contract.freeze(incomplete,score)
            for change in ({'candidate_id':'different'}, {'magnetic_sha256':'0'*64},
                           {'yoke_sha256':'0'*64},
                           {'parameters':{'l4_coupling':.4,'horizontal_tank_l':.0015}},
                           {'parameters':{'l4_coupling':.5,'horizontal_tank_l':.0014}}):
                with self.subTest(change=change),self.assertRaisesRegex(ValueError,'differs from calibration freeze'):
                    contract.verify_run(frozen,**(binding|change))
            proposal['fit_points']=[9,14,15,17]
            with self.assertRaisesRegex(ValueError,'fit points'):
                contract.freeze(proposal,score)
            proposal['fit_points']=[14,15,17]
            metadata['experiment']['capture_sha256']='0'*64
            (trial/'metadata.json').write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError,'selected synthetic capture'):
                contract.freeze(proposal,score)
            metadata['experiment']['capture_sha256']=proposal['source_capture_sha256']
            (trial/'metadata.json').write_text(json.dumps(metadata))
            metadata['candidate']['candidate']['id']='other-t3'
            (trial/'metadata.json').write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError,'different T3 candidate'):
                contract.freeze(proposal,score)
            metadata['candidate']['candidate']['id']=candidate
            metadata['parameters']['horizontal_tank_l']=.0014
            (trial/'metadata.json').write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError,'different horizontal_tank_l'):
                contract.freeze(proposal,score)
            metadata['parameters']['horizontal_tank_l']=.0015
            (trial/'metadata.json').write_text(json.dumps(metadata))
            proposal['targets']['eht_v']=11800
            with self.assertRaisesRegex(ValueError,'differs from connected trace measurement'):
                contract.freeze(proposal,score)
            proposal['targets']['eht_v']=11500
            proposal['targets']['horizontal_retrace_us']=19
            with self.assertRaisesRegex(ValueError,'differs from connected trace measurement'):
                contract.freeze(proposal,score)
            proposal['targets']['horizontal_retrace_us']=16
            proposal['targets']['picture_width_mm']=230
            with self.assertRaisesRegex(ValueError,'differs from connected grid geometry'):
                contract.freeze(proposal,score)
            proposal['targets']['picture_width_mm']=210
            wrong_score=service_score.score(path,start=.0585,end=.077,required={14,15,17})
            with self.assertRaisesRegex(ValueError,'final complete grid field'):
                contract.freeze(proposal,wrong_score)
            other=Path(directory)/'bench.csv'
            other.write_text('time,v(h_feedback),v(h_drivecol),v(h_sync)\n0,0,0,80\n0.000001,70,45,0\n0.000002,0,0,80\n')
            bench_score=service_score.score(other,required={14,15,17})
            with self.assertRaisesRegex(ValueError,'connected trace.raw'):
                contract.freeze(proposal,bench_score)
            proposal['source_capture_sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'capture hash mismatch'):
                contract.freeze(proposal,score)
            proposal['source_capture_sha256']=hashlib.sha256(capture.read_bytes()).hexdigest()
            sparse=Path(directory)/'text.json'
            sparse.write_bytes(subprocess.check_output(
                [str(ROOT.parents[1]/'build/robotron-signal-pattern'),'text']))
            proposal['source_capture_path']=str(sparse)
            proposal['source_capture_sha256']=hashlib.sha256(sparse.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'labelled grid or crosshatch'):
                contract.freeze(proposal,score)
            mistimed=Path(directory)/'mistimed-grid.json'
            mistimed.write_bytes(subprocess.check_output(
                [str(ROOT.parents[1]/'build/robotron-signal-pattern'),'grid',
                 '--fields','4','--line-characters','112']))
            proposal['source_capture_path']=str(mistimed)
            proposal['source_capture_sha256']=hashlib.sha256(mistimed.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'timing differs'):
                contract.freeze(proposal,score)
            inconsistent=json.loads(json.dumps(frozen))
            inconsistent['targets']['horizontal_retrace_us']=19
            inconsistent['freeze_sha256']=contract.digest({k:v for k,v in inconsistent.items()
                                                           if k!='freeze_sha256'})
            with self.assertRaisesRegex(ValueError,'frozen EHT or retrace differs'):
                contract.verify(inconsistent)
            inconsistent=json.loads(json.dumps(frozen))
            inconsistent['targets']['picture_width_mm']=230
            inconsistent['freeze_sha256']=contract.digest({k:v for k,v in inconsistent.items()
                                                           if k!='freeze_sha256'})
            with self.assertRaisesRegex(ValueError,'frozen picture size differs'):
                contract.verify(inconsistent)
            frozen['targets']['eht_v']=12500
            with self.assertRaisesRegex(ValueError,'changed'):
                contract.verify(frozen)


if __name__=='__main__':unittest.main()
