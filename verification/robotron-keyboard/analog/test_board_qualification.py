#!/usr/bin/env python3
"""Reject timing or model changes even when full-board serial bits agree."""
import copy
import tempfile
import unittest
from pathlib import Path

from qualify_board_pair import compare, normalized_analysis, require_clock_voltage
from receiver_margins import measure


def report(step):
    return {'assumptions': {'maximumStepNs': step, 'bridgeDelayNs': 10},
            **{k: 'same' for k in ('romSha256', 'connectivitySha256', 'bridge', 'tv80',
                                  'ngspice', 'iverilog', 'scenario', 'sources')},
            'hdlSha256': {'/run/controller.v': 'same'},
            'serialTransport': {'transmitted': [[100000, 1]], 'received': [[200000, 1]]},
            'resetEvents': [[.1248, '1']], 'firstFetchAfterRelease': [.124801, '0000', 'af']}


class BoardQualificationTests(unittest.TestCase):
    def test_voltage_evidence_is_required_beyond_timing(self):
        valid = {'supplyTraceSignal': 'v(n_p5V)', 'cpuClockVoltage': {
            'samples': 10, 'validSupplySamples': 10,
            'lowExcursionObserved': True, 'highExcursionObserved': True}}
        require_clock_voltage(valid)
        for field, value in [('samples', 0), ('validSupplySamples', 9),
                             ('lowExcursionObserved', False), ('highExcursionObserved', False)]:
            changed = copy.deepcopy(valid)
            changed['cpuClockVoltage'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                require_clock_voltage(changed)
        with self.assertRaises(ValueError):
            require_clock_voltage({})

    def test_transient_invocation_and_breakpoint_are_verified(self):
        ordinary = 'fixture\n.control\ntran 2n .127 124m\n.endc\n.end\n'
        from transient_analysis import with_minimum_breakpoint
        explicit = with_minimum_breakpoint(ordinary, 1)
        settings = {'maximumStepNs': 2, 'minimumBreakpointFs': 1, 'analysisInvocation': 'deck-tran/run'}
        self.assertIn('tran TIMESTEP .127 124m', normalized_analysis(ordinary, {'maximumStepNs': 2}))
        self.assertIn('.tran TIMESTEP .127 124m', normalized_analysis(explicit, settings))
        for changed in (explicit.replace('1f', '2f'), explicit.replace('run\n', ''),
                        explicit.replace('.tran 2n', '.tran 1n'), explicit + 'tran 2n 1u\n'):
            with self.assertRaises(ValueError):
                normalized_analysis(changed, settings)
        with self.assertRaises(ValueError):
            normalized_analysis(ordinary, settings)
        with self.assertRaises(ValueError):
            normalized_analysis(explicit, {'maximumStepNs': 2})

    def test_phase_shift_cannot_hide_behind_matching_bits(self):
        coarse, fine = report(10), report(5)
        self.assertTrue(compare(coarse, fine, 15)['withinTolerance'])
        for key in ('reset', 'fetch', 'received'):
            changed = copy.deepcopy(fine)
            if key == 'reset':
                changed['resetEvents'][0][0] += 20e-9
            elif key == 'fetch':
                changed['firstFetchAfterRelease'][0] += 20e-9
            else:
                changed['serialTransport']['received'][0][0] += 20000
            self.assertFalse(compare(coarse, changed, 15)['withinTolerance'])

    def test_model_changes_missing_edges_and_unrefined_steps_fail(self):
        for kind in ('step', 'model', 'bits', 'reset', 'runtime'):
            fine = report(5)
            if kind == 'runtime': fine['ngspiceRuntime'] = {'codeModels': ['different']}
            if kind == 'step': fine['assumptions']['maximumStepNs'] = 10
            if kind == 'model': fine['sources'] = 'changed'
            if kind == 'bits': fine['serialTransport']['received'] = []
            if kind == 'reset': fine['resetEvents'] = []
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                compare(report(10), fine, 15)

    def test_board_margin_uses_cable_data_not_cpu_clock(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / 'trace.txt'
            trace.write_text('time cpu_clock reset cable_data cable_clock\n' + '\n'.join(
                f'{t * 1e-9} 5 5 0 5' for t in range(0, 501, 25)))
            self.assertTrue(measure(trace, [(250000, 1)], 25, columns=5, data_column=3)['withinBudget'])
            with self.assertRaises(ValueError):
                measure(trace, [(250000, 1)], 25, columns=5, data_column=1)
            with self.assertRaises(ValueError):
                measure(trace, [(250000, 1)], 25)


if __name__ == '__main__':
    unittest.main()
