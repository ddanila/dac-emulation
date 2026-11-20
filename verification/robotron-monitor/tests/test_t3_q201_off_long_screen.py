from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import t3_q201_off_long_screen as screen


class LongScreenRawTests(unittest.TestCase):
    def trace(self, path, rows):
        names = ('time', 'v(eht)', 'v(h_sync)', 'v(h_hot)')
        header = ('Title: field diagnostic\nFlags: real\nNo. Variables: 4\n'
                  f'No. Points: {len(rows)}\nVariables:\n')
        header += ''.join(f'{i} {name} voltage\n'
                          for i, name in enumerate(names))
        header += 'Binary:\n'
        path.write_bytes(header.encode()+b''.join(struct.pack('=4d', *row)
                                               for row in rows))

    def test_equal_time_event_has_no_elapsed_weight(self):
        rows = ((0., 0., 0., 0.), (.001, 100., 0., 0.),
                (.001, 200., 0., 200.), (.0195, 200., 0., 0.),
                (.039, 300., 0., 0.))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'trace.raw'
            self.trace(path, rows)
            result = screen.summarize_raw(path)
        self.assertEqual(result['complete_rows'], len(rows))
        self.assertEqual(result['equal_time_event_rows'], 1)
        self.assertEqual(result['trailing_bytes'], 0)
        self.assertAlmostEqual(result['fields'][0]['duration_s'], .0195)
        self.assertAlmostEqual(result['fields'][0]['eht_time_mean_v'],
                               (.001*50+.0185*200)/.0195)
        self.assertEqual(result['fields'][0]['h_hot_upcrossings_100v'], 1)

    def test_backward_time_is_rejected(self):
        rows = ((0., 0., 0., 0.), (.001, 100., 0., 0.),
                (.0009, 100., 0., 0.))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'trace.raw'
            self.trace(path, rows)
            with self.assertRaisesRegex(ValueError, 'backward raw time'):
                screen.summarize_raw(path)


if __name__ == '__main__':
    unittest.main()
