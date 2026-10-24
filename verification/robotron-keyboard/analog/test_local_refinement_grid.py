import unittest
from local_refinement_grid import grids,startup_grids

class LocalGridTests(unittest.TestCase):
    def test_nested_clipped_and_common_preserved(self):
        assessment={'refinementPairs':[{'signals':{
            'v':{'unit':'V','timeSeconds':1e-9},
            'end':{'unit':'V','timeSeconds':999e-9},
            'i':{'unit':'A','timeSeconds':999}}}]}
        common={'timesSeconds':[5.123e-9]}
        result=grids(assessment,common,1000)
        for grid in result:
            self.assertIn(5.123e-9,grid['timesSeconds'])
            self.assertTrue(all(0<t<=1e-6 for t in grid['timesSeconds']))
            self.assertEqual(grid['timesSeconds'],sorted(set(grid['timesSeconds'])))
        for a,b in zip(result,result[1:]):
            self.assertLess(set(a['timesSeconds']),set(b['timesSeconds']))
    def test_startup_extension_preserves_inputs_and_nesting(self):
        original=[{'timesSeconds':[5.123e-9,9e-6],'stopNs':10000} for _ in range(3)]
        result=startup_grids(original,20)
        for a,b in zip(original,result):
            self.assertEqual(a['timesSeconds'],[5.123e-9,9e-6])
            self.assertTrue(set(a['timesSeconds'])<=set(b['timesSeconds']))
            self.assertIn(20e-9,b['timesSeconds'])
        for a,b in zip(result,result[1:]):self.assertLess(set(a['timesSeconds']),set(b['timesSeconds']))
        for bad in (0,float('nan'),20000,3000):
            with self.assertRaises(ValueError):startup_grids(original,bad)
    def test_outside_peak_rejected(self):
        with self.assertRaises(ValueError):
            grids({'refinementPairs':[{'signals':{'v':{'unit':'V','timeSeconds':1}}}]}, {'timesSeconds':[]},1000)

if __name__=='__main__':unittest.main()
