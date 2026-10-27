import lzma,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import audit_log as legacy
import fast_audit_log as fast
from test_newton_retry_review import fixture

class FastAudit(unittest.TestCase):
    def test_diagnostics_exact_including_unicode_and_filter_exceptions(self):
        phrases=['warning','error','failed','fatal','singular','no vlog_startup_routines','timestep too small','simulation(s) aborted','XSPICE time is behind vtime','ſingular','WARNİNG','Truncation error correction, charge based, is selected:','Truncation error correction, voltage based, is selected:','STARTUP_TRUNC error malformed','FILTER_TRUNC error malformed','VT_FLAGS_SPARSE 512 1 0:0','VT_SOURCE 0 -','SORRY: unsupported']
        for phrase in phrases:
            for text in (phrase,phrase.upper(),phrase+'\n', 'before\n'+phrase+'\nafter'):
                self.assertEqual(fast.diagnostic(text),legacy.diagnostic(text),text)
        with patch('fast_audit_log.SUPPORTED',False),patch('fast_audit_log.legacy_diagnostic',return_value='new diagnostic') as call:
            self.assertEqual(fast.diagnostic('previously harmless'),'new diagnostic');call.assert_called_once()

    def test_complete_observer_log_and_mutations_match_original(self):
        with tempfile.TemporaryDirectory() as d:
            _,root,_=fixture(Path(d));path=root/'ngspice.log';original=path.read_text()
            observer='VT_FLAGS_SPARSE 512 2 0:0 511:3\n'*1000
            cases=[original+observer,original+'fatal: failure\n',original+'SORRY: unsupported\n',original+'No. of Data Rows : 3\n',original.replace('BUS_LATCH 1003000000 af af','BUS_LATCH 1003000000 af 00'),original.replace('BUS_EDGE_PS 1003000000','BUS_EDGE_PS broken')]
            for case in cases:
                path.write_text(case)
                def outcome(function):
                    try:return ('value',function(path))
                    except ValueError as exc:return ('error',str(exc))
                self.assertEqual(outcome(fast.scan),outcome(legacy.scan))
                self.assertEqual(outcome(fast.complete),outcome(legacy.complete))
            with patch('fast_audit_log.SUPPORTED',False),patch('fast_audit_log.legacy.scan',return_value={'fallback':True}):
                self.assertEqual(fast.scan(path),{'fallback':True})
            with patch('fast_audit_log.SUPPORTED',False),patch('fast_audit_log.legacy.complete',return_value={'fallback':True}):
                self.assertEqual(fast.complete(path),{'fallback':True})

    def test_truncated_compressed_log_still_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'log';Path(str(path)+'.xz').write_bytes(lzma.compress(b'VT_END 0\n'*1000)[:-8])
            with self.assertRaises((EOFError,lzma.LZMAError)):fast.complete(path)

if __name__=='__main__':unittest.main()
