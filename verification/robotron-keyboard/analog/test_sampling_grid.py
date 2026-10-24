import unittest
from sampling_grid import add_sampling_grid

class SamplingTests(unittest.TestCase):
 def test_zero_source_preserves_circuit(self):
  deck='Vfixture_clock fixture_clock 0 PULSE(0 5 500n 1n 1n 499n 1u)\n'
  result=add_sampling_grid(deck,[1e-8,1e-6],2000)
  self.assertTrue(result.endswith(deck))
  self.assertIn('Vsampling_grid sampling_grid 0 PWL(0 0',result)
  self.assertIn('+ 1e-08 0',result)
  with self.assertRaises(ValueError):add_sampling_grid(result,[1e-8],2000)
 def test_reject_invalid_times(self):
  for times in ([],[0],[2e-6],[float('nan')],[True],[1e-7,1e-8],[1e-8,1e-8]):
   with self.assertRaises(ValueError):add_sampling_grid('Vfixture_clock x 0 0',times,2000)
  with self.assertRaises(ValueError):add_sampling_grid('Vfixture_clock x 0 0',[1e-8],None)

if __name__=='__main__':unittest.main()
