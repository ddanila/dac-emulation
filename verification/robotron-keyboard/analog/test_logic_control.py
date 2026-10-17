#!/usr/bin/env python3
"""Check physical control-pin boundaries before replacing digital pullups."""
import copy
import unittest
from circuit import load
from logic_control import wiring


class LogicControlTests(unittest.TestCase):
    def test_canonical_paths_and_explicit_fixture_capacitance(self):
        components, _ = load()
        lines, models, info = wiring(components)
        self.assertIn('R6.3 n_p5V n_LATCH_OE_N 1k', lines)
        self.assertIn('R6.6 n_p5V n_FF_PULLUP 1k', lines)
        self.assertIn('R9.9 n_p5V n_IO_ACTIVE 3.9k', lines)
        self.assertEqual(set(models), {'R6.3', 'R6.6', 'R9.9'})
        self.assertEqual(info['drivers']['ioActive'], {'reference': 'A2.2', 'pin': '6'})
        self.assertFalse(any(line.startswith('Ccontrol') for line in lines))
        loaded, _, _ = wiring(components, 10)
        self.assertEqual(sum(line.startswith('Ccontrol') for line in loaded), 3)

    def test_changed_driver_load_supply_or_extra_attachment_rejected(self):
        components, _ = load()
        for reference, pin in [('A2.2', '6'), ('A2.2', '8'), ('A4', '9'), ('A6', '13'), ('R6.6', '1')]:
            changed = copy.deepcopy(components)
            changed[reference]['pins'][pin] = '/WRONG_NET'
            with self.subTest(reference=reference, pin=pin), self.assertRaises(ValueError):
                wiring(changed)
        for load_pf in (-1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                wiring(components, load_pf)


if __name__ == '__main__':
    unittest.main()
