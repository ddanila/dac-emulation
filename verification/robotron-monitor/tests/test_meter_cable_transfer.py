"""Verify the conditional measuring-cable transfer limits."""
import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import meter_cable_transfer as cable


class MeterCableTransferTests(unittest.TestCase):
    def test_saved_structural_bound_and_frequency_limits(self):
        saved = cable.run()
        with (patch.object(cable, 'PDF', Path('/missing/older.pdf')),
              patch.object(cable, 'OPERATION', Path('/missing/older-operation.pdf'))):
            self.assertEqual(saved, cable.run())
        self.assertEqual(cable.gain(0, 100e-12, 1e6), 0)
        self.assertLess(cable.gain(1/0.0195, 100e-12, 1e6), .04)
        self.assertGreater(cable.gain(16000, 100e-12, 1e6), .99)
        self.assertLess(cable.gain(16000, 100e-12, 1e6, 390),
                        cable.gain(16000, 100e-12, 1e6))
        for case in saved['cases']:
            threshold = case['minimum_series_capacitance_f_for_90pct_best_case_gain']
            self.assertTrue(math.isclose(cable.gain(case['frequency_hz'], threshold,
                                                 case['load_ohm']), .9, rel_tol=1e-12))


if __name__ == '__main__':
    unittest.main()
