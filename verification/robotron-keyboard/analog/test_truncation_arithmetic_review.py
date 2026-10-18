import math
import unittest
from fractions import Fraction as F
from truncation_arithmetic_review import divided_difference, review_record


class TruncationArithmeticTests(unittest.TestCase):
    def test_nonuniform_quadratic_and_cubic_history(self):
        # Times 0, -1, -3, -6; divided differences of t^n are exactly one.
        self.assertEqual(divided_difference([F(0), F(1), F(9)], [F(1), F(2)]), 1)
        self.assertEqual(divided_difference([F(0), F(-1), F(-27), F(-216)],
                                            [F(1), F(2), F(3)]), 1)

    def test_offset_does_not_destroy_exact_small_difference(self):
        offset = F(2**60)
        self.assertEqual(divided_difference([offset, offset+1, offset+9], [F(1), F(2)]), 1)
        with self.assertRaises(ValueError):
            divided_difference([F(0), F(1)], [F(0)])

    def test_second_order_proposal_uses_square_root(self):
        expected = math.sqrt(1/.08333333333)
        r = {k:float(v).hex() for k,v in {'time':1,'delta':1,'dt0':1,'dt1':2,'dt2':3,
             'q0':0,'q1':-1,'q2':-27,'q3':-216,'tol':1,'difference':1,'proposed':expected}.items()}
        r.update(order='2', state='0')
        self.assertAlmostEqual(review_record(r, 1e-13, 1)['exactHistoryProposalSeconds'], expected)
        r['difference'] = float(2).hex()
        with self.assertRaisesRegex(ValueError, 'Logged proposal'):
            review_record(r, 1e-13, 1)

    def test_logged_proposal_must_match(self):
        r = {k:float(v).hex() for k,v in {'time':1,'delta':1,'dt0':1,'dt1':2,
             'q0':0,'q1':1,'q2':9,'tol':1,'difference':1,'proposed':2}.items()}
        r.update(order='1', state='0')
        self.assertEqual(review_record(r, 1e-13, 1)['exactHistoryProposalSeconds'], 2)
        r['proposed'] = float(3).hex()
        with self.assertRaisesRegex(ValueError, 'Logged proposal'):
            review_record(r, 1e-13, 1)
