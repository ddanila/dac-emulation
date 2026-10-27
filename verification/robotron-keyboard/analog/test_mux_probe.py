"""Mux caches and scheduler ownership are independent acceptance requirements."""
import copy,json,unittest
from pathlib import Path
import mux_probe as mux
HERE=Path(__file__).resolve().parent
ROOT=HERE/'reports/mux-state'

class MuxProbe(unittest.TestCase):
    def snapshots(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines();result=[];i=0
        while i<len(lines):
            if lines[i].startswith('VXM_BEGIN '):
                start=i
                while not lines[i].startswith('VXM_END '):i+=1
                result.append(lines[start:i+1])
            i+=1
        return result
    def test_retained(self):
        result=mux.review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        self.assertTrue(all(result['faultsByField'].values()))
        self.assertIn('executing',result['coverage'])
    def test_pending_and_wrapper_bindings(self):
        state=next(mux.parse(lines) for lines in self.snapshots() if any(m['pending'] for m in mux.parse(lines)['muxes']))
        mux.validate(state)
        bad=copy.deepcopy(state);next(m for m in bad['muxes'] if m['pending'])['pending']=0
        with self.assertRaisesRegex(ValueError,'queue mismatch'):mux.validate(bad)
        for key,value in [('event',4),('delete',1)]:
            bad=copy.deepcopy(state);bad['events'][0][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'Foreign/owned'):mux.validate(bad)
    def test_exact_selection_fault(self):
        before=mux.parse(self.snapshots()[0]);after=copy.deepcopy(before)
        after['muxes'][0]['select']=0;mux.changed(before,after,2)
        after['muxes'][1]['ran']^=1
        with self.assertRaisesRegex(ValueError,'unrelated'):mux.changed(before,after,2)
    def test_invalid_vector_and_selection(self):
        lines=self.snapshots()[0]
        for column,value in ((6,'3'),(7,'2'),(8,'0'),(9,'q')):
            bad=list(lines);row=bad[1].split();row[column]=value;bad[1]=' '.join(row)
            with self.subTest(column=column),self.assertRaises(ValueError):mux.parse(bad)

if __name__=='__main__':unittest.main()
