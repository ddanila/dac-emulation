import ast,copy,json,unittest,tempfile
from pathlib import Path
from gate_recovery_gate import require,FAULTS
from arithmetic_board_budget_review import budgets
HERE=Path(__file__).resolve().parent

class GateRecoveryTests(unittest.TestCase):
    def valid(self):
        r=json.loads((HERE/'reports/net-board/assessment.json').read_text())
        n=r['observedState']['boundaries'];r['observedState'].update(wireObservations=n,wireKinds=[4,8],maximumWireFilters=1573,signalObservations=n,maximumSignalFunctors=196,muxObservations=n,maximumMuxFunctors=251,gateObservations=n,maximumGateFunctors=100)
        r['negativeControls']={name:dict(fault=dict(index=0 if name=='gate-input0-corrupt' else 37918,phase='before-step',targetSeconds=0 if name=='gate-input0-corrupt' else 5e-6)) for name in FAULTS}
        r['captureLogBudgets']={name:dict(bytes=100,compressedBytes=10,logicalLimitBytes=24*1024**3,compressedLimitBytes=256*1024**2) for name in FAULTS|{'off','observe'}}
        return r
    def test_gate_and_missing_full_evidence(self):
        require(self.valid())
        mutations=[lambda r:r.update(controlsPassed=False),lambda r:r.update(reviewCompleted=False),lambda r:r.update(firmwareRecordsExactlyEqual=False),lambda r:r['comparisons']['enabledObserver'].update(allSamplesExactlyEqual=False),lambda r:r['comparisons']['disabledBaseline'].update(samples=1),lambda r:r['comparisons']['enabledObserver']['signals'].pop(),lambda r:r['observedState'].update(wireObservations=1),lambda r:r['observedState'].update(wireKinds=[4]),lambda r:r['observedState'].update(signalObservations=1),lambda r:r['observedState'].update(maximumSignalFunctors=0),lambda r:r['observedState'].update(muxObservations=1),lambda r:r['observedState'].update(maximumMuxFunctors=0),lambda r:r['observedState'].update(gateObservations=1),lambda r:r['observedState'].update(maximumGateFunctors=0),lambda r:r['negativeControls'].pop('gate-input1-corrupt'),lambda r:r['negativeControls']['gate-invert-corrupt']['fault'].update(targetSeconds=0),lambda r:r['negativeControls']['gate-input0-corrupt']['fault'].update(index=2),lambda r:r['captureLogBudgets']['observe'].update(bytes=25*1024**3)]
        for mutate in mutations:
            r=self.valid();mutate(r)
            with self.assertRaises(ValueError):require(r)
    def test_actual_incomplete_failure_and_prior_layer_cannot_pass(self):
        for name in ('wire-budget-failure','net-board'):
            with self.assertRaises(ValueError):require(json.loads((HERE/'reports'/name/'assessment.json').read_text()))
    def test_capture_only_adds_gate_and_resource_limit(self):
        s=(HERE/'arithmetic_board_budget_capture.py').read_text().replace('\nfrom gate_recovery_gate import require','').replace('require(prior);','').replace('logical_limit=28*1024**3','logical_limit=4*1024**3')
        self.assertEqual(ast.dump(ast.parse(s)),ast.dump(ast.parse((HERE/'arithmetic_board_capture.py').read_text())))

    def test_arithmetic_budget_receipts_remain_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);r=dict(completed=True,captureTimeoutSeconds=3300,log=dict(bytes=100,compressedBytes=4,logicalLimitBytes=28*1024**3,compressedLimitBytes=256*1024**2))
            for mode in ('off','observe','arithmetic-input0-corrupt','arithmetic-input1-corrupt','arithmetic-fallback-corrupt','arithmetic-width-corrupt'):
                folder=root/mode;folder.mkdir();(folder/'ngspice.log.xz').write_bytes(b'test');(folder/'run.json').write_text(json.dumps(r))
            self.assertEqual(len(budgets(root)),6)
            for mutate in (lambda d:d.update(completed=False),lambda d:d.update(captureTimeoutSeconds=4000),lambda d:d['log'].update(bytes=29*1024**3),lambda d:d['log'].update(compressedBytes=3),lambda d:d['log'].update(logicalLimitBytes=32*1024**3)):
                bad=copy.deepcopy(r);mutate(bad);(root/'observe/run.json').write_text(json.dumps(bad))
                with self.assertRaises(ValueError):budgets(root)

if __name__=='__main__':unittest.main()
