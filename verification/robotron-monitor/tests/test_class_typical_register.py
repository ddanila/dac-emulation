import json
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT/'reference/k7222-11'


class ClassTypicalRegisterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.register = json.loads((REF/'class-typical-register.json').read_text())
        cls.by_id = {row['id']: row for row in cls.register['entries']}

    def test_entries_have_sources_bounds_and_unique_ids(self):
        register = self.register
        self.assertEqual(register['format'], 'dac-monitor-class-typical-register-v1')
        self.assertIn('partial', register['status'])
        self.assertEqual(len(self.by_id), len(register['entries']))
        for row in register['entries']:
            self.assertTrue(row['stage'] and row['model_ref'] and row['basis'])
            self.assertTrue(row['sources'])
            self.assertTrue(all(key in register['sources'] for key in row['sources']))
            low, high = row['bounds']
            self.assertTrue(all(math.isfinite(value) for value in (low, row['value'], high)))
            self.assertLessEqual(low, row['value'])
            self.assertLessEqual(row['value'], high)
        self.assertTrue(register['open_families'])

    def test_device_and_instrument_rows_match_live_sources(self):
        devices = json.loads((REF/'device-model-register.json').read_text())
        for device in devices['devices']:
            for key, parameter in device['parameters'].items():
                row = self.by_id[device['id']+'.'+key]
                self.assertEqual(row['value'], parameter['nominal'])
                self.assertEqual(row['bounds'], parameter['bounds'])
        instrument = json.loads((REF/'service-instrument.json').read_text())
        for key in ('vertical_bandwidth_hz', 'direct_input_resistance_ohm',
                    'direct_input_capacitance_f'):
            row = self.by_id['service-instrument.'+key]
            self.assertEqual(row['value'], instrument[key]['value'])
            self.assertEqual(row['bounds'], instrument[key]['bounds'])
        sources = {item['file']: item['sha256'] for item in
                   json.loads((ROOT/'sources.json').read_text())['sources']}
        self.assertEqual(self.register['sources']['b31_g_outline']['sha256'],
                         sources['b31-g-outline.gif'])


if __name__ == '__main__':
    unittest.main()
