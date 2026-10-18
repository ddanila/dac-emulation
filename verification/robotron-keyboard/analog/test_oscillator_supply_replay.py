"""Guard the recorded-supply boundary independently of the circuit solver."""
from pathlib import Path
import tempfile
import unittest

from oscillator_supply_replay import check_supply, supply_samples


class SupplyReplayTests(unittest.TestCase):
    def test_retains_nonuniform_points_and_only_identical_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.txt'
            source.write_text('time v(n_p5V) ignored\n0 0 9\n0.1 2 8\n0.1 2 7\n0.4 5 6\n')
            times, volts, report = supply_samples(source, root / 'supply.txt')
            self.assertEqual(times, [0, .1, .4])
            self.assertEqual(volts, [0, 2, 5])
            self.assertEqual(report['identicalDuplicateSamples'], 1)
            self.assertEqual((root / 'supply.txt').read_text().splitlines()[:3],
                             ['0 0', '0.1 2', '0.4 5'])
            trace = root / 'trace.txt'
            trace.write_text('time v(n_CLK) v(n_p5V)\n0 0 0\n0.05 1 1\n0.25 2 3.5\n0.4 0 5\n')
            self.assertLess(check_supply(trace, times, volts)['maximumInterpolationErrorVolts'], 1e-14)

    def test_invalid_source_is_rejected(self):
        cases = ['0 0\n0 1\n1 5\n', '0 0\n1 5\n0.5 3\n',
                 '0.1 0\n1 5\n', '0 0\n1 nan\n', '0 0\n']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for rows in cases:
                with self.subTest(rows=rows):
                    (root / 'source.txt').write_text('time v(n_p5V)\n' + rows)
                    with self.assertRaises(ValueError):
                        supply_samples(root / 'source.txt', root / 'supply.txt')

    def test_wrong_or_incomplete_replay_is_rejected(self):
        cases = ['0 0 0\n1 0 4.99\n', '0 0 0\n0.5 0 2.5\n',
                 '0.1 0 0.5\n1 0 5\n', '0 0 0\n1 0 nan\n',
                 '0 0 0\n0.5 0 2.5\n0.4 0 2\n1 0 5\n']
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / 'trace.txt'
            for rows in cases:
                with self.subTest(rows=rows):
                    trace.write_text('time v(n_CLK) v(n_p5V)\n' + rows)
                    with self.assertRaises(ValueError):
                        check_supply(trace, [0, 1], [0, 5])


if __name__ == '__main__':
    unittest.main()
