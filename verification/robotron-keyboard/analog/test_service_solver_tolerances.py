"""Explicit numerical controls must not silently combine with unknown defaults."""
import unittest
import argparse
from firmware_io_cosim import solver_tolerances, positive_iterations, truncation_tolerance


class ServiceSolverToleranceTests(unittest.TestCase):
    def test_truncation_control_cannot_loosen_xspice_default(self):
        self.assertEqual(truncation_tolerance('0.1'), .1)
        self.assertEqual(truncation_tolerance('1'), 1)
        for value in ('0', '-1', '7', 'nan', 'inf', 'other'):
            with self.assertRaises(argparse.ArgumentTypeError):
                truncation_tolerance(value)

    def test_iteration_limit_is_a_positive_integer(self):
        self.assertEqual(positive_iterations('100'), 100)
        for value in ('0', '-1', '1.5', 'nan', 'inf'):
            with self.assertRaises(argparse.ArgumentTypeError):
                positive_iterations(value)

    def test_omitted_controls_preserve_engine_defaults(self):
        self.assertIsNone(solver_tolerances(None, None, None))

    def test_explicit_controls_preserve_values(self):
        self.assertEqual(solver_tolerances(1e-4, 1e-7, 1e-13),
                         {'reltol': 1e-4, 'vntol': 1e-7, 'abstol': 1e-13})

    def test_partial_nonpositive_and_nonfinite_controls_rejected(self):
        for index in range(3):
            for invalid in (None, 0, -1, float('inf'), float('nan')):
                values = [1e-4, 1e-7, 1e-13]
                values[index] = invalid
                with self.assertRaises(ValueError):
                    solver_tolerances(*values)


if __name__ == '__main__':
    unittest.main()
