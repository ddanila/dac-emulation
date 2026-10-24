import unittest
from tolerance_controls_review import normalized

class ToleranceEvidence(unittest.TestCase):
 def test_normalization_preserves_physical_and_other_solver_changes(self):
  a='.options reltol=1e-6 vntol=1e-9 abstol=1e-15\nR1 a 0 100\n'
  limits={'reltol':1e-6,'vntol':1e-9,'abstol':1e-15}
  b=a.replace('reltol=1e-6','reltol=1e-7')
  self.assertEqual(normalized(a,limits),normalized(b,{**limits,'reltol':1e-7}))
  self.assertNotEqual(normalized(a,limits),normalized(a.replace('100','200'),limits))
  self.assertNotEqual(normalized(a,limits),normalized(a+'.options method=gear\n',limits))
 def test_wrong_or_duplicate_tolerance_is_rejected(self):
  with self.assertRaises(ValueError):normalized('reltol=1e-6',{'reltol':1e-7})
  with self.assertRaises(ValueError):normalized('reltol=1e-6 reltol=1e-6',{'reltol':1e-6})

if __name__=='__main__':unittest.main()
