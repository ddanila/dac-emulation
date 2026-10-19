import unittest
from fractions import Fraction
from linear_precision_review import solve


class PrecisionTests(unittest.TestCase):
    def test_row_pivot_and_known_solution(self):
        system = {'metadata': {'size': 2}, 'a': {(1, 2): Fraction(2), (2, 1): Fraction(1),
                                              (2, 2): Fraction(1)}, 'b': {1: Fraction(6), 2: Fraction(4)}}
        self.assertEqual(solve(system, 80), {1: Fraction(1), 2: Fraction(3)})

    def test_large_dynamic_range(self):
        large = Fraction(2**80)
        system = {'metadata': {'size': 2}, 'a': {(1, 1): large, (1, 2): Fraction(1),
                                              (2, 1): Fraction(1), (2, 2): Fraction(0)},
                  'b': {1: large, 2: Fraction(1)}}
        self.assertEqual(solve(system, 80), {1: Fraction(1), 2: Fraction(0)})

    def test_singular_system_rejected(self):
        with self.assertRaises(ValueError):
            solve({'metadata': {'size': 1}, 'a': {}, 'b': {1: Fraction(1)}}, 80)


if __name__ == '__main__':
    unittest.main()
