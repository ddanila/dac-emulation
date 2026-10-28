import ast,json,unittest
from pathlib import Path
from postreset_adc_decision_capture import experiment
from postreset_delivery_capture import experiment as previous
HERE=Path(__file__).resolve().parent
class PostresetADCDecision(unittest.TestCase):
    def setUp(self):
        folder=HERE/'reports/postreset-adc/25'
        self.deck=(folder/'io.cir').read_text();self.base=json.loads((folder/'run.json').read_text())
        self.old=next(d['path'] for d in self.base['externalDependencies'] if Path(d['path']).name=='ivlng.vpi')
    def test_only_trace_gate_and_provenance_change(self):
        a=(HERE/'postreset_delivery_capture.py').read_text();b=(HERE/'postreset_adc_decision_capture.py').read_text()
        b=b.replace('Capture full post-reset ADC decisions after exact bounded controls.','Capture the full post-reset delivery audit after exact bounded controls.')
        b=b.replace("'postreset_adc_decision_capture.py','adc_decision_review.py','adc_decision_control_review.py','adc_decision_capture.py'","'postreset_delivery_capture.py'")
        b=b.replace("env=dict(environment);env['ROBOTRON_ADC_TRACE']='1'","env=dict(environment)")
        b=b.replace('from adc_decision_review import assess','from delivery_audit_review import assess')
        b=b.replace('json.loads(json.dumps(reviewed))!=','reviewed!=')
        b=b.replace('its opt-in mode, ADC trace logging, timestep','its opt-in mode, timestep')
        self.assertEqual(ast.dump(ast.parse(a)),ast.dump(ast.parse(b)))
    def test_all_supported_experiments_preserve_timing(self):
        for mode,step in [('off',25),('tick',25),('on',25),('on',12.5),('on',6.25),('retry',25)]:
            with self.subTest(mode=mode,step=step):
                olddeck,oldenv=previous(self.deck,self.base['environment'],self.old,'/tmp/diagnostic/ivlng.vpi',mode,step)
                deck,env=experiment(self.deck,self.base['environment'],self.old,'/tmp/diagnostic/ivlng.vpi',mode,step)
                self.assertEqual(deck,olddeck);self.assertEqual(env,dict(oldenv,ROBOTRON_ADC_TRACE='1'))
    def test_crossing_control_required(self):
        env=dict(self.base['environment']);env.pop('ROBOTRON_ADC_CROSSINGS')
        with self.assertRaisesRegex(ValueError,'unmodified ADC'):experiment(self.deck,env,self.old,'/tmp/diagnostic/ivlng.vpi','on',25)
    def test_unmodified_timing_required(self):
        env=dict(self.base['environment'],ROBOTRON_ABSOLUTE_TICKS='1')
        with self.assertRaisesRegex(ValueError,'unmodified ADC'):experiment(self.deck,env,self.old,'/tmp/diagnostic/ivlng.vpi','on',25)
    def test_full_window_required(self):
        deck=self.deck.replace('.tran 25n 1.16e+06n','.tran 25n 20000n')
        self.assertTrue(deck!=self.deck)
        with self.assertRaises(ValueError):experiment(deck,self.base['environment'],self.old,'/tmp/diagnostic/ivlng.vpi','on',25)
if __name__=='__main__':unittest.main()
