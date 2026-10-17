#!/usr/bin/env python3
"""The optional driver adapter must preserve schematic-derived passive wiring."""
import copy
from unittest.mock import patch
import unittest

from circuit import load
from output_circuit import output_circuit
from ttl7406_output_probe import driver_circuit


class TTL7406OutputTests(unittest.TestCase):
    def test_passives_and_connector_mapping_preserved(self):
        components, _ = load()
        original, metadata = output_circuit(components, cable_pf=2000)
        nominal, _ = driver_circuit(components, 'nominal', 2000)
        self.assertEqual(nominal[:-1], original)
        changed, info = driver_circuit(components, '7406-dc', 2000)
        for line in original:
            if 'OUTPUT_SINK_NOMINAL' not in line:
                self.assertIn(line, changed)
        self.assertEqual(metadata['serial'], info['serial'])
        self.assertEqual(metadata['leds'], info['leds'])
        self.assertIn('Vdriver_supply n_p5V driver_vp 0', changed)
        self.assertFalse(info['serialDriver']['modelQualified'])

    def test_incompatible_package_and_unclassified_gate_rejected(self):
        components, _ = load()
        changed = copy.deepcopy(components)
        changed['A1']['type'] = '7407'
        with self.assertRaisesRegex(ValueError, 'package or ground'):
            driver_circuit(changed, '7406-dc', 1000)
        lines, metadata = output_circuit(components)
        lines.append('Sadditional x 0 intent 0 OUTPUT_SINK_NOMINAL')
        with patch('ttl7406_output_probe.output_circuit', return_value=(lines, metadata)):
            with self.assertRaisesRegex(ValueError, 'Unclassified remaining'):
                driver_circuit(components, '7406-dc', 1000)


if __name__ == '__main__':
    unittest.main()
