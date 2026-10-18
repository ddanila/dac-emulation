#!/usr/bin/env python3
"""Reject control-net omissions and confirm pullups are assigned to actual CPU pins."""
import copy
import unittest
from circuit import load
from cpu_control import wiring, reset_load


class CPUControlTests(unittest.TestCase):
    def test_reset_load_uses_cpu_pin_and_preserves_profile_boundary(self):
        components, _ = load()
        components['A5']['pins']['26'] = '/TEST_RESET'
        lines, info = reset_load(components, 'reference-capacitance')
        self.assertEqual(len(lines), 1)
        fields = lines[0].split()
        self.assertEqual(fields[:3], ['Ccpu_reset', 'n_TEST_RESET', '0'])
        self.assertEqual(float(fields[3]), 5e-12)
        self.assertIsNone(info['resistanceOhms'])
        self.assertFalse(info['qualified'])
        lines, info = reset_load(components)
        self.assertEqual(info['capacitanceFarads'], 10e-12)
        self.assertIn('Rcpu_reset n_TEST_RESET 0 1g', lines)
        with self.assertRaises(ValueError):
            reset_load(components, 'measured')
        components['A5']['pins']['26'] = components['A5']['pins']['29']
        with self.assertRaises(ValueError):
            reset_load(components)

    def test_resistors_and_each_input_load_are_present(self):
        components, _ = load()
        lines, models, info = wiring(components)
        self.assertIn('R6.4 n_p5V n_CPU_PULLUP 1k', lines)
        self.assertIn('R6.5 n_p5V n_BUSRQ_N 1k', lines)
        for pin, net in [('16', 'n_CPU_PULLUP'), ('17', 'n_CPU_PULLUP'),
                         ('24', 'n_CPU_PULLUP'), ('25', 'n_BUSRQ_N')]:
            self.assertTrue(any(line.startswith(f'Ccpu_control_{pin} {net} 0 ') for line in lines))
        self.assertEqual(set(models), {'R6.4', 'R6.5'})
        self.assertEqual(info['inputCapacitanceFaradsPerPin'], 5e-12)
        self.assertFalse(info['qualified'])

    def test_changed_pin_supply_or_extra_attachment_rejected(self):
        components, _ = load()
        for reference, pin in [('A5', '17'), ('A5', '25'), ('R6.4', '1'), ('R6.5', '2'), ('X1', 'A9')]:
            changed = copy.deepcopy(components)
            changed[reference]['pins'][pin] = '/WRONG_NET'
            with self.subTest(reference=reference, pin=pin), self.assertRaises(ValueError):
                wiring(changed)
        changed = copy.deepcopy(components)
        changed['A5']['pins']['18'] = '/CPU_PULLUP'
        with self.assertRaises(ValueError):
            wiring(changed)


if __name__ == '__main__':
    unittest.main()
