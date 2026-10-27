import copy
import unittest
from pathlib import Path
import net_delta_probe as delta
import net_delta_budget as budget
HERE=Path(__file__).resolve().parent
ROOT=HERE/'reports/net-delta'


class NetDelta(unittest.TestCase):
    def test_retained_native_and_board_images(self):
        result=delta.review(ROOT)
        self.assertTrue(result['denseAndDeltaExactlyEqual'])
        self.assertEqual(result['restoredFaults'],36)
        result=budget.review(HERE/'reports/net-delta-budget')
        self.assertTrue(result['denseAndDeltaExactlyEqual'])
        self.assertLess(result['projection']['unchangedGraphDeltaLogBytes'],result['projection']['fullGraphLogBytes']/100)
    def frames(self):
        lines=(ROOT/'corrupt.stdout').read_text().splitlines();frames=[];i=0
        while i<len(lines):
            if lines[i].startswith('VND_BEGIN '):
                frame,end=delta.block(lines,i);frames.append((i,end,frame));i=end
            else:i+=1
        return lines,frames
    def test_new_allocation_must_be_present(self):
        _,frames=self.frames();reference=frames[0][2]['rows']
        frame=copy.deepcopy(next(f for _,_,f in frames if f['mode']=='D' and f['total']>len(reference)))
        del frame['rows'][frame['total']]
        with self.assertRaises(ValueError):delta.reconstruct(reference,frame)
    def test_lost_fault_row_and_reset_rejected(self):
        lines,frames=self.frames();start,end,frame=next((s,e,f) for s,e,f in frames if f['mode']=='D' and f['rows'])
        replacement=[f"VND_BEGIN D {frame['tick']} {frame['total']} 0",'VND_END 0']
        with self.assertRaises(ValueError):delta.separate(lines[:start]+replacement+lines[end:])
        start,end,_=frames[0]
        with self.assertRaises(ValueError):delta.separate(lines[:end]+lines[start:end]+lines[end:])
    def test_incomplete_reference_rejected(self):
        lines,frames=self.frames();start,end,_=frames[0]
        frame=lines[start:end];del frame[1]
        with self.assertRaises(ValueError):delta.block(frame)


if __name__=='__main__':unittest.main()
