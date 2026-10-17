#!/usr/bin/env python3
"""Guard the shared contact/reset stimulus against ambiguous or mismatched timing."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from io_scenario import load, contact_source, reset_source, c_header, time_ns, observe

HERE = Path(__file__).resolve().parent


class ScenarioTests(unittest.TestCase):
    def test_single_press_keeps_original_cycle_and_electrical_times(self):
        scenario = load(HERE / 'scenarios/single-press.json')
        self.assertEqual(contact_source(scenario, 61), 'PWL(0 0 5000000n 0 5000001n 5)')
        self.assertEqual(contact_source(scenario, 60), '0')
        self.assertIn('{4000, 61, 1}', c_header(scenario))
        self.assertEqual(time_ns(scenario['cycles']), 30000000)

    def test_reset_uses_same_cycles_in_both_domains(self):
        scenario = load(HERE / 'scenarios/reset.json')
        self.assertIn('41000000n 5 41000001n 0 41016000n 0 41016001n 5', reset_source(scenario))
        self.assertIn('{40000, 1}', c_header(scenario))
        self.assertIn('{40016, 0}', c_header(scenario))

    def test_invalid_stimuli_rejected(self):
        original = load(HERE / 'scenarios/single-press.json')
        cases = []
        for key, value in [('cycle', True), ('cycle', 29000), ('index', 104), ('closed', 1), ('closed', False)]:
            changed = copy.deepcopy(original)
            changed['contacts'][0][key] = value
            cases.append(changed)
        changed = copy.deepcopy(original)
        changed['contacts'] *= 2
        cases.append(changed)
        changed = copy.deepcopy(original)
        changed['resets'] = [{'cycle': 0, 'asserted': True}]
        cases.append(changed)
        changed = copy.deepcopy(original)
        changed['contacts'].append({'cycle': 3000, 'index': 62, 'closed': True})
        cases.append(changed)
        for scenario in cases:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'scenario.json'
                path.write_text(json.dumps(scenario))
                with self.assertRaises(ValueError):
                    load(path)

    def test_all_shipped_scenarios_are_valid(self):
        for path in (HERE / 'scenarios').glob('*.json'):
            with self.subTest(path=path):
                load(path)

    def test_observations_reject_missing_activity_and_unchanged_modifier(self):
        scenario = {'observations': [
            {'name': 'modified', 'startCycle': 100, 'endCycle': 200, 'minimumBits': 2},
            {'name': 'ordinary', 'startCycle': 300, 'endCycle': 400, 'minimumBits': 2, 'differentFrom': 'modified'}]}
        self.assertFalse(observe(scenario, [])['passed'])
        self.assertFalse(observe(scenario, [(110, 1), (120, 0), (310, 1), (320, 0)])['passed'])
        events = [(110, 1), (120, 0), (310, 0), (320, 1)]
        self.assertTrue(observe(scenario, events)['passed'])
        electrical = [(time_ns(cycle) * 1000, bit) for cycle, bit in events]
        self.assertEqual(observe(scenario, events), observe(scenario, electrical, electrical=True))

    def test_release_window_rejects_late_traffic(self):
        scenario = {'observations': [
            {'name': 'released', 'startCycle': 100, 'endCycle': 200, 'minimumBits': 0, 'maximumBits': 0}]}
        self.assertTrue(observe(scenario, [])['passed'])
        self.assertFalse(observe(scenario, [(150, 1)])['passed'])


if __name__ == '__main__':
    unittest.main()
