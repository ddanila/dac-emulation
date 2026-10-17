#!/usr/bin/env python3
"""Bus attachment changes must not silently escape electrical model review."""
import copy
import json
from pathlib import Path
import unittest

from bus_inventory import inventory
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


if __name__ == '__main__':
    unittest.main()
