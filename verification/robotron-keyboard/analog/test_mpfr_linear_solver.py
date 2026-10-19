"""Native MPFR arithmetic against independent Decimal solutions, without ngspice."""
from fractions import Fraction
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

from linear_precision_review import solve

HERE = Path(__file__).resolve().parent


class MpfrTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.binary = Path(cls.temporary.name)/'solve'
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'mpfr', 'gmp'], text=True))
        subprocess.run([*shlex.split(os.environ.get('CC', 'cc')), '-O2', '-Wall', '-Wextra', '-Werror',
                        str(HERE/'reports/host-mpfr-linear-review/solve.c'), *flags,
                        '-o', str(cls.binary)], check=True, capture_output=True, text=True)

    def run_solver(self, stimulus, bits=256):
        return subprocess.run([str(self.binary), str(bits)], input=stimulus,
                              capture_output=True, text=True, timeout=30)

    def test_recorded_systems_against_independent_decimal(self):
        for name in ('control', 'shifted'):
            with self.subTest(system=name):
                stimulus = (HERE/'reports/host-mpfr-linear-review'/name/'input.txt').read_text()
                lines = stimulus.splitlines()
                size, count = map(int, lines[0].split())
                matrix = {}
                for line in lines[1:count+1]:
                    row, col, value = line.split()
                    matrix[int(row), int(col)] = Fraction(float.fromhex(value))
                rhs = {i+1: Fraction(float.fromhex(value)) for i, value in enumerate(lines[count+1:])}
                reference = solve({'metadata': {'size': size}, 'a': matrix, 'b': rhs}, 160)
                results = []
                for bits in (256, 512):
                    result = self.run_solver(stimulus, bits)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    output = [line.split() for line in result.stdout.splitlines()]
                    solution = {int(i): Fraction(float.fromhex(value)) for i, value in output}
                    self.assertEqual(len(output), size)
                    self.assertEqual(set(solution), set(reference))
                    for i in reference:
                        error = abs(solution[i]-reference[i])/max(Fraction(1), abs(reference[i]))
                        self.assertLessEqual(error, Fraction(1, 2**52), (name, bits, i))
                    results.append(solution)
                self.assertEqual(*results)

    def test_pivot_with_analytic_solution(self):
        result = self.run_solver('2 3\n1 2 1\n2 1 1\n2 2 1\n2\n3\n')
        self.assertEqual(result.returncode, 0)
        self.assertEqual([float.fromhex(line.split()[1]) for line in result.stdout.splitlines()], [1, 2])

    def test_invalid_or_singular_inputs_fail(self):
        for stimulus, bits in (
            ('2 4\n1 1 1\n1 2 1\n2 1 2\n2 2 2\n2\n4\n', 256),
            ('1 1\n1 1 nan\n1\n', 256),
            ('1 1\n1 1 1\ninf\n', 256),
            ('1 1\n2 1 1\n1\n', 256),
            ('1 1\n1 1 1\n1\n', 32),
        ):
            with self.subTest(stimulus=stimulus, bits=bits):
                result = self.run_solver(stimulus, bits)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
