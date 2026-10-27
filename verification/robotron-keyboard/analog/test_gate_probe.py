"""Native gate inventories must preserve every cache and wrapper association."""
import copy,json,unittest
from pathlib import Path
import native_gate_probe as gate
ROOT=Path(__file__).resolve().parent/'reports/gate-state'

class GateProbe(unittest.TestCase):
    def states(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines();states=[];i=0
        while i<len(lines):
            if lines[i].startswith('VGL_BEGIN '):
                start=i
                while not lines[i].startswith('VGL_END '):i+=1
                states.append(gate.parse(lines[start:i+1]))
            i+=1
        return states
    def test_retained(self):
        result=gate.review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        self.assertTrue(all(result['faultsByField'].values()))
    def test_each_input_and_inversion_fault(self):
        before=self.states()[0]
        for g in before['gates']:
            for field in gate.fields(g):
                after=copy.deepcopy(before);item=next(v for v in after['gates'] if v['id']==g['id'])
                if field==5:item['invert']^=1
                else:item['inputs'][field]='1'+item['inputs'][field][1:]
                gate.changed(before,after,g['id'],field)
                after['tick']+=1
                with self.assertRaisesRegex(ValueError,'unrelated'):gate.changed(before,after,g['id'],field)
    def test_pending_and_wrapper_ownership(self):
        before=next(s for s in self.states() if any(g['pending'] for g in s['gates']))
        gate.validate(before)
        bad=copy.deepcopy(before);next(g for g in bad['gates'] if g['pending'])['pending']=0
        with self.assertRaisesRegex(ValueError,'queue mismatch'):gate.validate(bad)
        bad=copy.deepcopy(before);bad['events'][0]['event']=4
        with self.assertRaisesRegex(ValueError,'Foreign'):gate.validate(bad)
    def test_unknown_family_or_wrong_arity(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines();start=next(i for i,l in enumerate(lines) if l.startswith('VGL_BEGIN '));end=next(i for i in range(start,len(lines)) if lines[i].startswith('VGL_END '));lines=lines[start:end+1]
        for column,value in [(5,'6'),(6,'-1'),(8,'3'),(9,'0'),(10,'q')]:
            bad=list(lines);row=bad[1].split();row[column]=value;bad[1]=' '.join(row)
            with self.subTest(column=column),self.assertRaises(ValueError):gate.parse(bad)

if __name__=='__main__':unittest.main()
