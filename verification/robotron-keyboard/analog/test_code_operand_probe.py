import copy
import shutil
import tempfile
import unittest
from pathlib import Path
import code_operand_probe as probe

ROOT = Path(__file__).resolve().parent/'reports/code-operands'


class CodeOperands(unittest.TestCase):
    def test_retained_complete_reconstruction(self):
        result = probe.review(ROOT)
        self.assertTrue(result['completeAllocatedOperandCoverage'])
        self.assertTrue(result['denseAndDeltaExactlyEqual'])
        self.assertGreater(result['allocatedInstructions'], 1024)

    def test_delta_reference_and_redundancy(self):
        reference = {1: dict(opcode='of_ZOMBIE',fields={})}
        delta = dict(mode='D',total=1,rows={})
        self.assertEqual(probe.reconstruct(reference,delta),reference)
        for changed in (dict(delta,total=2),dict(delta,rows=reference),dict(delta,rows={2:reference[1]})):
            with self.assertRaises(ValueError):
                probe.reconstruct(reference,changed)

    def test_lossy_delta_and_missing_restoration_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for p in ROOT.iterdir():
                if p.suffix in ('.stdout','.stderr','.xz') or p.name=='probe.vvp':
                    shutil.copy2(p,root/p.name)
            p=root/'corrupt.stdout';original=probe.stdout(root,'corrupt')
            start=original.index('VOM_CHANGED 0\n')
            a=original.index('VCO_BEGIN D ',start)
            b=original.index('\n',a)
            words=original[a:b].split();self.assertEqual(words[-1],'1')
            end=original.index('VCO_END 1\n',b)+len('VCO_END 1\n')
            p.write_text(original[:a]+' '.join(words[:-1]+['0'])+'\nVCO_END 0\n'+original[end:])
            with self.assertRaises(ValueError):
                probe.review(root)
            a=original.index('VOM_RESTORED\n',start)
            b=original.index('VOM_FAULT 0 ',a)
            p.write_text(original[:a]+original[b:])
            with self.assertRaises(ValueError):
                probe.review(root)


if __name__=='__main__':
    unittest.main()
