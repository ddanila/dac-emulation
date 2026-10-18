import unittest
from compare_driver_replay import prefix


class PrefixTests(unittest.TestCase):
    def test_keeps_knots_and_interpolates_boundary(self):
        self.assertEqual(list(prefix([(0,0),(1,4),(2,0),(3,9)],1.5)),
                         [(0,0),(1,4),(1.5,2)])
        self.assertEqual(list(prefix([(0,0),(1,4),(2,0)],1)),[(0,0),(1,4)])

    def test_rejects_missing_extent_and_invalid_boundary(self):
        for end in (0,-1,float('nan'),float('inf'),3):
            with self.assertRaises(ValueError):
                list(prefix([(0,0),(2,0)],end))
        with self.assertRaises(ValueError):
            list(prefix([(1,0),(2,0)],.5))
