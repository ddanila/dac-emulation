from fractions import Fraction as F
import unittest
from capacitor_onset_review import final_systems, compare


class TrialLinkTests(unittest.TestCase):
    def fixture(self):
        system = {'id': 1, 'metadata': {'time':'0x1p+0', 'delta':'0x1p-2', 'order':'1'},
                  'names': {0:'ground', 1:'signal'}, 'x': {1:F(2)}}
        log = ('LINEAR_AUDIT end id=1\n'
               'TRUNC_AUDIT solver time=0x1p+0 delta=0x1p-2 order=1 result=0\n'
               'NODE_AUDIT time=0x1p+0 delta=0x1p-2 result=0 name=signal rhs=0x1p+1 oldrhs=0x1p+0\n')
        return system, log

    def test_final_solve_matches_rhs_not_previous_iteration(self):
        s, log = self.fixture()
        self.assertEqual(final_systems(log, [s]), [s])
        with self.assertRaises(ValueError): final_systems(log.replace('rhs=0x1p+1','rhs=0x1p+0'), [s])

    def test_missing_stale_or_mismatched_solve_rejected(self):
        s, log = self.fixture()
        for bad in [log.split('\n',1)[1], log.replace('delta=0x1p-2','delta=0x1p-3'),
                    log.replace('result=0','result=1',1),log+'LINEAR_AUDIT end id=1\n']:
            with self.assertRaises(ValueError): final_systems(bad, [s])

    def test_nonconverged_trials_remain_available_for_diagnosis(self):
        s, log = self.fixture()
        self.assertEqual(final_systems(log.replace('result=0','result=1'), [s]), [s])

    def test_frozen_correction_preserves_small_lost_conductance(self):
        system = {'id':1, 'metadata':{'size':'2'},
                  'a':{(1,1):F(10**16), (2,2):F(1)}, 'b':{1:F(10**16), 2:F(0)},
                  'names':{1:'n_cable_daten', 2:'host_receiver_gnd'}}
        before = dict(name='c1', p=1, n=0, m=1., C=1., ag0=1e16, ag1=-1e16,
                      q1=0., i1=0., geq=1e16, pp=1., nn=0., pn=0., np=0., bp=0., bn=0.)
        after = dict(pp=1e16, nn=1e16, pn=-1e16, np=-1e16, bp=0., bn=0.)
        result = compare(system, {'order':1, 'capacitors':[{'before':before,'after':after}]})
        expected = float(-F(1, 10**16+1))
        self.assertAlmostEqual(result['frozenCableDataChangeV'], expected, delta=1e-30)
        self.assertLess(result['corrected80Vs160Scaled'], 1e-60)

    def test_retried_timestamp_preserves_execution_order(self):
        s, log = self.fixture()
        second = dict(s, id=2)
        self.assertEqual([x['id'] for x in final_systems(log+log.replace('id=1','id=2'),[s,second])],[1,2])

if __name__ == '__main__': unittest.main()
