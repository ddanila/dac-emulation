#!/usr/bin/env python3
"""Failure controls for firmware-to-cable transport qualification."""
import unittest

from serial_observation import validate_transport, first_reference_difference, SerialMismatch


class SerialObservationTests(unittest.TestCase):
    def test_received_sequence_and_delay(self):
        result = validate_transport('SERIAL_TX 1000 1\nSERIAL_RX 1200 1\n'
                                    'SERIAL_TX 2000 0\nSERIAL_RX 2300 0\n', True)
        self.assertTrue(result['activityObserved'])
        self.assertEqual(result['received'], [(1200, 1), (2300, 0)])
        self.assertAlmostEqual(result['clockTransportSeconds'][0], 200e-12)

    def test_idle_is_not_activity_qualification(self):
        self.assertFalse(validate_transport('')['activityObserved'])
        with self.assertRaises(ValueError):
            validate_transport('', True)

    def test_reference_difference_retains_both_clock_domains(self):
        reference = [(10, 1), (20, 0)]
        self.assertIsNone(first_reference_difference(reference, [(1000, 1), (2000, 0)]))
        difference = first_reference_difference(reference, [(1000, 1), (2000, 1)])
        self.assertEqual(difference['ordinal'], 1)
        self.assertEqual(difference['expected'], {'cycle': 20, 'bit': 0})
        self.assertEqual(difference['observed'], {'timePs': 2000, 'bit': 1})
        self.assertIsNone(first_reference_difference(reference, [(1000, 1)])['observed'])
        self.assertIsNone(first_reference_difference([], [(1000, 1)])['expected'])

    def test_transport_difference_identifies_signal_and_times(self):
        with self.assertRaises(SerialMismatch) as caught:
            validate_transport('SERIAL_TX 1000 1\nSERIAL_RX 1200 0\n')
        self.assertEqual(caught.exception.details, {
            'signal': 'serial_data', 'ordinal': 0, 'transmittedTimePs': 1000,
            'receivedTimePs': 1200, 'expectedBit': 1, 'observedBit': 0})
        with self.assertRaises(SerialMismatch) as caught:
            validate_transport('SERIAL_TX 1000 1\n')
        self.assertEqual(caught.exception.details['signal'], 'serial_clock')
        self.assertEqual(caught.exception.details['firstUnpairedOrdinal'], 0)
        self.assertEqual(caught.exception.details['transmittedEvent'], (1000, 1))

    def test_bad_transport_is_rejected(self):
        failures = [
            'SERIAL_TX 1000 1\n',  # missing edge
            'SERIAL_RX 1200 1\n',  # spurious edge
            'SERIAL_TX 1000 1\nSERIAL_RX 1200 0\n',  # bit changed
            'SERIAL_TX 1000 x\nSERIAL_RX 1200 1\n',
            'SERIAL_TX 1000 1\nSERIAL_RX 1200 x\n',
            'SERIAL_TX 1000 1\nSERIAL_RX 900 1\n',  # receiver precedes source
            'SERIAL_TX 1000 1\nSERIAL_RX 1000 1\n',  # no electrical propagation
            'SERIAL_TX 1000 1\nSERIAL_TX 1100 0\nSERIAL_RX 1200 1\nSERIAL_RX 1300 0\n',
            'SERIAL_TX 1000 1\nSERIAL_TX 1000 1\nSERIAL_RX 1200 1\nSERIAL_RX 1300 1\n',
            'SERIAL_TX bad 1\n',
        ]
        for log in failures:
            with self.subTest(log=log), self.assertRaises(ValueError):
                validate_transport(log)


if __name__ == '__main__':
    unittest.main()
