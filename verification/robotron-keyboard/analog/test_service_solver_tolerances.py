"""Explicit numerical controls must not silently combine with unknown defaults."""
import unittest
from firmware_io_cosim import solver_tolerances


class ServiceSolverToleranceTests(unittest.TestCase):
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
