import copy
import unittest
from pathlib import Path
from net_board_review import GraphState
from code_operand_board_review import OperandState
from net_delta_probe import block
from array_probe import parse
from build_net_bridge import net_header,HERE
ROOT=HERE/'reports/net-delta-budget'


class NetBoard(unittest.TestCase):
    def setup_state(self):
        compiled=(ROOT/'board.vvp').read_text();graph=GraphState(compiled)
        graph.set_reference((ROOT/'reference.txt').read_text().splitlines())
        operands=OperandState(compiled);operands.set_reference((ROOT/'operands.txt').read_text().splitlines())
        frame,_=block((ROOT/'delta-before.txt').read_text().splitlines())
        arrays=parse((ROOT/'arrays.txt').read_text().splitlines())
        key=arrays['ports'][0]['net']
        state=dict(graph=frame,threads=dict(tick=0),arrays=arrays,assignments=dict(events=[dict(target=hex(key))]),primitives=dict(events=[dict(target=key)]))
        return graph,operands,state
    def test_complete_reference_and_cross_references(self):
        graph,operands,state=self.setup_state();graph.observe(state,operands)
        result=graph.result(False)
        self.assertGreater(result['uniqueCodeNetTargets'],0)
        self.assertGreater(result['arrayNetReferenceObservations'],0)
        with self.assertRaises(ValueError):graph.set_reference((ROOT/'reference.txt').read_text().splitlines())
    def test_cross_layer_foreign_targets_rejected(self):
        for family,key in [('arrays','net'),('assignments','target'),('primitives','target')]:
            graph,operands,state=self.setup_state()
            items=state[family]['ports' if family=='arrays' else 'events']
            items[0][key]='0x4' if family=='assignments' else 4
            with self.assertRaises(ValueError):graph.observe(state,operands)
    def test_actual_reference_fault_and_unrelated_mutation(self):
        graph,operands,before=self.setup_state();graph.observe(before,operands)
        identity=next(i for i,row in graph.reference.items() if int(row.split()[6].split('/')[1])!=0)
        row=graph.reference[identity].split();row[6]='0x4/0/0'
        after=copy.deepcopy(before);after['graph']['rows']={identity:' '.join(row)}
        graph.changed(before,after,'foreign')
        with self.assertRaises(ValueError):graph.observe(after,operands)
        after['threads']['tick']=1
        with self.assertRaises(ValueError):graph.changed(before,after,'foreign')
    def test_bridge_layers_and_restore_before_verdict(self):
        header=net_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for name in ('ports','output','start','assignment','primitive','island','filter','thread','wait','code','scope','operand','array','net'):
            self.assertIn('robotron_'+name+'_inventory(f, ctx)',header)
        self.assertLess(header.index('    robotron_net_reference(ctx);'),header.index('    char *before = display_snapshot(ctx, api);'))
        restore=header.index('robotron_net_fault(ctx,net_field)!=1)exit(3)')
        self.assertLess(restore,header.index('int detected=',restore))


if __name__=='__main__':unittest.main()
