import json,os,tempfile,unittest
from pathlib import Path
from parameter_late_refusal_core_review import refusal
from parameter_late_refusal_review import review
HERE=Path(__file__).resolve().parent

class LateRefusalReview(unittest.TestCase):
    def test_refusal_boundaries(self):
        first='VB_PARAMETER_LATE round=1 time=5e-6 refused=1 cache_unchanged=1'
        second='VB_PARAMETER_LATE round=2 time=6e-6 refused=1 cache_unchanged=1'
        self.assertEqual(refusal(first,1),5e-6)
        self.assertEqual(refusal(second,2),6e-6)
        for bad in [first.replace('5e-6','4e-6'),first.replace('5e-6','nan'),first.replace('refused=1','refused=0'),first.replace('cache_unchanged=1','cache_unchanged=0'),first.replace('round=1','round=2'),first+' extra=1']:
            with self.assertRaises(ValueError):refusal(bad,1)
        with self.assertRaises(ValueError):refusal(second.replace('6e-6','5e-6'),2)

    def test_complete_capture_replay(self):
        root=Path(os.environ.get('ROBOTRON_PARAMETER_LATE_REFUSAL_REPORT',HERE/'reports/parameter-late-refusal-controls'))
        if not (root/'assessment.json').exists():self.skipTest('Complete retained campaign not available yet')
        self.assertEqual(review(root),json.loads((root/'assessment.json').read_text()))

if __name__=='__main__':unittest.main()
