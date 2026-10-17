#!/usr/bin/env python3
"""Independent short-time limits and precision checks for the linear reference."""
from decimal import Decimal as D
from pathlib import Path
import tempfile
import unittest
from linear_startup_reference import evaluate, parameters, FIXTURE, compare_trace


class LinearStartupReferenceTests(unittest.TestCase):
    def test_unpowered_initial_state(self):
        self.assertTrue(all(value == 0 for value in evaluate(0).values()))

    def test_short_time_circuit_limits(self):
        # Initially all caps are shorts and inductors carry zero current.
        # Equal supply/return/serial L gives G=-H/4, I'=3H/(4L), K'=H/(4L).
        t, ramp, inductance = D('1e-18'), D('5e6'), D('1e-6')
        p = parameters()
        cb = sum(v for k, v in p.items() if k.startswith(('C3.', 'C5.')))
        expected = {'cableReturnV': -ramp*t/4,
                    'hostSourceCurrentA': -3*ramp*t*t/(8*inductance),
                    'serialBranchCurrentA': ramp*t*t/(8*inductance),
                    'boardRailV': ramp*t**3/(24*inductance*cb),
                    'cableDifferentialV': ramp*t**3/(24*inductance*p['Cdata_load'])}
        actual = evaluate(t)
        for name, value in expected.items():
            with self.subTest(name=name):
                self.assertLess(abs(actual[name]/value-1), D('1e-8'))

    def test_decimal_precision_refinement_at_end_of_window(self):
        low, high = evaluate('1e-7', 80), evaluate('1e-7', 120)
        for name in low:
            self.assertLess(abs(low[name]-high[name]), D('1e-30'))

    def test_waveform_validation_and_known_unpowered_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'trace.txt'
            path.write_text('time b g i\n0 0 0 0\n1e-9 0 0 0\n')
            result = compare_trace(path, 1)
            self.assertEqual(result['lastSeconds'], '1E-9')
            self.assertTrue(all(D(v['absoluteDifference']) == 0
                                for v in result['maximumDifferences'].values()))
            for data in ('0 NaN 0 0', '-1e-9 0 0 0', '1e-9 0 0 0',
                         '0 0 0', '0 0 0 0\n2e-7 0 0 0'):
                path.write_text('time b g i\n' + data + '\n')
                with self.subTest(data=data), self.assertRaises(ValueError):
                    compare_trace(path, 0)

    def test_rejects_other_circuits_and_outside_ramp_window(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'changed.cir'
            path.write_text(FIXTURE.read_text().replace('1000p', '2000p'))
            with self.assertRaisesRegex(ValueError, 'frozen'):
                parameters(path)
        for time in ('-1e-9', '1.01e-7', 'NaN', 'Infinity'):
            with self.subTest(time=time), self.assertRaises(ValueError):
                evaluate(time)


if __name__ == '__main__':
    unittest.main()
