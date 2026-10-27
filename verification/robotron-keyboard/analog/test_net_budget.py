import re
import shutil
import tempfile
import unittest
from pathlib import Path
import net_budget as budget
ROOT=Path(__file__).resolve().parent/'reports/net-budget'


class NetBudget(unittest.TestCase):
    def test_complete_graph_and_cross_references(self):
        result=budget.review(ROOT)
        self.assertTrue(result['completeAllocatedGraphObserved'])
        self.assertGreater(result['crossReferences']['codeNetOperands'],0)
        self.assertGreater(result['crossReferences']['arrayReadPortDestinations'],0)
        self.assertNotEqual(result['allocatedNodes'],result['compiledProfile']['networkDeclarationCount'])
        self.assertGreater(result['projection']['fullGraphLogBytes'],4*1024**3)
    def test_unallocated_array_and_code_targets_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for p in ROOT.iterdir():
                if p.is_file():shutil.copy2(p,root/p.name)
            p=root/'arrays.txt';original=p.read_text();lines=original.splitlines()
            i=next(i for i,l in enumerate(lines) if l.startswith('VAR_PORT '));a=lines[i].split();a[4]='0x4';lines[i]=' '.join(a)
            p.write_text('\n'.join(lines)+'\n')
            with self.assertRaises(ValueError):budget.review(root)
            p.write_text(original)
            p=root/'operands.txt';p.write_text(re.sub(r' net=\d+', ' net=4',p.read_text(),count=1))
            with self.assertRaises(ValueError):budget.review(root)
    def test_execution_marker_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for p in ROOT.iterdir():
                if p.is_file():shutil.copy2(p,root/p.name)
            p=root/'stdout.txt';p.write_text(p.read_text()+'FIRST_FETCH 1\n')
            with self.assertRaises(ValueError):budget.review(root)


if __name__=='__main__':unittest.main()
