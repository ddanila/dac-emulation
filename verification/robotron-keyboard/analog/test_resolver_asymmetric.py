import json,shutil,tempfile,unittest
from pathlib import Path
import resolver_asymmetric_inputs as dense
import resolver_asymmetric_delta as compact
from resolver_strength_oracle import scalar
HERE=dense.HERE

class ResolverAsymmetric(unittest.TestCase):
    def test_all_retained_original_scalar_pairs(self):
        states=set();pairs={}
        for line in (HERE/'reports/strength-encoding/baseline.stdout').read_text().splitlines():
            if line.startswith('STRENGTH_STATE '):states.add(int(line.split()[1]))
            if line.startswith('STRENGTH_RESOLVE '):
                a,b,value=map(int,line.split()[1:]);pairs[a,b]=value
        self.assertEqual(set(pairs),{(a,b) for a in states for b in states})
        for (a,b),value in pairs.items():self.assertEqual(scalar(a,b),value,(a,b))
        self.assertTrue(set(dense.RAW_INPUTS)<=states)
    def test_retained_native_replays(self):
        for name,module in [('resolver-asymmetric-inputs',dense),('resolver-asymmetric-delta',compact)]:
            root=HERE/'reports'/name
            self.assertEqual(module.review_all(root),json.loads((root/'assessment.json').read_text()))
    def test_high_impedance_encoding_is_order_sensitive(self):
        self.assertEqual(scalar(0,136),136)
        self.assertEqual(scalar(136,0),0)
        self.assertEqual(dense.tree([b'\x88'],0),[b'\x88'])
    def reject(self,name,module,mode,old,new):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'width';shutil.copytree(HERE/'reports'/name/'width-9',root)
            text=dense.output_text(root,mode);self.assertIn(old,text)
            (root/(mode+'.stdout')).write_text(text.replace(old,new,1))
            with self.assertRaises(ValueError):module.review(root)
    def test_original_asymmetric_output_required(self):
        self.reject('resolver-asymmetric-inputs',dense,'baseline','RES_VALUE 2 0 '+'81'*9,'RES_VALUE 2 0 '+'91'*9)
    def test_compact_original_asymmetric_output_required(self):
        self.reject('resolver-asymmetric-delta',compact,'baseline','RES_VALUE 2 0 '+'81'*9,'RES_VALUE 2 0 '+'91'*9)
    def test_restoration_required(self):
        self.reject('resolver-asymmetric-delta',compact,'corrupt','RSM_RESTORED','RSM_NOT_RESTORED')
    def test_compact_pair_required(self):
        self.reject('resolver-asymmetric-delta',compact,'corrupt','VRX_BEGIN D','VRX_MISSING D')

if __name__=='__main__':unittest.main()
