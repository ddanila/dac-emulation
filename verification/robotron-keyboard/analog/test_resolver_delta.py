import copy,json,unittest
from pathlib import Path
from resolver_delta_probe import block,reconstruct,separate,review,HERE
from resolver_delta_board import review as board_review

class ResolverDelta(unittest.TestCase):
    def frames(self,name='resolver-delta'):
        lines=(HERE/'reports'/name/'corrupt.stdout').read_text().splitlines();frames=[];i=0
        while i<len(lines):
            if lines[i].startswith('VRX_BEGIN '):
                f,i=block(lines,i);frames.append(f)
            else:i+=1
        return lines,frames
    def test_retained_native_replays(self):
        for name in ('resolver-delta','resolver-delta-growth'):
            root=HERE/'reports'/name
            self.assertEqual(review(root),json.loads((root/'assessment.json').read_text()))
    def test_board_budget(self):
        root=HERE/'reports/resolver-delta-budget';a=board_review(root)
        self.assertEqual(a,json.loads((root/'assessment.json').read_text()))
        self.assertLess(a['projection']['resolverDeltaLogBytesAtInitialState'],a['projection']['resolverLogBytesAtInitialState'])
    def test_new_allocations_need_full_records_every_time(self):
        _,frames=self.frames('resolver-delta-growth');reference=frames[0]['rows'];grown=[f for f in frames[1:] if f['total']>len(reference)]
        self.assertTrue(grown)
        for f in grown:
            new=set(f['rows'])-set(reference);self.assertEqual(len(new),8)
            for n in new:self.assertEqual(f['rows'][n][:2],(0,0))
        bad=copy.deepcopy(grown[-1]);del bad['rows'][next(iter(set(bad['rows'])-set(reference)))]
        with self.assertRaisesRegex(ValueError,'Missing new'):reconstruct(reference,bad)
    def test_splice_outside_reference_rejected(self):
        _,frames=self.frames();reference=frames[0]['rows'];bad=copy.deepcopy(next(f for f in frames[1:] if f['rows']));key=next(iter(bad['rows']));bad['rows'][key]=(len(reference[key])+1,0,'')
        with self.assertRaisesRegex(ValueError,'exceeds'):reconstruct(reference,bad)
    def test_cache_slot_loss_rejected(self):
        _,frames=self.frames();reference=copy.deepcopy(frames[0]['rows'])
        key=next(k for k,v in reference.items() if 'VRS_SLOT ' in v)
        reference[key]='\n'.join(l for l in reference[key].splitlines() if not l.startswith('VRS_SLOT 0 '))+'\n'
        with self.assertRaises(ValueError):reconstruct(reference,frames[1])
    def test_raw_collision_bytes_remain_distinct(self):
        lines,frames=self.frames()
        self.assertTrue(any(' 6 ' in line and line.startswith('RSM_CHANGED ') for line in lines))
        # Paired reconstruction plus the independent dense fault oracle checks each raw collision.
        self.assertGreater(separate(lines)[1],0)
    def test_reference_reset_rejected(self):
        lines,_=self.frames();i=next(i for i,l in enumerate(lines) if l.startswith('VRX_BEGIN R'));_,end=block(lines,i)
        with self.assertRaisesRegex(ValueError,'reset'):separate(lines[:end]+lines[i:end]+lines[end:])

if __name__=='__main__':unittest.main()
