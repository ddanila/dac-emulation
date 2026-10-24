import unittest
from rollback_audit_log import analyze

A='ROLLBACK_AUDIT accept time='
C='ROLLBACK_AUDIT client phase={phase} time=0x1p+0 name=hdl priority=1 index=1 count=2 breakpoint=0x1p+10'


class RollbackLogTests(unittest.TestCase):
    def test_rejected_trial_then_successful_retry(self):
        result=analyze([A+'0x0p+0','ROLLBACK_AUDIT reject kind=lte time=0x1p+1 delta=0x1p+1 target_delta=0x1p+0',C.format(phase='before'),C.format(phase='after'),A+'0x1p+0'])
        self.assertEqual(result['rejectedTrials'],{'lte':1})
        self.assertEqual(result['clientCalls'],{'hdl':1})
        self.assertEqual(result['trialsRejectedAfterClientCallbacks'],{})
        self.assertEqual(result['unprotectedClientCalls'],0)

    def test_client_requested_breakpoint_is_reported_not_hidden(self):
        result=analyze([A+'0x0p+0',C.format(phase='before'),C.format(phase='after'),
            'ROLLBACK_AUDIT reject kind=breakpoint time=0x1p+0 delta=0x1p+0 target=0x1p-1',A+'0x1p-1'])
        self.assertEqual(result['trialsRejectedAfterClientCallbacks'],{'breakpoint':1})
        self.assertFalse(result['qualified'])

    def test_rejects_missing_return_malformed_and_truncated_audits(self):
        for lines in ([A+'0x0p+0',C.format(phase='before'),A+'0x1p+0'],
                      [A+'0x0p+0',C.format(phase='after'),A+'0x1p+0'],
                      [A+'0x0p+0','ROLLBACK_AUDIT reject kind=lte time=nan'],
                      [A+'0x0p+0',C.format(phase='before'),C.format(phase='after')]):
            with self.subTest(lines=lines),self.assertRaises(ValueError):analyze(lines)


if __name__=='__main__':unittest.main()
