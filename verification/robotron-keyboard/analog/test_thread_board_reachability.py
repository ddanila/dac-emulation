import json,unittest
from pathlib import Path
from thread_board_reachability import analyze
HERE=Path(__file__).resolve().parent

class BoardReachability(unittest.TestCase):
    def test_retained_input_reproduces_inventory(self):
        report=json.loads((HERE/'reports/thread-board-reachability/assessment.json').read_text())
        compiled=report['compiled'];text=(HERE/'reports/island-filter-board/off/io.vvp').read_text()
        self.assertEqual(analyze(text),{k:v for k,v in compiled.items() if k not in ('path','sha256')})
        self.assertEqual(compiled['opcodeCounts']['%join'],2)
        self.assertTrue(compiled['emitted']['strobe'])

    def test_labels_and_quoted_counterfeits(self):
        text='''S .scope module, "top" "top" 1 1;
label %join/detach 2;
    %wait/fork;
other %disable/fork;
    %vpi_call/w 1 1 "$display", "%evctl %join/detach";
'''
        r=analyze(text)
        self.assertTrue(all(r['emitted'][k] for k in ('detach','waitFork','disableFork')))
        self.assertFalse(r['emitted']['eventControls'])
        self.assertEqual(r['opcodeCounts']['%join/detach'],1)

    def test_automatic_scope_and_changed_native_requirement(self):
        text='''S .scope module, "top" "top" 1 1;
F .scope task, "t" "t" 1 2, 1 2 1, S;
label %evctl/i E, 3;
    %vpi_call/w 1 2 "$strobe", "x";
'''
        r=analyze(text)
        self.assertTrue(r['emitted']['automaticScopes'])
        self.assertTrue(r['emitted']['eventControls'])
        self.assertTrue(r['emitted']['strobe'])
        with self.assertRaises(ValueError):analyze(text.replace('1 2 1, S','1 2 7, S'))
        with self.assertRaises(ValueError):analyze(text.replace('"top" "top"','broken'))

if __name__=='__main__':unittest.main()
