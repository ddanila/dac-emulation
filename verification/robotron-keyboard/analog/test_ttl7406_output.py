#!/usr/bin/env python3
"""The optional driver adapter must preserve schematic-derived passive wiring."""
import copy
import json
from pathlib import Path

from write_control import wiring
from unittest.mock import patch
import unittest

from circuit import load
from output_circuit import output_circuit
from ttl7406_output_probe import driver_circuit


class TTL7406OutputTests(unittest.TestCase):
    def test_bus_input_drives_same_transistors_as_serial_output(self):
        components, _ = load()
        for net in ('/D0', '/D7'):
            changed = copy.deepcopy(components)
            changed['A1']['pins']['3'] = net
            lines, metadata = driver_circuit(changed, '7406-dc', 1000, electrical_data_input=True)
            self.assertIn(f'Xdata n_{net[1:]} n_TA_DATEN driver_vp 0 TTL7406_NOMINAL input_br=.01', lines)
            self.assertIn('Xclock clock_intent n_TA_TAKT driver_vp 0 TTL7406_NOMINAL input_br=.01', lines)
            self.assertFalse(any(line.startswith('Xdata data_intent') or line.startswith('Sdata ') for line in lines))
            self.assertEqual(metadata['serialDriver']['dataInput']['net'], net)
        with self.assertRaisesRegex(ValueError, 'transistor driver'):
            driver_circuit(components, 'nominal', 1000, electrical_data_input=True)

    def test_physical_clock_input_and_wr_ownership(self):
        components, _ = load()
        limits = json.loads(Path(__file__).with_name('bus_limits.json').read_text())
        for net in ('/WR_N', '/ALTERNATE_WR'):
            changed = copy.deepcopy(components)
            changed['A1']['pins']['1'] = net
            changed['A5']['pins']['22'] = net
            lines, metadata = driver_circuit(changed, '7406-dc', 1000, electrical_clock_input=True)
            self.assertIn(f'Xclock n_{net[1:]} n_TA_TAKT driver_vp 0 TTL7406_NOMINAL input_br=.01', lines)
            self.assertFalse(any('clock_intent' in line for line in lines))
            self.assertEqual(metadata['serialDriver']['clockInput']['net'], net)
            loads, info = wiring(changed, limits, 3)
            self.assertEqual(info['pins'], ['A1:1', 'A5:22'])
            self.assertTrue(any('V(wr_low)' in line for line in loads))
            self.assertTrue(any('V(wr_high)' in line for line in loads))
        for cap in (None, -1, float('nan'), float('inf')):
            with self.assertRaisesRegex(ValueError, 'capacitance'):
                wiring(components, limits, cap)
        changed = copy.deepcopy(components)
        changed['A1']['pins']['3'] = changed['A5']['pins']['22']
        with self.assertRaisesRegex(ValueError, 'Unmodeled WR connection'):
            wiring(changed, limits, 3)
        changed = copy.deepcopy(components)
        changed['A1']['pins']['1'] = '/DIFFERENT_NET'
        with self.assertRaisesRegex(ValueError, 'mapping'):
            wiring(changed, limits, 3)
        with self.assertRaisesRegex(ValueError, 'transistor driver'):
            driver_circuit(components, 'nominal', 1000, electrical_clock_input=True)

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
