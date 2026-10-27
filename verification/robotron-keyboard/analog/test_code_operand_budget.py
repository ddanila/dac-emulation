import shutil
import tempfile
import unittest
from pathlib import Path
import code_operand_budget as budget

ROOT=Path(__file__).resolve().parent/'reports/code-operand-budget'


class OperandBudget(unittest.TestCase):
    def test_complete_profile_and_explicit_projection(self):
        result=budget.review(ROOT)
        self.assertTrue(result['compiledBoardOperandImageComplete'])
        self.assertTrue(result['denseAndDeltaExactlyEqual'])
        projection=result['projection']
        self.assertGreater(projection['recommendedCaptureTimeoutSeconds'],projection['estimatedCombinedProducerSeconds'])
        self.assertTrue(projection['unchangedCodeAssumption'])
        self.assertLess(projection['unchangedCodeDeltaLogBytesUpperEstimate'],projection['fullLogBytes'])

    def test_partial_or_executed_profile_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for p in ROOT.iterdir():
                if p.is_file():shutil.copy2(p,root/p.name)
            original=(root/'stdout.txt').read_text()
            (root/'stdout.txt').write_text('FIRST_FETCH 1\n'+original)
            with self.assertRaises(ValueError):budget.review(root)
            (root/'stdout.txt').write_text(original)
            raw=budget.text(root/'full.txt')
            (root/'full.txt').write_text(raw.replace('number=', 'wrong=', 1))
            with self.assertRaises(ValueError):budget.review(root)


if __name__=='__main__':unittest.main()
