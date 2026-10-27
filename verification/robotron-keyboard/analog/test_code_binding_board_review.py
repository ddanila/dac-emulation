import copy,unittest
from code_binding_board_review import CodeBindings,changed_code
from test_wait_board_review import state as wait_state


def state():
    s=wait_state();s['threadCode']=[dict(thread=t['id'],pc=t['pc'],code=i+1,opcode=0x1000+i) for i,t in enumerate(s['threads']['threads'])]
    return s


class CodeBindingBoard(unittest.TestCase):
    def test_all_thread_bindings_and_stable_instruction_identity(self):
        tracker=CodeBindings();tracker.observe(state());tracker.observe(state())
        self.assertEqual(tracker.result(False)['threadCodeObservations'],4)
        for key in ('opcode','pc'):
            tracker=CodeBindings();tracker.observe(state());bad=state();bad['threadCode'][0][key]+=1
            if key=='pc':bad['threads']['threads'][0]['pc']+=1
            with self.assertRaises(ValueError):tracker.observe(bad)

    def test_null_foreign_and_unrelated_mutations(self):
        before=state()
        for name,pc in [('null',0),('foreign',1)]:
            bad=copy.deepcopy(before);bad['threads']['threads'][0]['pc']=pc;bad['threadCode'][0].update(pc=pc,code=0,opcode=0)
            changed_code(before,bad,name)
            with self.assertRaises(ValueError):CodeBindings().observe(bad)
            bad['threadQueue']['events'][0]['key']+=1
            with self.assertRaises(ValueError):changed_code(before,bad,name)

    def test_missing_thread_binding_rejected(self):
        bad=state();bad['threadCode'].pop()
        with self.assertRaises(ValueError):CodeBindings().observe(bad)

if __name__=='__main__':unittest.main()
