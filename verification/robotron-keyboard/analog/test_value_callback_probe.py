#!/usr/bin/env python3
"""Reject missing faults, changed continuation and stale callback lifetimes."""
from pathlib import Path
import shutil
import tempfile
import unittest
from value_callback_probe import review
HERE=Path(__file__).resolve().parent


class ValueCallbackReview(unittest.TestCase):
    def test_retained_controls(self):
        result=review(HERE/'reports/value-callback')
        self.assertTrue(result['timestampedCallbackOutputExactlyEqual'])
        self.assertEqual(result['restoredFaults'],48)
        self.assertEqual(result['callbackIdentityObservations'],36)

    def test_reject_missing_or_wrong_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for src in (HERE/'reports/value-callback').glob('*.std*'):shutil.copy2(src,root/src.name)
            path=root/'corrupt.stdout';original=path.read_text()
            lines=original.splitlines();fault=next(l for l in lines if l.startswith('VQ_FAULT '));link=next(l for l in lines if l.startswith('VQ_LINK 2 0 '))
            variants=[original.replace(fault+'\n','',1),original.replace(fault,fault[:-1]+'0',1),
                      original.replace(link,'VQ_LINK 2 0 1',1),
                      original.replace('CALLBACK 0 9000 B 8 0','CALLBACK 0 9000 B 7 0'),
                      original+'VQ_UNKNOWN 1\n']
            for bad in variants:
                path.write_text(bad)
                with self.assertRaises(ValueError):review(root)
            path.write_text(original);(root/'enabled.stderr').write_text('unexpected runtime warning\n')
            with self.assertRaises(ValueError):review(root)


if __name__=='__main__':unittest.main()
