import unittest
from pathlib import Path
import array_compact_probe as compact
import array_compact_budget as budget
HERE=Path(__file__).resolve().parent


class CompactArray(unittest.TestCase):
    def frames(self):
        lines=(HERE/'reports/array-compact/corrupt.stdout').read_text().splitlines()
        frames=[];current=None
        for line in lines:
            if line.startswith('VAC_BEGIN '):current=[]
            if current is not None:current.append(line)
            if line.startswith('VAC_END '):frames.append(current);current=None
        return frames

    def test_retained_native_faults_and_board_budget(self):
        result=compact.review(HERE/'reports/array-compact')
        self.assertTrue(result['denseAndCompactExactlyEqual'])
        self.assertEqual(result['restoredFaults'],18)
        result=budget.review(HERE/'reports/array-compact-budget')
        self.assertTrue(result['denseAndCompactExactlyEqual'])
        self.assertLess(result['logicalImageBytes'],result['denseLogicalImageBytes']/4)

    def test_padding_and_truncated_words_rejected(self):
        frame=self.frames()[0]
        i=next(i for i,line in enumerate(frame) if line.startswith('VAR_ARRAY ') and int(line.split()[10])%2)
        bad=list(frame);packed=bad[i+1].split()[1]
        # The high pair of the final hex digit in each odd-width word is padding.
        stride=(int(frame[i].split()[10])+1)//2
        bad[i+1]='VAC_WORDS '+packed[:stride-1]+'f'+packed[stride:]
        with self.assertRaises(ValueError):compact.expand(bad)
        bad=list(frame);bad[i+1]=bad[i+1][:-1]
        with self.assertRaises(ValueError):compact.expand(bad)

    def test_cache_overflow_and_missing_snapshot_rejected(self):
        frame=next(f for f in self.frames() if any(l.startswith('VAC_CACHE_RUN ') for l in f))
        i=next(i for i,l in enumerate(frame) if l.startswith('VAC_CACHE_RUN '))
        bad=list(frame);bad[i]='VAC_CACHE_RUN 999999999 '+bad[i].split()[2]
        with self.assertRaises(ValueError):compact.expand(bad)
        with self.assertRaises(ValueError):compact.separate(frame)


if __name__=='__main__':unittest.main()
