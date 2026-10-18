import hashlib
import tempfile
import unittest
from pathlib import Path
from host_transition_windows import extract, crossings


class WindowTests(unittest.TestCase):
    def test_exact_bytes_and_brackets(self):
        data=b'time v(x)\n0 0\n1 1.0000000000000001\n2 2\n3 3\n4 4\n'
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'trace.txt';p.write_bytes(data)
            header,windows=extract(p,['v(x)'],[2,2],.5,hashlib.sha256(data).hexdigest())
            self.assertEqual(len(windows),1)
            self.assertEqual(header+b''.join(r[1] for r in windows[0]['rows']),
                             b'time v(x)\n1 1.0000000000000001\n2 2\n3 3\n')
            for centers,radius,digest in (([2],.5,'wrong'),([4],.5,hashlib.sha256(data).hexdigest()),
                                          ([2],0,hashlib.sha256(data).hexdigest())):
                with self.assertRaises(ValueError):extract(p,['v(x)'],centers,radius,digest)

    def test_interpolated_crossings_keep_pulse_edges(self):
        r=crossings([(0,b'0 0'),(1,b'1 2'),(2,b'2 0')],1)
        self.assertEqual([x['direction']for x in r],['rising','falling'])
        self.assertAlmostEqual(r[0]['timeSeconds'],.7)
        self.assertAlmostEqual(r[1]['timeSeconds'],1.3)


if __name__=='__main__':unittest.main()
