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
            names=('time','v(h_feedback)','v(h_drivecol)','v(h_sync)')
            rows=[(0.,0.,0.,80.)]
            for i in range(58500,78001):
                t=i*1e-6;phase=t%62.5e-6;on=phase<6e-6
                rows.append((t,70. if on else 0.,45. if on else 0.,0. if on else 80.))
            header=('Title: connected grid fixture\nFlags: real\nNo. Variables: 4\n'
                    f'No. Points: {len(rows)}\nVariables:\n'
                    +''.join(f'{i} {name} voltage\n' for i,name in enumerate(names))
                    +'Binary:\n')
            path=trial/'trace.raw'
            path.write_bytes(header.encode()+b''.join(struct.pack('=4d',*row) for row in rows))
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
            binding=dict(candidate_id=candidate,
                         parameters={'l4_coupling':.5,'horizontal_tank_l':.0015},
                         magnetic_sha256=proposal['assumptions']['t3_winding_parameters']['sha256'],
                         yoke_sha256=proposal['assumptions']['yoke_profile']['sha256'])
            self.assertTrue(contract.verify_run(frozen,**binding))
            self.assertIn('dark_raster_r28',frozen['trims'])
            self.assertIn('max_beam_r4_0126921',frozen['trims'])
            self.assertIn('centering_horizontal_r4_0126931',frozen['trims'])
            self.assertIn('picture_width_r5',frozen['trims'])
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
            frozen['targets']['eht_v']=12500
            with self.assertRaisesRegex(ValueError,'changed'):
                contract.verify(frozen)


if __name__=='__main__':unittest.main()
