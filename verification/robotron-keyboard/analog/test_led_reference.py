#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path

from compare_led_reference import intent_events


class LedReferenceTests(unittest.TestCase):
    def events(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'trace.txt'
            p.write_text('time siso caps i_siso i_caps\n' + '\n'.join(rows))
            return intent_events(p)

    def test_bit_mapping_hold_and_transition_band(self):
        result = self.events(['0 5 5 0 0', '.001 0 0 0 0', '.002 2.5 0 0 0',
                              '.003 5 0 0 0', '.004 5 0 0 0', '.005 5 5 0 0',
                              '.006 0 5 0 0', '.007 0 0 0 0'])
        self.assertEqual([v for _, v in result], [0, 1, 3, 2, 0])
        self.assertEqual(result[1][0], .003)

    def test_missing_known_state_is_not_an_empty_pass(self):
        with self.assertRaisesRegex(ValueError, 'No known LED'):
            self.events(['.001 2.5 2.5 0 0', '.002 2.5 2.5 0 0'])

    def test_reversal_and_nonfinite_samples_rejected(self):
        for rows in [['.002 0 0 0 0', '.001 5 5 0 0'], ['.001 nan 0 0 0']]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.events(rows)


if __name__ == '__main__':
    unittest.main()
