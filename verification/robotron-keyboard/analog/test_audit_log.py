import lzma
from pathlib import Path
import tempfile
import unittest
from audit_log import complete, equal, BUS, AUDIT
from test_newton_retry_review import fixture


class StreamingLogTests(unittest.TestCase):
    def test_compressed_exact_and_extra_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, control, _ = fixture(Path(tmp))
            a = control/'ngspice.log'; b = control/'copy.log'
            with a.open('rb') as source, lzma.open(str(b)+'.xz', 'wb') as out:
                out.write(source.read())
            self.assertTrue(equal(a,b)); self.assertEqual(complete(a),complete(b))
            with lzma.open(str(b)+'.xz', 'at') as out:
                out.write('TIME_AUDIT advance target=0 actual=0 base=0 tick=1e-12 pending=0\n')
            self.assertFalse(equal(a,b,AUDIT))

    def test_truncation_diagnostics_and_malformed_events(self):
        mutations = [lambda s:s.replace('No. of Data Rows : 3\n',''),
                     lambda s:s+'No. of Data Rows : 3\n',
                     lambda s:s+'fatal: solver failure\n',
                     lambda s:s+'SORRY: unsupported HDL\n',
                     lambda s:s.replace('BUS_SAMPLE 1003000000 0000 af 0 1 0','BUS_SAMPLE broken'),
                     lambda s:s.replace('BUS_EDGE_PS 1003000000','BUS_EDGE_PS broken'),
                     lambda s:s.replace('BUS_LATCH 1003000000 af af\n','')]
        for mutation in mutations:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                _,control,_=fixture(Path(tmp));p=control/'ngspice.log';p.write_text(mutation(p.read_text()))
                with self.assertRaises(ValueError):complete(p)

    def test_truncated_xz_is_not_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,control,_=fixture(Path(tmp));p=control/'ngspice.log'
            data=lzma.compress(p.read_bytes());p.unlink()
            Path(str(p)+'.xz').write_bytes(data[:-8])
            with self.assertRaises((EOFError,lzma.LZMAError)):complete(p)

    def test_changed_event_and_bad_latch(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,control,_=fixture(Path(tmp));a=control/'ngspice.log';b=control/'other.log'
            b.write_text(a.read_text().replace('BUS_LATCH 1003000000 af af','BUS_LATCH 1003000000 af 00'))
            self.assertFalse(equal(a,b,BUS));self.assertFalse(complete(b)['latchesMatch'])

if __name__=='__main__':unittest.main()
