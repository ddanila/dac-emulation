#!/usr/bin/env python3
"""Reject incomplete primitive state, faults and continuation evidence."""
from pathlib import Path
import shutil,tempfile,unittest
from primitive_probe import review,parse_snapshot
HERE=Path(__file__).resolve().parent

class PrimitiveProbe(unittest.TestCase):
    def test_retained_controls(self):
        r=review(HERE/'reports/primitive-payload')
        self.assertTrue(r['simulationOutputExactlyEqual']);self.assertEqual(r['restoredFaults'],10)

    def test_missing_fault_bad_payload_and_changed_continuation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for p in (HERE/'reports/primitive-payload').glob('*.std*'):shutil.copy2(p,root/p.name)
            path=root/'corrupt.stdout';original=path.read_text()
            changes=[('VPM_FAULT 1 0 1 1\n',''),('VPM_FAULT 2 2 1 1','VPM_FAULT 2 2 1 0'),
                     ('CHANGE 1000','CHANGE 1001'),('VPR_END 2 1','VPR_END 1 1'),
                     ('4 8 8 10110111','4 8 8 1011011'),('VPM_RESTORED','VPM_REPEAT')]
            for old,new in changes:
                bad=original.replace(old,new,1);self.assertNotEqual(bad,original);path.write_text(bad)
                with self.assertRaises(ValueError):review(root)
            path.write_text(original);(root/'enabled.stderr').write_text('warning\n')
            with self.assertRaises(ValueError):review(root)

    def test_snapshot_requires_matching_wrapper_and_typed_payload(self):
        lines=['VPR_BEGIN 1 0','VPR_EVENT 0 active 0 1 1 2 0','VPR_DATA 2 0x1000 4 8 8 00110011','VPR_END 1 0']
        self.assertEqual(parse_snapshot(lines)['events'][0]['base'],4)
        for old,new in [('VPR_DATA 2','VPR_DATA 1'),('8 8 00110011','8 7 0011001'),('00110011','00110014'),('VPR_EVENT 0 active','VPR_EVENT 0 invalid')]:
            with self.assertRaises(ValueError):parse_snapshot([l.replace(old,new) for l in lines])

if __name__=='__main__':unittest.main()
