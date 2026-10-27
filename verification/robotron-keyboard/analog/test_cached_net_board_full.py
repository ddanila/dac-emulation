"""Check retained complete-review identity; this does not repeat the hour-long replay."""
import json,math,unittest
from pathlib import Path
from retained_evidence import check
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent

class CachedNetBoardFullTests(unittest.TestCase):
    def test_complete_review_receipt_and_reference(self):
        root=HERE/'reports/cached-net-board-full';check(root)
        reference=HERE/'reports/net-board';check(reference)
        r=json.loads((root/'assessment.json').read_text())
        self.assertTrue(r['completed']);self.assertTrue(r['completeAssessmentExactlyEqual'])
        self.assertEqual(r['referenceSha256'],sha(reference/'assessment.json'))
        self.assertEqual(json.dumps(r['assessment'],sort_keys=True),json.dumps(json.loads((reference/'assessment.json').read_text()),sort_keys=True))
        self.assertGreater(r['cacheHits'],0);self.assertGreater(r['cacheMisses'],0)
        self.assertTrue(math.isfinite(r['elapsedSeconds']) and r['elapsedSeconds']>0)
        for name,digest in r['sources'].items():self.assertEqual(sha(HERE/name),digest)

if __name__=='__main__':unittest.main()
