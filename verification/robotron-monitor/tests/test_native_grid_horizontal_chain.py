"""Check horizontal-chain binning on an unfinished real raw trace."""
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import native_grid_horizontal_chain as chain


class NativeGridHorizontalChainTests(unittest.TestCase):
    def test_partial_rows_and_periodic_drive_are_separate_from_tp17_swing(self):
        names = ('time', *chain.PROBES)
        header = ('Title: synthetic unfinished trace\nFlags: real\n'
                  f'No. Variables: {len(names)}\nNo. Points: 0\nVariables:\n'
                  + ''.join(f'\t{i}\t{name}\tvoltage\n'
                            for i, name in enumerate(names))
                  + 'Binary:\n').encode()
        rows = []
        for time_s, drive, hot, sync in ((0, 0, 0, -10),
                                         (.0004, 20, 200, 3),
                                         (.0008, 0, 0, -80),
                                         (.0012, 20, 200, 3)):
            values = {'v(h_drivecol)': drive, 'v(h_hot)': hot,
                      'v(h_sync)': sync}
            rows.append(struct.pack('='+str(len(names))+'d', time_s,
                                    *(values.get(name, 0) for name in chain.PROBES)))
        raw = header+b''.join(rows)+b'abc'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'trace.raw'
            path.write_bytes(raw)
            report = chain.summarize(path)
        self.assertEqual(report['input_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual((report['declared_points'], report['complete_rows'],
                          report['trailing_bytes']), (0, 4, 3))
        self.assertEqual([row['upcrossings']['v(h_hot)'] for row in report['bins']],
                         [1, 1])
        self.assertEqual(report['bins'][0]['minimum']['v(h_sync)'], -80)
        self.assertEqual(report['bins'][0]['maximum']['v(h_sync)'], 3)


if __name__ == '__main__':
    unittest.main()
