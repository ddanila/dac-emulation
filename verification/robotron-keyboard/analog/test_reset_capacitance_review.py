#!/usr/bin/env python3
"""Protect absolute-time reset crossing accounting from filtering extra releases."""
import unittest
from reset_capacitance_review import releases


class Crossings(unittest.TestCase):
    def test_restart_is_relative_to_power_edge(self):
        self.assertAlmostEqual(releases([[4.1,0,0,1],[4.3,0,0,3]],4,7)[0], .2)

    def test_extra_release_is_not_hidden(self):
        rows = [[t,0,0,v] for t,v in [(0,0),(1,3),(2,0),(3,3)]]
        self.assertEqual(len(releases(rows,0,3)),2)

    def test_no_release_is_not_a_pass(self):
        self.assertEqual(releases([[0,0,0,0],[3,0,0,1]],0,3),[])

    def test_ignore_outside_window_and_count_exact_threshold_once(self):
        rows = [[t,0,0,v] for t,v in [(0,0),(1,3),(4,0),(5,2),(6,3)]]
        self.assertEqual(releases(rows,4,7),[1])


if __name__ == '__main__':
    unittest.main()
