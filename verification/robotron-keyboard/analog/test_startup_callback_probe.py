#!/usr/bin/env python3
"""Reject incomplete startup lifetime/fault and continuation evidence."""
from pathlib import Path
import shutil
import tempfile
import unittest
from startup_callback_probe import review
HERE=Path(__file__).resolve().parent

class StartupCallbackReview(unittest.TestCase):
    def test_retained_controls(self):
        result=review(HERE/'reports/startup-callback')
        self.assertTrue(result['timestampedCallbackOutputExactlyEqual'])
        self.assertEqual(result['restoredFaults'],32)
        self.assertEqual(result['callbackIdentityObservations'],30)

    def test_reject_wrong_lifetime_fault_or_continuation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for src in (HERE/'reports/startup-callback').glob('*.std*'):shutil.copy2(src,root/src.name)
            path=root/'corrupt.stdout';original=path.read_text()
            fault=next(l for l in original.splitlines() if l.startswith('VS_FAULT '))
            variants=[original.replace(fault+'\n','',1),original.replace(fault,fault[:-1]+'0',1),
                      original.replace('VS_LINK 4 0 0','VS_LINK 4 0 1'),
                      original.replace('CALLBACK 0 0 C','CALLBACK 0 1 C'),
                      original.replace('CALLBACK 0 0 A\n','')+'CALLBACK 0 0 A\n',
                      original.replace('VS_LINK 2 2 3','VS_LINK 2 2 4'),original+'VS_UNKNOWN 1\n']
            for bad in variants:
                self.assertNotEqual(bad,original)
                path.write_text(bad)
                with self.assertRaises(ValueError):review(root)
            path.write_text(original);(root/'enabled.stderr').write_text('unexpected diagnostic\n')
            with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
