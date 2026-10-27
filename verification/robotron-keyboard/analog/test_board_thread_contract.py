import copy,unittest
from pathlib import Path
from board_thread_contract import compiled_contract,validate_thread
from test_thread_board_review import state
HERE=Path(__file__).resolve().parent

class BoardThreadContract(unittest.TestCase):
    def test_current_compiled_profile(self):
        text=(HERE/'reports/thread-board/observe/io.vvp').read_text()
        self.assertTrue(compiled_contract(text)['compiledProfileAccepted'])
        for suffix in ('\nnew_label %alloc S;\n','\nnew_label %new/cobj C;\n','\n    %vpi_call/w 1 1 "$foreign";\n','\nA .scope task, "a" "a" 1 1, 1 1 1, S;\n'):
            with self.assertRaises(ValueError):compiled_contract(text+suffix)

    def test_actual_nonzero_referents_are_not_ignored(self):
        original=state()['threads']['threads'][0];validate_thread(original)
        for field in ('writeContext','readContext','event','eventCount','objects'):
            changed=copy.deepcopy(original);changed[field]=[123] if field=='objects' else 123
            with self.assertRaises(ValueError):validate_thread(changed)

    def test_unexpected_lifecycle_and_detached_membership(self):
        original=state()['threads']['threads'][0]
        for index in (1,2):
            changed=copy.deepcopy(original);changed['state']=changed['state'][:index]+'1'+changed['state'][index+1:]
            with self.assertRaises(ValueError):validate_thread(changed)
        changed=copy.deepcopy(original);changed['children'][1]=[123]
        with self.assertRaises(ValueError):validate_thread(changed)

if __name__=='__main__':unittest.main()
