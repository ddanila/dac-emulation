"""Reject missing WR activity, mismatched enables and incomplete waveforms."""
from pathlib import Path
import tempfile
import unittest

from write_control_observation import measure


class WriteObservationTests(unittest.TestCase):
    def fixture(self, directory, final='01'):
        trace = Path(directory) / 'wr.txt'
        rows = []
        for i in range(121):
            time = i * 50e-9
            state = '01' if i < 40 else '10' if i < 80 else final
            low, high = (5 * int(bit) for bit in state)
            rows.append([time, .15 if low else 4.9, low, high,
                         .000675 if low else 0, .00001 if high else 0, 5])
        self.write(trace, rows)
        log = 'WR_DRIVE 0 01\nWR_DRIVE 2000000 10\nWR_DRIVE 4000000 ' + final + '\n'
        return trace, rows, log

    def write(self, path, rows):
        path.write_text('time v(n_WR_N) v(wr_low) v(wr_high) @bwr_low[i] @bwr_high[i] v(n_p5V)\n' +
                        '\n'.join(' '.join(format(x, '.17g') for x in row) for row in rows) + '\n')

    def test_activity_and_release(self):
        with tempfile.TemporaryDirectory() as directory:
            trace, _, log = self.fixture(directory, '00')
            result = measure(log, trace, 50, 6e-6, start_seconds=1e-6)
            self.assertTrue(result['passed'])
            self.assertFalse(result['qualified'])
            self.assertTrue(all(result['checkedSamples'].values()))

    def test_first_voltage_dac_and_current_mismatch(self):
        for column, value, message in ((1, 2.1, 'voltage differs'),
                                       (2, 0, 'ownership differs'),
                                       (5, .001, 'still sources')):
            with self.subTest(column=column), tempfile.TemporaryDirectory() as directory:
                trace, rows, log = self.fixture(directory)
                rows[60][column] = value
                self.write(trace, rows)
                with self.assertRaisesRegex(ValueError, message):
                    measure(log, trace, 50, 6e-6, start_seconds=1e-6)

    def test_missing_activity_unknowns_and_truncated_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            trace, rows, log = self.fixture(directory)
            with self.assertRaisesRegex(ValueError, 'Unknown WR'):
                measure(log.replace('2000000 10', '2000000 xx'), trace, 50, 6e-6, start_seconds=1e-6)
            self.write(trace, rows[:-1])
            with self.assertRaisesRegex(ValueError, 'extent'):
                measure(log, trace, 50, 6e-6, start_seconds=1e-6)
            self.write(trace, [rows[0], *rows[2:]])
            with self.assertRaisesRegex(ValueError, 'gap'):
                measure(log, trace, 50, 6e-6, start_seconds=1e-6)
            self.write(trace, [[r[0], 4.9, 0, 5, 0, .00001, 5] for r in rows])
            with self.assertRaisesRegex(ValueError, 'not both observed'):
                measure('WR_DRIVE 0 01\n', trace, 50, 6e-6, start_seconds=1e-6)


if __name__ == '__main__':
    unittest.main()
