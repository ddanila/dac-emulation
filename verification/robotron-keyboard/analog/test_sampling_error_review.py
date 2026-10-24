import unittest
from decimal import Decimal as D
from sampling_error_review import decompose

class SamplingDecomposition(unittest.TestCase):
 def test_same_endpoint_values_isolate_curve_sampling(self):
  # Coarse chord is 2; the finer curve has a midpoint at 1.
  r=decompose(1.,'2','1',[0.,2.],['0','4'])
  self.assertEqual(D(r['endpointValueContributionVolts']),0)
  self.assertEqual(D(r['referenceCurveSamplingContributionVolts']),1)
  self.assertEqual(D(r['identityResidualVolts']),0)
 def test_signed_cancellation_is_preserved(self):
  r=decompose(1.,'1.5','1',[0.,2.],['0','4'])
  self.assertEqual(D(r['endpointValueContributionVolts']),D('-.5'))
  self.assertEqual(D(r['referenceCurveSamplingContributionVolts']),1)
  self.assertEqual(D(r['signedTotalVolts']),D('.5'))
  self.assertEqual(D(r['identityResidualVolts']),0)
 def test_attribution_depends_on_reference_direction(self):
  forward=decompose(1.,'2','1',[0.,2.],['0','4'])
  reverse=decompose(1.,'1','2',[0.,1.],['0','2'])
  self.assertEqual(D(forward['signedTotalVolts']),-D(reverse['signedTotalVolts']))
  self.assertEqual(D(forward['referenceCurveSamplingContributionVolts']),1)
  self.assertEqual(D(reverse['referenceCurveSamplingContributionVolts']),0)
  self.assertEqual(D(reverse['endpointValueContributionVolts']),-1)
 def test_invalid_bracket(self):
  with self.assertRaises(ValueError):decompose(3.,'0','0',[0.,2.],['0','0'])

if __name__=='__main__':unittest.main()
