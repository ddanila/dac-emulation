"""Stimulus reduction must retain short transitions and bound interpolation error."""
import unittest
from analog_driver_replay import reduce_linear


class AnalogDriverReplayTests(unittest.TestCase):
    def test_straight_line_and_narrow_peak(self):
        self.assertEqual(reduce_linear([(0,0),(.3,.6),(1,2)], 1e-12), [(0,0),(1,2)])
        points = [(0,0),(.49,0),(.5,5),(.51,0),(1,0)]
        self.assertEqual(reduce_linear(points, 1e-12), points)

    def test_bounded_error_at_every_source_knot(self):
        points = [(i/100, ((i % 11)-5)*.001+i/100) for i in range(101)]
        reduced = reduce_linear(points, .002)
        for a,b in zip(reduced,reduced[1:]):
            for t,value in points:
                if a[0] <= t <= b[0]:
                    expected = a[1]+(t-a[0])/(b[0]-a[0])*(b[1]-a[1])
                    self.assertLessEqual(abs(value-expected), .002+1e-15)

    def test_invalid_samples_and_budget(self):
        for points in ([], [(0,0)], [(0,0),(0,1)], [(0,0),(1,float('nan'))]):
            with self.assertRaises(ValueError):
                reduce_linear(points, 1e-12)
        for budget in (0, -1, float('inf'), float('nan')):
            with self.assertRaises(ValueError):
                reduce_linear([(0,0),(1,1)], budget)


if __name__ == '__main__':
    unittest.main()
