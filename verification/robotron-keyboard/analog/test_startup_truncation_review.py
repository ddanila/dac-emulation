import unittest
from decimal import Decimal
from startup_truncation_review import difference, analyze

class DifferenceTests(unittest.TestCase):
    def test_kernel_recurrence_on_unequal_history_steps(self):
        # Backward-time knots 0, -1, -3, -6 have a unit cubic divided difference.
        self.assertEqual(difference([0.,-1.,-27.,-216.],[1.,2.,3.],2),1.)
        self.assertEqual(difference([0.,-1.,-27.,-216.],[1.,2.,3.],2,True),Decimal(1))
        self.assertEqual(difference([0.,1.,9.],[1.,2.],1),1.)
    def test_invalid_histories_and_empty_audit_rejected(self):
        for values,deltas,order in [([0.,1.],[1.],2),([0.,1.,2.],[0.,1.],1),([0.,1.,float('nan')],[1.,1.],1)]:
            with self.assertRaises(ValueError):difference(values,deltas,order)
        with self.assertRaises(ValueError):analyze('no audit')

if __name__=='__main__':unittest.main()
