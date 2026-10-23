import math,unittest
from bus_read_replay import validate,at,rk4,derive
class BusReadTests(unittest.TestCase):
 def test_invalid_samples(self):
  for data in ([[0,1],[0,2]],[[0,1],[1,float('nan')]],[[0,1],[1,2,3]],[[0,1]]):
   with self.assertRaises(ValueError):validate(data)
 def test_missing_target(self):
  with self.assertRaises(ValueError):at([[0,1],[1,2]],2)
 def test_independent_rc_solution(self):
  # One high driver charges 1 F through 1 ohm; exact solution is 1-exp(-t).
  data=[[0,0,1,0,5],[1,0,1,0,5]]
  self.assertAlmostEqual(rk4(data,1,[[1,1]],1,.001),1-math.exp(-1),places=11)
 def test_incomplete_circuit(self):
  with self.assertRaises(ValueError):derive('Rbus_numerical1 n_D1 0 1e12')
if __name__=='__main__':unittest.main()
