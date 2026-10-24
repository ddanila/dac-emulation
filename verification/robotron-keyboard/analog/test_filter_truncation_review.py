import copy
import json
import unittest
from pathlib import Path
from filter_truncation_review import analyze, validate_run

HERE = Path(__file__).resolve().parent


class FilterReviewTests(unittest.TestCase):
    def record(self, floor=2., time=138.25e-6):
        fields = {'time':time, 'state':10, 'delta':1., 'dt0':1., 'dt1':2., 'dt2':3., 'order':2,
                  'before':1., 'proposed':.5, 'currenttol':1e-6, 'chargetol':1e-5, 'abstol':1e-15,
                  'reltol':1e-8, 'chgtol':floor, 'difference':1., 'q0':0., 'q1':-1., 'q2':-27., 'q3':-216.}
        return 'FILTER_TRUNC error '+' '.join(k+'='+(str(v) if k in ('state','order') else float(v).hex()) for k,v in fields.items())

    def test_arithmetic_identity_device_mapping_and_charge_floor(self):
        log = '\n'.join((self.record(), self.record(.5),
            'FILTER_TRUNC instance time='+float(138.25e-6).hex()+' name=q_clock state=10 before=0x1p+0 proposed=0x1p-1'))
        result = analyze(log)
        state = result['states']['10']
        self.assertTrue(result['binary64ReplayExact'])
        self.assertEqual(state['instance'], 'q_clock')
        self.assertEqual(state['chargeFloorActive'], 1)
        self.assertEqual(state['storedChargeAboveFloor'], 1)
        self.assertEqual(float(state['maximumRelativeArithmeticError']), 0)
        self.assertEqual(state['chargeToleranceDominant'], 2)

    def test_rejects_wrong_window_malformed_and_empty_logs(self):
        for log in ('', self.record(time=1e-6), self.record()+' warning', 'FILTER_TRUNC instance broken'):
            with self.assertRaises(ValueError): analyze(log)

    def test_only_runtime_and_audit_flag_may_change(self):
        base=json.loads((HERE/'reports/dense-anchored-refinement/25/run.json').read_text())
        run=copy.deepcopy(base)
        run.update(filterTruncAudit=False, generatorSha256='new', elapsedSeconds=123.)
        run['runtime']['executable']['sha256']='instrumented'
        validate_run(run,base,'disabled','instrumented')
        run['filterTruncAudit']=True
        validate_run(run,base,'enabled','instrumented')
        for field,value in [('stopNs',2000),('haltNs',2000),('stepNs',12.5),('toleranceScale',.1),
                            ('solverDiagnostic','failure'),('timedOut',True),('filterTruncAudit',False)]:
            bad=copy.deepcopy(run);bad[field]=value
            with self.assertRaises(ValueError):validate_run(bad,base,'enabled','instrumented')
        bad=copy.deepcopy(run);bad['runtime']['spinit']['sha256']='changed'
        with self.assertRaises(ValueError):validate_run(bad,base,'enabled','instrumented')


if __name__ == '__main__':
    unittest.main()
