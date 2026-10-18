#!/usr/bin/env python3
"""Bus attachment changes must not silently escape electrical model review."""
import copy
import json
from pathlib import Path
import unittest

from bus_inventory import inventory
from bus_load import wiring
from circuit import load


class BusInventoryTests(unittest.TestCase):
    def setUp(self):
        self.components, _ = load()
        self.limits = json.loads(Path(__file__).with_name('bus_limits.json').read_text())

    def test_input_bias_and_unknown_output_capacitance_remain_distinct(self):
        report = inventory(self.components, self.limits)
        inputs = [(bus['net'], pin['reference'], pin['pin']) for bus in report['buses']
                  for pin in bus['endpoints'] if pin['role'] == 'input']
        self.assertEqual(inputs, [('/D0', 'A1', '3')])
        for bus in report['buses']:
            latch = next(pin for pin in bus['endpoints'] if pin['reference'] == 'A4')
            self.assertIsNone(latch['capacitanceReference'])
            self.assertFalse(bus['releasedVoltageQualified'])
        self.assertFalse(report['qualified'])

    def test_added_pullup_or_output_attachment_requires_review(self):
        changed = copy.deepcopy(self.components)
        changed['RTEST'] = {'type': '10k', 'pins': {'1': '/D0', '2': '/+5V'}}
        with self.assertRaisesRegex(ValueError, 'Unclassified bus attachment: RTEST'):
            inventory(changed, self.limits)
        changed = copy.deepcopy(self.components)
        changed['A1']['pins']['4'] = '/D1'
        with self.assertRaisesRegex(ValueError, 'Unclassified bus attachment: A1:4'):
            inventory(changed, self.limits)

    def test_pin_mapping_or_device_substitution_is_not_assumed_compatible(self):
        changed = copy.deepcopy(self.components)
        changed['A8']['pins']['9'] = '/D1'
        with self.assertRaisesRegex(ValueError, 'Unexpected data pin/net mapping'):
            inventory(changed, self.limits)
        changed = copy.deepcopy(self.components)
        changed['A5']['type'] = 'Z84C00'
        with self.assertRaisesRegex(ValueError, 'Unsupported bus device'):
            inventory(changed, self.limits)

    def test_unknown_loads_cannot_be_silently_omitted(self):
        for fixture in ({}, {'I8282': 12}, {'I8282': 12, '7406': 3, 'U880': 10}):
            with self.assertRaisesRegex(ValueError, 'Explicit unknown-capacitance'):
                wiring(self.components, self.limits, fixture)
        for value in (-1, float('nan'), float('inf'), True, '3'):
            with self.assertRaisesRegex(ValueError, 'finite nonnegative'):
                wiring(self.components, self.limits, {'I8282': 12, '7406': value})

    def test_loads_preserve_pin_identity_and_distinguish_assumptions(self):
        _, report = wiring(self.components, self.limits, {'I8282': 12, '7406': 3})
        for load in report['loads']:
            self.assertEqual(load['net'], self.components[load['reference']]['pins'][load['pin']])
            self.assertEqual(load['basis'], 'explicit fixture assumption' if
                             load['profile'] in ('I8282', '7406') else 'published reference maximum')
        lines, zero = wiring(self.components, self.limits, {'I8282': 0, '7406': 0})
        self.assertTrue(any(load['capacitanceFarads'] == 0 for load in zero['loads']))
        self.assertFalse(any('Cbus_A4_' in line for line in lines))
        changed = copy.deepcopy(self.components)
        changed['A4']['pins']['10'] = '/+5V'
        with self.assertRaisesRegex(ValueError, 'reference ground'):
            wiring(changed, self.limits, {'I8282': 12, '7406': 3})


if __name__ == '__main__':
    unittest.main()
