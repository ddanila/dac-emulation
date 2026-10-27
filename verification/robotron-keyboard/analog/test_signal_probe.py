"""Reject malformed or incomplete signal payload and unrelated fault changes."""
import copy,json,unittest
from pathlib import Path
import signal_probe as signal
HERE=Path(__file__).resolve().parent
ROOT=HERE/'reports/signal-state'

class SignalProbe(unittest.TestCase):
    def snapshots(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines();result=[];i=0
        while i<len(lines):
            if lines[i].startswith('VSG_BEGIN '):
                start=i
                while not lines[i].startswith('VSG_END '):i+=1
                result.append(lines[start:i+1])
            i+=1
        return result
    def test_retained(self):
        result=signal.review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        self.assertTrue(all(result['faultsByField'].values()))
    def test_link_fault_and_unrelated_change(self):
        before=next(signal.parse(lines) for lines in self.snapshots() if any(s['link'] for s in signal.parse(lines)['signals']))
        index=signal.target(before,3);after=copy.deepcopy(before);after['signals'][index]['link']=0
        signal.changed(before,after,3)
        after['signals'][index]['init']^=1
        with self.assertRaisesRegex(ValueError,'unrelated'):signal.changed(before,after,3)
    def test_bad_width_bits_and_alias(self):
        lines=self.snapshots()[0]
        for column,value in ((7,'0'),(8,'q'),(9,'1'),(4,'2')):
            bad=list(lines);row=bad[1].split();row[column]=value;bad[1]=' '.join(row)
            with self.subTest(column=column),self.assertRaises(ValueError):signal.parse(bad)
        bad=list(lines);first=bad[1].split();second=bad[2].split();second[3]=first[3];bad[2]=' '.join(second)
        with self.assertRaisesRegex(ValueError,'aliased'):signal.parse(bad)

if __name__=='__main__':unittest.main()
