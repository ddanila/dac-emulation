import unittest
from common_samples import samples_at, compare_native

class CommonSamples(unittest.TestCase):
 def test_never_interpolates(self):
  result=samples_at([(0,0),(1,10),(2,20)],[0,.75,2])
  self.assertEqual([r['values'][0] for r in result],[0,10,20])
  self.assertFalse(result[1]['exactTime'])
  self.assertEqual(result[1]['timeErrorSeconds'],.25)
  self.assertTrue(result[2]['exactTime'])
 def test_comparison_requires_identical_actual_times(self):
  a=samples_at([(0,0),(1,10),(2,20)],[1])
  b=samples_at([(0,0),(1,11),(2,20)],[1])
  result=compare_native(a,b,['v(a)'])
  self.assertTrue(result['identicalActualTimes'])
  self.assertEqual(result['signals']['v(a)']['maximumAbsoluteDifference'],1)
  b[0]['actualSeconds']+=.01
  self.assertIsNone(compare_native(a,b,['v(a)'])['signals'])
 def test_rejects_bad_extent_or_order(self):
  for rows,times in (([(1,0),(2,1)],[0]), ([(0,0),(1,1)],[2]),
                     ([(0,0),(0,1)],[0]), ([(0,0),(1,1)],[1,0])):
   with self.assertRaises(ValueError):samples_at(rows,times)

if __name__=='__main__':unittest.main()
