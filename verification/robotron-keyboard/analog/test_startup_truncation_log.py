import unittest
from startup_truncation_log import diagnostic

class StartupLogTests(unittest.TestCase):
    def test_structured_startup_error_audit_is_not_failure(self):
        keys = ('time state delta dt0 dt1 dt2 order before proposed currenttol '
                'chargetol abstol reltol chgtol difference q0 q1 q2 q3').split()
        record = 'STARTUP_TRUNC error ' + ' '.join(k+'='+('2' if k in ('state','order') else '0x1.2p-3') for k in keys)
        self.assertIsNone(diagnostic(record))
        for line in (record+' fatal', record.replace('q3=', 'missing='), 'WARNING: '+record):
            self.assertEqual(diagnostic(line), line)
        self.assertEqual(diagnostic(record+'\nTimestep too small'), 'Timestep too small')


if __name__ == "__main__":
    unittest.main()
