#!/usr/bin/env python3
import unittest
from reset_capacitor_polarity import summarize


class SignedVoltage(unittest.TestCase):
    def rows(self):
        return [[t,5,-2,4] for t in (0,2.5,2.99,3,3.5,4,6.5,7)]

    def test_preserves_negative_voltage_and_capacitor_columns(self):
        r=summarize(self.rows())
        self.assertEqual(r['C2']['startup']['minimumVoltsPin1MinusPin2'],-2)
        self.assertEqual(r['C4']['startup']['maximumVoltsPin1MinusPin2'],4)

    def test_power_off_excursion_is_not_filtered_by_supply(self):
        rows=self.rows();rows[4]=[3.5,0,-8,-1]
        r=summarize(rows)
        self.assertEqual(r['C2']['power-off']['minimumVoltsPin1MinusPin2'],-8)
        self.assertEqual(r['C4']['power-off']['minimumVoltsPin1MinusPin2'],-1)

    def test_missing_end_rejected(self):
        with self.assertRaises(ValueError):summarize(self.rows()[:-1])

    def test_nonfinite_and_nonmonotonic_rejected(self):
        for replacement in ([3.5,0,float('nan'),0],[2,0,0,0]):
            rows=self.rows();rows[4]=replacement
            with self.assertRaises(ValueError):summarize(rows)


if __name__=='__main__':unittest.main()
