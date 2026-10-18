"""Validate clamp coordinates and signed current preservation."""
import unittest
from ls00_iv_probe import parse_trace


class IvTests(unittest.TestCase):
    def capture(self):
        return ['v-sweep v(y) i(Vforce) i(Vcc)'] + [f'{i*.01:.17g} {i*.01:.17g} -.02 -.001' for i in range(501)]

    def test_preserves_current_direction(self):
        rows = parse_trace('\n'.join(self.capture()))
        self.assertEqual(rows[200][1:], [2, -.02, -.001])

    def test_rejects_missing_or_displaced_clamp(self):
        cases = [self.capture()[:-1], self.capture(), self.capture(), self.capture()]
        cases[1][201] = '2 2.1 -.02 -.001'
        cases[2][201] = '2 2 nan -.001'
        cases[3][201] = cases[3][200]
        for lines in cases:
            with self.assertRaises(ValueError):
                parse_trace('\n'.join(lines))


if __name__ == '__main__':
    unittest.main()
