import json,shutil,tempfile,unittest
from pathlib import Path
from signal_handle_board_budget import HERE,review,compiled_handles
from retained_evidence import check
ROOT=HERE/'reports/signal-handle-board-budget'


class SignalHandleBoardBudget(unittest.TestCase):
    def test_actual_bridge_bindings_and_budget_replay(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))

    def tamper(self,name,change):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/name;s=p.read_text();changed=change(s);self.assertNotEqual(s,changed);p.write_text(changed)
            with self.assertRaises(ValueError):review(root)

    def test_missing_input_handle_handoff_rejected(self):self.tamper('handle-bindings.txt',lambda s:'\n'.join(s.splitlines()[1:])+'\n')
    def test_no_prior_admission_allowed(self):self.tamper('handles-unadmitted.txt',lambda s:(ROOT/'handles-before.txt').read_text())
    def test_native_graph_pointer_binding_required(self):
        def change(s):
            lines=s.splitlines();a=lines[1].split();a[2]='0x1';lines[1]=' '.join(a);return '\n'.join(lines)+'\n'
        self.tamper('handle-graph.txt',change)
    def test_native_scope_binding_required(self):
        def change(s):
            lines=s.splitlines();i=next(i for i,l in enumerate(lines) if l.startswith('VSC_SCOPE 2 '));a=lines[i].split();a[2]='0x1';lines[i]=' '.join(a);return '\n'.join(lines)+'\n'
        self.tamper('handle-scopes.txt',change)
    def test_observation_must_not_change_state(self):self.tamper('handles-after.txt',lambda s:s.replace('VSH_BEGIN 1 0','VSH_BEGIN 1 1'))
    def test_callback_object_handoff_must_match(self):
        def change(s):
            lines=s.splitlines();a=lines[-1].split();a[3]='0x1';lines[-1]=' '.join(a);return '\n'.join(lines)+'\n'
        self.tamper('handle-bindings.txt',change)
    def test_scan_cost_must_be_finite(self):self.tamper('handle-budget.txt',lambda s:'SH_BUDGET 64 nan 1 2\nSH_DONE\n')
    def test_compiled_scope_must_match_port_names(self):
        with self.assertRaisesRegex(ValueError,'top module'):compiled_handles((ROOT/'io.vvp').read_text(),['other.fixture_clk'])


if __name__=='__main__':unittest.main()
