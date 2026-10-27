"""Combined gate checks preserve prior layers and agree with shared NOT views."""
import copy,unittest
from types import SimpleNamespace
from gate_board_review import GateState
from gate_delta_probe import block
from net_probe import parse
from net_types_probe import parse as types_parse
from build_gate_bridge import gate_header,HERE
ROOT=HERE/'reports/gate-delta-budget'

class GateBoardIntegration(unittest.TestCase):
    def setup_state(self):
        lines=(ROOT/'before.txt').read_text().splitlines();parsed=parse(lines)
        graph=SimpleNamespace(nodes=parsed['nodes'],reference={int(l.split()[1]):l for l in lines[1:-1]})
        signals=SimpleNamespace(types=types_parse((ROOT/'types-before.txt').read_text().splitlines()))
        gates=GateState((ROOT/'board.vvp').read_text())
        gates.set_reference((ROOT/'gate-reference.txt').read_text().splitlines(),graph,signals)
        frame,_=block((ROOT/'gate-delta-before.txt').read_text().splitlines())
        return gates,graph,dict(gates=frame,threads=dict(tick=0),primitives=dict(events=[]),muxes=dict(marker='unchanged'))
    def test_native_bindings(self):
        gates,graph,state=self.setup_state();gates.observe(state,graph)
        self.assertGreater(gates.result()['maximumGateFunctors'],0)
        with self.assertRaisesRegex(ValueError,'reset'):gates.set_reference([],graph,None)
    def test_foreign_allocation_or_changed_width(self):
        gates,graph,state=self.setup_state();identity=next(iter(gates.expected))
        next(n for n in graph.nodes if n['id']==identity)['fun']=4
        with self.assertRaisesRegex(ValueError,'binding'):gates.observe(state,graph)
        gates,graph,state=self.setup_state();identity=next(iter(gates.reference));row=gates.reference[identity].split()
        row[9]=str(int(row[9])+1);row[10]+='0';state['gates']['rows'][identity]=(0,0,' '.join(row)+'\n')
        with self.assertRaisesRegex(ValueError,'width binding'):gates.observe(state,graph)
    def test_inversion_fault_and_prior_state(self):
        gates,graph,before=self.setup_state();identity=next(iter(gates.reference));row=gates.reference[identity].split();row[6]=str(int(row[6])^1)
        after=copy.deepcopy(before);after['gates']['rows']={identity:(0,0,' '.join(row)+'\n')}
        gates.changed(before,after,'gate-invert')
        after['muxes']['marker']='changed'
        with self.assertRaisesRegex(ValueError,'preceding'):gates.changed(before,after,'gate-invert')
    def test_shared_inverter_payload_and_queue(self):
        gates,graph,state=self.setup_state();snapshot=copy.deepcopy(gates.image(state['gates']))
        g=next(g for g in snapshot['gates'] if g['kind']==5);g['pending']=g['node']
        event=dict(id=800,event=g['event'],slot=0,region='active',ordinal=3,delete=0);snapshot['events']=[event]
        old=dict(wrapper=800,kind=1,target=g['node'],size=len(g['inputs'][0]),bits=g['inputs'][0],slot=0,region='active',ordinal=3,delete=0)
        self.assertEqual(gates.primitive_links(snapshot,dict(events=[old])),1)
        with self.assertRaisesRegex(ValueError,'Missing shared'):gates.primitive_links(snapshot,dict(events=[]))
        for field,value in [('bits','0' if old['bits']!='0' else '1'),('target',4),('ordinal',4)]:
            bad=dict(old,**{field:value})
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'payload differs'):gates.primitive_links(snapshot,dict(events=[bad]))
    def test_unadmitted_growth(self):
        gates,graph,state=self.setup_state();identity=max(gates.reference)+1;row=next(iter(gates.reference.values())).split()
        row[1]=str(identity);row[2]='0x110';row[3]='0x120';row[4]='0x128';row[7]='0x0'
        state['gates']['total']+=1;state['gates']['rows'][identity]=(0,0,' '.join(row)+'\n')
        with self.assertRaisesRegex(ValueError,'admitted profile'):gates.observe(state,graph)
    def test_all_layers_and_exact_restore_order(self):
        header=gate_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for name in ('ports','output','start','assignment','primitive','island','filter','thread','wait','code','scope','operand','array','net','wire','signal','mux','gate'):
            self.assertIn('robotron_'+name+'_inventory(f, ctx)',header)
        self.assertLess(header.index('    robotron_gate_reference(ctx);'),header.index('    char *before = display_snapshot(ctx, api);'))
        restore=header.index('robotron_gate_fault(ctx,gate_field)!=1)exit(3)')
        self.assertLess(restore,header.index('int detected=',restore))
        self.assertIn('VB_GATE_FAULT',header)
        for name in ('input0','input1','input2','input3','invert'):self.assertIn('gate-'+name+'-corrupt',header)
        self.assertIn('kind>3)continue',header)

if __name__=='__main__':unittest.main()
