#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path

from led_observation import measure


class LedObservationTests(unittest.TestCase):
    def run_trace(self, kind='good'):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'led-trace.txt'
            rows = []
            for t in range(0, 1001, 25):
                on = 250 <= t < 750
                intent = 5 if on else 0
                current = .01 if on else 0
                if kind == 'stuck': current = 0
                if kind == 'unknown' and on: intent = 2.5
                if kind == 'idle': intent, current = 0, 0
                if kind == 'startup' and t < 200: intent, current = 5, 0
                rows.append(f'{t * 1e-9} {intent} {intent} {current} {current}')
            path.write_text('time siso caps siso_current caps_current\n' + '\n'.join(rows))
            return measure(path, 25, True, start_seconds=200e-9 if kind == 'startup' else 0)

    def test_both_indicators_switch(self):
        result = self.run_trace()
        self.assertTrue(result['passed'])
        self.assertTrue(result['bothIndicatorsExercised'])

    def test_no_current_unknown_intent_and_missing_activity_fail(self):
        for kind in ('stuck', 'unknown', 'idle'):
            with self.subTest(kind=kind):
                self.assertFalse(self.run_trace(kind)['passed'])

    def test_service_check_can_exclude_supply_startup(self):
        self.assertTrue(self.run_trace('startup')['passed'])


if __name__ == '__main__':
    unittest.main()
