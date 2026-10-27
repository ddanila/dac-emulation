import copy
import unittest
from pathlib import Path
import net_probe as probe
ROOT=Path(__file__).resolve().parent/'reports/net-state'


class NativeGraph(unittest.TestCase):
    def first(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines();start=lines.index('VNM_BEFORE')+1
        end=next(i for i in range(start,len(lines)) if lines[i].startswith('VNG_END '))
        return probe.parse(lines[start:end+1])
    def test_retained_native_controls(self):
        result=probe.review(ROOT)
        self.assertEqual(result['restoredFaults'],36)
        self.assertTrue(result['normalGraphTrajectoryExactlyEqual'])
    def test_foreign_targets_and_cycles_rejected(self):
        before=self.first();probe.validate(before)
        bad=copy.deepcopy(before);i,_=probe.target(before,5);bad['nodes'][i]['out']=(4,0,0)
        probe.changed(before,bad,5)
        with self.assertRaises(ValueError):probe.validate(bad)
        bad=copy.deepcopy(before);n=bad['nodes'][0];link=(n['key'],n['id'],0);n['out']=link;n['ports'][0]=link
        with self.assertRaises(ValueError):probe.validate(bad)
    def test_unrelated_mutation_and_lost_allocation_rejected(self):
        before=self.first();bad=copy.deepcopy(before);i,_=probe.target(before,3);bad['nodes'][i]['fun']=0
        probe.changed(before,bad,3)
        bad['tick']+=1
        with self.assertRaises(ValueError):probe.changed(before,bad,3)
        lines=(ROOT/'enabled.stdout').read_text().splitlines();start=lines.index('VNM_BEFORE')+1
        end=next(i for i in range(start,len(lines)) if lines[i].startswith('VNG_END '))
        frame=lines[start:end+1];del frame[1]
        with self.assertRaises(ValueError):probe.parse(frame)


if __name__=='__main__':unittest.main()
