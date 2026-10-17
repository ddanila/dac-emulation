#!/usr/bin/env python3
"""Reset coverage must prove pin delivery and CPU restart, not only later traffic."""
import unittest

from reset_observation import validate_service_reset, ResetMismatch

SCENARIO = {'cycles': 100000, 'resets': [
    {'cycle': 40000, 'asserted': True}, {'cycle': 40016, 'asserted': False}]}
LOG = '''RESET 0 0
RESET 501000 0
RESET 1000001000 1
FIRST_FETCH 1001001000 0000 af
RESET 41000001000 0
RESET 41016001000 1
FIRST_FETCH 41017001000 0000 af
'''


class ResetObservationTests(unittest.TestCase):
    def test_delivered_reset_and_restart(self):
        result = validate_service_reset(LOG, SCENARIO, 0xaf)
        self.assertEqual(len(result['firstFetches']), 2)

    def test_lost_pulse_is_not_hidden_by_later_serial_traffic(self):
        log = '\n'.join(LOG.splitlines()[:4]) + '\nSERIAL_TX 61000000000 1\nSERIAL_RX 61000200000 1\n'
        with self.assertRaises(ResetMismatch) as caught:
            validate_service_reset(log, SCENARIO, 0xaf)
        self.assertEqual(caught.exception.details['signal'], 'RESET_N')

    def test_wrong_pin_timing_or_unknown_level_rejected(self):
        for log in (LOG.replace('41000001000', '41000010000'), LOG.replace('41000001000 0', '41000001000 x'),
                    LOG.replace('RESET 41000001000 0', 'RESET 40000001000 0')):
            with self.subTest(log=log), self.assertRaises(ResetMismatch):
                validate_service_reset(log, SCENARIO, 0xaf)

    def test_no_restart_wrong_address_or_wrong_byte_rejected(self):
        for replacement in ('', 'FIRST_FETCH 41017001000 4000 af', 'FIRST_FETCH 41017001000 0000 00'):
            with self.subTest(replacement=replacement), self.assertRaises(ResetMismatch) as caught:
                validate_service_reset(LOG.replace('FIRST_FETCH 41017001000 0000 af', replacement), SCENARIO, 0xaf)
            self.assertEqual(caught.exception.details['signal'], 'CPU first fetch')


if __name__ == '__main__':
    unittest.main()
