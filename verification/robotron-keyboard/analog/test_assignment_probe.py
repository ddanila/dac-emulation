#!/usr/bin/env python3
"""Reject missing assignment payloads, changed faults and lost continuation."""
from pathlib import Path
import shutil,tempfile,unittest
from assignment_probe import review,parse_snapshot
HERE=Path(__file__).resolve().parent

class AssignmentProbe(unittest.TestCase):
    def test_retained_controls(self):
        r=review(HERE/'reports/assignment-payload')
        self.assertTrue(r['simulationOutputExactlyEqual']);self.assertEqual(r['restoredFaults'],9)

    def test_reject_missing_fault_payload_or_changed_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for p in (HERE/'reports/assignment-payload').glob('*.std*'):shutil.copy2(p,root/p.name)
            path=root/'corrupt.stdout';original=path.read_text()
            variants=[original.replace('VAM_FAULT 4 0 1 1\n','',1),
                      original.replace('VAM_FAULT 8 2 1 1','VAM_FAULT 8 2 1 0'),
                      original.replace('VALUES 16000 c5','VALUES 16000 ac'),
                      original.replace('CHANGE 10000 a5','CHANGE 9000 a5'),
                      original.replace('VAP_END 6 1 ','VAP_END 6 0 ',1),
                      original.replace('200336033166','200836033166',1),
                      original.replace('VAM_RESTORED','VAM_REPEAT',1),
                      original+'VAM_UNKNOWN 1\n']
            for bad in variants:
                self.assertNotEqual(original,bad);path.write_text(bad)
                with self.assertRaises(ValueError):review(root)
            path.write_text(original);(root/'disabled.stderr').write_text('warning\n')
            with self.assertRaises(ValueError):review(root)

    def test_snapshot_rejects_aliases_and_partial_vectors(self):
        event='VAP_EVENT 0 active 0 1 4 0x1000 0 4 8 4 0011'
        self.assertEqual(parse_snapshot(['VAP_BEGIN 1 0',event,'VAP_END 1 0 0'])['events'][0]['base'],4)
        for data in [event.replace('0011','001'),event.replace(' 4 0011',' -1 0011'),event.replace('0x1000','(nil)')]:
            with self.assertRaises(ValueError):parse_snapshot(['VAP_BEGIN 1 0',data,'VAP_END 1 0 0'])
        with self.assertRaises(ValueError):parse_snapshot(['VAP_BEGIN 1 0',event,event,'VAP_END 2 0 0'])

if __name__=='__main__':unittest.main()
