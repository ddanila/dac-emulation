"""Test current direction, unique roots and rejection without vendor tables."""
import unittest
from ls00_ibis_loadline import equilibrium, tables


class LoadlineTests(unittest.TestCase):
    def test_known_resistor_divider(self):
        result = equilibrium([(0, 0), (5, .05)], 5, 100)
        self.assertAlmostEqual(result['outputVolts'], 2.5)
        self.assertAlmostEqual(result['pullupAmps'], .025)
        self.assertLess(abs(result['kclResidualAmps']), 1e-12)

    def test_high_output_supply_relative_coordinate(self):
        # A high driver sources current below 5 V. Convert the IBIS axis,
        # preserving current sign, before solving against the pullup resistor.
        table = [(0, 0), (5, -.05)]
        points = sorted((5 - v, i) for v, i in table)
        self.assertEqual(equilibrium(points, 5, 560)['outputVolts'], 5)

    def test_ambiguous_missing_or_extrapolated_root_rejected(self):
        for points in [[(0, .1), (5, .1)], [(1, 0), (4, .1)],
                       [(0, .05), (5, 0)], [(0, 0), (2, .1), (3, -.1), (5, .1)],
                       [(0, 0), (0, .1), (5, .2)]]:
            with self.subTest(points=points), self.assertRaises(ValueError):
                equilibrium(points, 5, 100)

    def test_malformed_table_rejected(self):
        good = '[Model] ls00_OUT\n[Pullup]\n0 0 0 0\n5 -1 -1 -1\n[Pulldown]\n0 0 0 0\n5 1 1 1\n'
        self.assertEqual(set(tables(good)), {'pullup', 'pulldown'})
        for text in [good.replace('5 -1 -1 -1', '0 -1 -1 -1'),
                     good.replace('5 -1 -1 -1', '5 nan -1 -1'),
                     good.replace('[Pulldown]', '[Other]')]:
            with self.assertRaises(ValueError):
                tables(text)


if __name__ == '__main__':
    unittest.main()
