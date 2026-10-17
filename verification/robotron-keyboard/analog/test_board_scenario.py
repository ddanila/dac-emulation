#!/usr/bin/env python3
"""Board scenarios retain physical contact times despite an independent CPU clock."""
import unittest
from pathlib import Path

import board_scenario as board

HERE = Path(__file__).resolve().parent


class BoardScenarioTests(unittest.TestCase):
    def test_contact_wall_time_and_release(self):
        scenario = board.load_board_scenario(HERE / 'scenarios/release-repress.json')
        source = board.contact_source(scenario, 61)
        self.assertIn('129000000n 0 129000001n 5', source)
        self.assertIn('155000000n 5 155000001n 0', source)
        self.assertEqual(board.contact_source(scenario, 0), '0')
        self.assertAlmostEqual(board.stop_seconds(scenario), .245)

    def test_window_uses_wall_time_not_cpu_clock_count(self):
        scenario = board.load_board_scenario(HERE / 'scenarios/single-press.json')
        tick = scenario['observations'][0]['startCycle']
        stamp = (board.ORIGIN_NS + tick * board.TICK_NS) * 1000
        events = [(stamp + i, 1) for i in range(26)]
        self.assertTrue(board.coverage(scenario, events)['passed'])
        self.assertFalse(board.coverage(scenario, [(t - board.ORIGIN_NS * 1000, b) for t, b in events])['passed'])
        self.assertFalse(board.coverage(scenario, [])['passed'])

    def test_service_reset_cannot_bypass_board_reset(self):
        with self.assertRaisesRegex(ValueError, 'BR2 closed'):
            board.load_board_scenario(HERE / 'scenarios/reset.json')


if __name__ == '__main__':
    unittest.main()
