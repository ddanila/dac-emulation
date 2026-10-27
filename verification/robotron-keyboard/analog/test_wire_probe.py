import copy
import unittest
from pathlib import Path
import wire_probe as probe
ROOT=Path(__file__).resolve().parent/'reports/wire-state'


class WireControls(unittest.TestCase):
    def first(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines();start=lines.index('WFM_BEFORE')+1
        end=next(i for i in range(start,len(lines)) if lines[i].startswith('VWF_END '))
        return lines[start:end+1]
    def test_retained_native_controls(self):
        result=probe.review(ROOT)
        self.assertEqual(result['restoredFaults'],68)
        self.assertTrue(result['normalWireTrajectoryExactlyEqual'])
    def test_exact_four_state_fault_and_callback_identity(self):
        before=probe.parse(self.first());after=copy.deepcopy(before);i=probe.target(before,4,1)
        v=after['filters'][i]['vectors']['driven'];bits=v['bits'];v['bits']=('0' if bits[0]=='1' else '1')+bits[1:]
        probe.changed(before,after,4,1)
        after['filters'][i]['callbacks']+=8
        with self.assertRaises(ValueError):probe.changed(before,after,4,1)
    def test_wrong_family_and_invalid_four_state_value(self):
        lines=self.first();i=next(i for i,l in enumerate(lines) if l.startswith('VWF_FILTER ') and l.endswith(' 4'))
        bad=list(lines);bad[i]=bad[i][:-1]+'9'
        with self.assertRaises(ValueError):probe.parse(bad)
        j=next(j for j in range(i+1,len(lines)) if lines[j].startswith('VIF_VECTOR driven '))
        a=lines[j].split();a[3]='7'+a[3][1:];bad=list(lines);bad[j]=' '.join(a)
        with self.assertRaises(ValueError):probe.parse(bad)


if __name__=='__main__':unittest.main()
