import copy
import unittest
from pathlib import Path
from code_operand_board_review import OperandState
from code_operand_budget import text
from build_code_operand_bridge import operand_header, HERE

ROOT=Path(__file__).resolve().parent/'reports/code-operand-budget'


class OperandBoard(unittest.TestCase):
    def tracker(self):
        tracker=OperandState((ROOT/'board.vvp').read_text())
        tracker.set_reference(text(ROOT/'reference.txt').splitlines())
        return tracker

    def state(self,tracker):
        return dict(threads=dict(tick=0),operands=dict(mode='D',tick=0,total=len(tracker.reference),rows={}),priorLayer='unchanged')

    def test_complete_reference_and_normal_observation(self):
        tracker=self.tracker();state=self.state(tracker)
        tracker.observe(state)
        self.assertGreater(tracker.result()['allocatedOperandInstructions'],20000)
        with self.assertRaises(ValueError):tracker.set_reference(text(ROOT/'reference.txt').splitlines())
        state['operands']['total']-=1
        with self.assertRaises(ValueError):tracker.observe(state)

    def test_exact_operand_mutations_and_other_layers(self):
        tracker=self.tracker();before=self.state(tracker)
        for mode,key in [('immediate','number'),('target','cptr'),('handle','handle')]:
            identity=next(i for i,r in tracker.reference.items() if key in r['fields'])
            row=copy.deepcopy(tracker.reference[identity])
            value=row['fields'][key]
            row['fields'][key]=str(int(value)^1) if mode=='immediate' else '1/0' if mode=='target' else '1'
            after=copy.deepcopy(before);after['operands']['rows']={identity:row}
            tracker.changed(before,after,mode)
            with self.assertRaises(ValueError):tracker.observe(after)
            after['priorLayer']='changed'
            with self.assertRaises(ValueError):tracker.changed(before,after,mode)

    def test_wrong_typed_reference(self):
        tracker=OperandState((ROOT/'board.vvp').read_text())
        raw=text(ROOT/'reference.txt').replace('number=','wrong=',1)
        with self.assertRaises(ValueError):tracker.set_reference(raw.splitlines())

    def test_bridge_keeps_all_layers_and_restores_before_verdict(self):
        header=operand_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for name in ('ports','output','start','assignment','primitive','island','filter','thread','wait','code','scope','operand'):
            self.assertIn('robotron_'+name+'_inventory(f, ctx)',header)
        self.assertLess(header.index('    robotron_operand_reference(ctx);'),header.index('    char *before = display_snapshot(ctx, api);'))
        restore=header.index('robotron_operand_fault(ctx,operand_field)!=1)exit(3)')
        self.assertLess(restore,header.index('int detected=operand_field==3',restore))
        self.assertIn('VB_OPERAND_REFUSAL field=3',header)
        self.assertIn('info->vtime>=5e-6',header)


if __name__=='__main__':unittest.main()
