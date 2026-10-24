import io
import struct
import unittest
from raw_waveform import header, rows


class RawWaveformTests(unittest.TestCase):
    def test_pipe_header_and_complete_samples(self):
        stream = io.BytesIO(b'Title: test\nPlotname: Transient Analysis\nFlags: real\nNo. Variables: 2\nNo. Points: 0\nVariables:\n0 time time\n1 v(out) voltage\nBinary:\n' + struct.pack('=4d', 0, 5, 1, 4))
        self.assertEqual(header(stream), (['time', 'v(out)'], 0))
        self.assertEqual(list(rows(stream, 2, 2)), [(0, 5), (1, 4)])

    def test_rejects_incomplete_or_extra_samples_and_old_pipe_count_suffix(self):
        data = struct.pack('=4d', 0, 5, 1, 4)
        for bad in (data[:-1], data+b'2', data+data):
            with self.subTest(data=bad), self.assertRaises(ValueError):
                list(rows(io.BytesIO(bad), 2, 2))

    def test_rejects_nonfinite_or_reversed_time(self):
        for data in ((0, 5, 0, 4), (1, 5, 0, 4), (0, 5, 1, float('nan'))):
            with self.subTest(data=data), self.assertRaises(ValueError):
                list(rows(io.BytesIO(struct.pack('=4d', *data)), 2, 2))


if __name__ == '__main__':
    unittest.main()
