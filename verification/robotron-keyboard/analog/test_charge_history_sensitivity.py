import itertools
import unittest
from fractions import Fraction as F
from charge_history_sensitivity import exact_difference, sensitivity, step_policy_screen


class HistorySensitivityTests(unittest.TestCase):
    def test_unequal_step_cubic_and_quadratic(self):
        self.assertEqual(exact_difference(list(map(F,(0,-1,-27,-216))),list(map(F,(1,2,3))),2),1)
        self.assertEqual(exact_difference(list(map(F,(0,1,9))),list(map(F,(1,2))),1),1)

    def test_exact_box_radius_matches_all_corner_perturbations(self):
        for values,deltas,order in (([0.,-1.,-27.,-216.],[1.,2.,3.],2),([1.,1.,1.],[1.,2.],1)):
            result=sensitivity(values,deltas,order);q=list(map(F.from_float,values));dt=list(map(F.from_float,deltas))
            offsets=[]
            for signs in itertools.product((-1,1),repeat=len(values)):
                shifted=[v+sign*u for v,sign,u in zip(q,signs,result['halfUlps'])]
                offsets.append(exact_difference(shifted,dt,order)-result['difference'])
            self.assertEqual(max(offsets),result['radius']);self.assertEqual(min(offsets),-result['radius'])
        self.assertIsNone(result['relativeRadius']);self.assertTrue(result['intervalIncludesZero'])

    def test_step_policy_thresholds_do_not_claim_final_decisions(self):
        self.assertEqual(step_policy_screen(1.,2.),{'belowGrowthCap':False,'atOrBelowRejectionThreshold':False})
        self.assertEqual(step_policy_screen(1.,1.),{'belowGrowthCap':True,'atOrBelowRejectionThreshold':False})
        self.assertEqual(step_policy_screen(1.,.9),{'belowGrowthCap':True,'atOrBelowRejectionThreshold':True})
        for delta,proposal in ((0.,1.),(1.,float('nan')),(1.,-1.)):
            with self.assertRaises(ValueError):step_policy_screen(delta,proposal)

    def test_rejects_invalid_histories(self):
        for q,dt,order in (([0.,1.],[1.],2),([0.,1.,2.],[0.,1.],1),([0.,float('nan'),2.],[1.,1.],1)):
            with self.assertRaises(ValueError):sensitivity(q,dt,order)


if __name__=='__main__':unittest.main()
