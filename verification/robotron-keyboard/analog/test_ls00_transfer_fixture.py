"""Reject incomplete transfer sweeps and preserve branch differences."""
import unittest
from ls00_transfer_fixture import read_sweep, compare


class TransferFixtureTests(unittest.TestCase):
    def fixture(self):
        return 'v-sweep v(y) i(Vin)\n' + '\n'.join(f'{i/1000:.4f} {3-i/1000} -0.0001' for i in range(1601))

    def test_sweep_direction(self):
        text = self.fixture(); lines = text.splitlines()
        forward = read_sweep(text, .001, False)
        reverse = read_sweep('\n'.join(lines[:1] + lines[1:][::-1]), .001, True)
        self.assertEqual(compare(forward, reverse)['maximumOutputDifferenceVolts'], 0)
        reverse[100][1] -= 2
        result = compare(forward, reverse)
        self.assertEqual(result['maximumOutputDifferenceVolts'], 2)
        self.assertEqual(result['inputVolts'], .1)

    def test_rejects_missing_reordered_and_nonfinite_points(self):
        text = self.fixture(); lines = text.splitlines()
        for bad in ['\n'.join(lines[:-1]), '\n'.join(lines[:10] + [lines[9]] + lines[11:]),
                    text.replace('v(y)', 'v(a)'), text.replace('-0.0001', 'nan')]:
            with self.assertRaises(ValueError): read_sweep(bad, .001, False)
        with self.assertRaises(ValueError): read_sweep(text, .001, True)
        with self.assertRaises(ValueError): compare([[0,1,0]], [[.1,1,0]])


if __name__ == '__main__': unittest.main()
