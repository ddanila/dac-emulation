#!/usr/bin/env python3
"""Failure controls for firmware-to-cable transport qualification."""
import unittest

from serial_observation import validate_transport


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
