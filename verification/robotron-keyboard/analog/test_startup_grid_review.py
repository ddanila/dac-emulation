import unittest
from startup_grid_review import prefix
class PrefixTests(unittest.TestCase):
 def test_shared_endpoint_preserves_interior_samples(self):
  self.assertEqual(list(prefix([(0.,0.,2.),(1.,2.,4.),(3.,6.,8.)],2.)),[(0.,0.,2.),(1.,2.,4.),(2.,4.,6.)])
 def test_native_endpoint_is_retained(self):
  self.assertEqual(list(prefix([(0.,0.),(1.,3.),(2.,4.)],1.)),[(0.,0.),(1.,3.)])
 def test_incomplete_or_missing_origin_rejected(self):
  for samples in ([(0.,0.),(1.,3.)],[(1.,3.),(3.,5.)],[]):
   with self.assertRaises(ValueError):list(prefix(samples,2.))
if __name__=='__main__':unittest.main()
