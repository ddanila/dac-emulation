import copy
from fractions import Fraction as F
import unittest

from capacitor_stamp_review import corrections, parse


class CapacitorStampTests(unittest.TestCase):
    def group(self, order=1):
        b = dict(name='c1', p=1, n=2, m=2., C=.5, ag0=4., ag1=-4. if order==1 else 1.,
                 q0=0., q1=3., i1=2., geq=2., ceq=-12. if order==1 else -14.,
                 pp=0., nn=0., pn=0., np=0., bp=0., bn=0.)
        a = dict(pp=4., nn=4., pn=-4., np=-4., bp=-2*b['ceq'], bn=2*b['ceq'])
        return dict(order=order, capacitors=[dict(before=b, after=a)])

    def test_charge_history_rhs_signs_and_multiplicity(self):
        for order in (1,2):
            a,b,_ = corrections(self.group(order))
            self.assertTrue(all(v == 0 for v in (*a.values(), *b.values())))

    def test_small_conductance_lost_in_large_addition_is_restored(self):
        group = self.group()
        before = group['capacitors'][0]['before']
        before.update(m=1., C=1., ag0=1e16, geq=1e16, q1=0., ceq=0., pp=1., nn=1.)
        group['capacitors'][0]['after'].update(pp=1e16, nn=1e16, pn=-1e16, np=-1e16, bp=0., bn=0.)
        a,_,details = corrections(group)
        self.assertEqual(a[1,1], F(1))
        self.assertEqual(a[2,2], F(1))
        self.assertEqual(details[0]['maximumAdditionDiscrepancySiemens'], 1)

    def test_ground_aliases_are_excluded(self):
        group = self.group()
        group['capacitors'][0]['before']['n'] = 0
        group['capacitors'][0]['after'].update(nn=123., pn=234., np=345., bn=456.)
        a,b,_ = corrections(group)
        self.assertEqual(a, {(1,1):F(0)})
        self.assertEqual(b, {1:F(0)})

    def test_invalid_and_duplicate_devices_rejected(self):
        for change in ({'p':2}, {'C':float('nan')}, {'m':0}):
            group = self.group()
            group['capacitors'][0]['before'].update(change)
            with self.assertRaises(ValueError): corrections(group)
        group = self.group()
        group['capacitors'].append(copy.deepcopy(group['capacitors'][0]))
        with self.assertRaises(ValueError): corrections(group)

    def test_log_pairing_and_trial_identity(self):
        text = '''CAP_AUDIT begin time=0x1p+0 delta=0x1p-1 order=1 mode=0
CAP_AUDIT before name=c1 p=1 n=0
CAP_AUDIT after name=c1 pp=0x1p+0
CAP_AUDIT end
LINEAR_AUDIT begin id=7 time=0x1p+0 delta=0x1p-1 order=1
'''
        self.assertEqual(parse(text)[7]['capacitors'][0]['before']['name'], 'c1')
        for bad in [text.replace('after name=c1', 'after name=c2'),
                    text.replace('CAP_AUDIT end\n', ''),
                    text.replace('id=7 time=0x1p+0', 'id=7 time=0x1p+1')]:
            with self.assertRaises(ValueError): parse(bad)


if __name__ == '__main__':
    unittest.main()
