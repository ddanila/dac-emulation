import shutil
import tempfile
import unittest
from pathlib import Path
import array_budget as budget
ROOT=Path(__file__).resolve().parent/'reports/array-budget'


class ArrayBudget(unittest.TestCase):
    def test_complete_profile_and_storage_projection(self):
        result=budget.review(ROOT)
        self.assertTrue(result['compiledBoardArrayImageComplete'])
        self.assertTrue(result['observationExactlyRepeatable'])
        self.assertGreater(result['projection']['uncachedImageLogBytes'],4*1024**3)
        self.assertTrue(result['projection']['excludesLaterWordHandleAllocation'])

    def test_execution_and_missing_memory_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for p in ROOT.iterdir():
                if p.is_file():shutil.copy2(p,root/p.name)
            original=(root/'stdout.txt').read_text()
            (root/'stdout.txt').write_text('FIRST_FETCH 1\n'+original)
            with self.assertRaises(ValueError):budget.review(root)
            (root/'stdout.txt').write_text(original)
            raw=(root/'before.txt').read_text()
            lines=raw.splitlines()
            index=next(i for i,l in enumerate(lines) if l.startswith('VAR_WORD '))
            del lines[index]
            for name in ('before','after'):(root/(name+'.txt')).write_text('\n'.join(lines)+'\n')
            with self.assertRaises(ValueError):budget.review(root)


if __name__=='__main__':unittest.main()
