#!/usr/bin/env python3
"""A clock-load fixture must reject misidentified CPU and pullup connections."""
import copy
import unittest
from circuit import load
from clock_output_probe import wiring


class ClockOutputTests(unittest.TestCase):
    def test_canonical_pullup_and_bridge(self):
        components, _ = load()
        lines, nets = wiring(components, 50e-12)
        self.assertIn('R10.3 n_p5V n_CLK 560', lines)
        self.assertIn('RBR1 n_OSC_OUT n_CLK .001', lines)
        self.assertEqual(nets['clock'], 'n_CLK')

    def test_wrong_clock_pin_pullup_or_supply_rejected(self):
        components, _ = load()
        for reference, pin in (('A5', '6'), ('A5', '11'), ('A7', '10'), ('R10.3', '2')):
            changed = copy.deepcopy(components)
            changed[reference]['pins'][pin] = '/WRONG_NET'
            with self.assertRaises(ValueError):
                wiring(changed, 50e-12)


if __name__ == '__main__':
    unittest.main()
