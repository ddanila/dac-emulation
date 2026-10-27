import json,shutil,tempfile,unittest
from pathlib import Path
from island_raw_feedback import review,HERE,output_text,settle_feedback
ROOT=HERE/'reports/island-raw-feedback'

class IslandRawFeedback(unittest.TestCase):
    def test_retained_native_replay(self):
        self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_previous_output_controls_initial_branch_state(self):
        old=(0x66,0x66)
        self.assertEqual(settle_feedback((0xee,0),False,0,old),((0xee,0),0,[0xee,0],[1,0]))
        self.assertEqual(settle_feedback((0xee,0),False,0,None),((0xee,0),0,[0],[0]))
    def test_resistive_intermediate_output(self):
        self.assertEqual(settle_feedback((0xee,0),True,0,(0x66,0x55)),((0xee,0),0,[0xdd,0],[1,0]))
    def test_nonsettling_model_is_rejected(self):
        with self.assertRaises(ValueError):settle_feedback((0xbb,0x66),False,1,None)
    def reject(self,mode,old,new):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);s=output_text(root,mode);self.assertIn(old,s);(root/(mode+'.stdout')).write_text(s.replace(old,new,1))
            with self.assertRaises(ValueError):review(root)
    def test_intermediate_original_output_required(self):
        self.reject('baseline','GROW_VALUE 2000 0 ee\n','')
    def test_intermediate_output_order_required(self):
        self.reject('baseline','GROW_VALUE 2000 0 ee\nGROW_VALUE 2000 0 00','GROW_VALUE 2000 0 00\nGROW_VALUE 2000 0 ee')
    def test_feedback_endpoint_binding_required(self):
        text=output_text(ROOT,'enabled');line=next(l for l in text.splitlines() if l.startswith('VI_TRAN '));parts=line.split();parts[1]='0x0'
        self.reject('enabled',line,' '.join(parts))
    def test_restoration_required(self):
        self.reject('corrupt','IRM_RESTORED','IRM_CHANGED')

if __name__=='__main__':unittest.main()
