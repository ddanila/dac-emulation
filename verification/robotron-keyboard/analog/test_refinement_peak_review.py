import tempfile
import unittest
from pathlib import Path
from decimal import Decimal
from refinement_peak_review import interpolate, witnesses

class PeakTests(unittest.TestCase):
 def test_exact_linear_interpolation(self):
  self.assertEqual(interpolate([[0,2],[2,6]], .5), Decimal(3))
  self.assertEqual(interpolate([[0,2],[2,6]], 2), Decimal(6))
  for bracket,t in (([[0,2],[0,3]],0),([[1,2],[2,3]],0)):
   with self.assertRaises(ValueError):interpolate(bracket,t)
 def test_streaming_brackets_and_boundaries(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'trace.txt'
   path.write_text('time v(a)\n0 2\n1 4\n2 6\n')
   requests=[{'id':i,'signal':'v(a)','timeSeconds':t} for i,t in enumerate((0,.5,1,2))]
   result=witnesses(path,['v(a)'],1e9,requests)
   self.assertEqual([Decimal(result[i]['interpolatedValue']) for i in range(4)],list(map(Decimal,(2,3,4,6))))
   self.assertFalse(result[1]['atSavedKnot'])
   self.assertTrue(result[3]['atSavedKnot'])
   with self.assertRaises(ValueError):witnesses(path,['v(a)'],1e9,[{'id':0,'signal':'v(a)','timeSeconds':3}])

if __name__=='__main__':unittest.main()
