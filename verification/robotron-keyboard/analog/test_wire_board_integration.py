"""Board wire controls retain graph bindings and shared island observations."""
import copy,unittest
from pathlib import Path
from types import SimpleNamespace
from wire_board_review import WireState
from wire_delta_probe import block
from net_probe import parse
from build_wire_bridge import wire_header,HERE
ROOT=HERE/'reports/wire-delta-budget'

class WireBoardIntegration(unittest.TestCase):
    def setup_state(self):
        wires=WireState();wires.set_reference((ROOT/'wire-reference.txt').read_text().splitlines())
        frame,_=block((ROOT/'wire-delta-before.txt').read_text().splitlines())
        graph=SimpleNamespace(nodes=parse((ROOT/'before.txt').read_text().splitlines())['nodes'])
        state=dict(wires=frame,threads=dict(tick=0),filters=dict(tick=0,ports=[]))
        return wires,graph,state
    def test_complete_board_bindings(self):
        wires,graph,state=self.setup_state();wires.observe(state,graph)
        self.assertEqual(wires.result()['wireKinds'],[4,8])
        with self.assertRaisesRegex(ValueError,'reset'):wires.set_reference((ROOT/'wire-reference.txt').read_text().splitlines())
    def test_wrong_graph_binding(self):
        for key in ('key','filter'):
            wires,graph,state=self.setup_state()
            next(n for n in graph.nodes if n['filter'])[key]+=4
            with self.assertRaisesRegex(ValueError,'binding'):wires.observe(state,graph)
    def test_alias_and_exact_fault(self):
        wires,graph,before=self.setup_state();first=wires.image(before['wires'])
        target=next(w for w in first['filters'] if w['kind']==8)
        alias={k:v for k,v in target.items() if k not in ('id','node','kind','callbacks','arrayWords')}
        alias.update(island=1,port=1);before['filters']['ports']=[alias]
        wires.observe(before,graph)
        identity=target['id'];row=wires.reference[identity]
        changed=row.replace('VIF_WIRE '+str(target['init']), 'VIF_WIRE '+str(target['init']^1))
        after=copy.deepcopy(before);after['wires']['rows']={identity:(0,0,changed)}
        after['filters']['ports'][0]['init']^=1
        wires.changed(before,after,'wire8-init')
        after['filters']['ports'][0]['island']+=1
        with self.assertRaisesRegex(ValueError,'ownership'):wires.changed(before,after,'wire8-init')
    def test_bridge_preserves_layers_and_restores(self):
        header=wire_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for name in ('ports','output','start','assignment','primitive','island','filter','thread','wait','code','scope','operand','array','net','wire'):
            self.assertIn('robotron_'+name+'_inventory(f, ctx)',header)
        self.assertLess(header.index('    robotron_wire_reference(ctx);'),header.index('    char *before = display_snapshot(ctx, api);'))
        restore=header.index('robotron_wire_fault(ctx,wire_kind,wire_field)!=1)exit(3)')
        self.assertLess(restore,header.index('int detected=',restore))

if __name__=='__main__':unittest.main()
