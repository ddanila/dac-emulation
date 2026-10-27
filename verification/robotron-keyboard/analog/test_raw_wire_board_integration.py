"""Bind raw bytes to preceding board layers without collapsing hidden faults."""
import copy,unittest
from types import SimpleNamespace
from pathlib import Path
from raw_wire_board_review import RawWireState,WireState
from wire_raw_delta_probe import block
from net_probe import parse
from net_types_probe import parse as types_parse
from build_raw_wire_bridge import raw_wire_header,HERE
ROOT=HERE/'reports/wire-raw-delta-budget'

class RawWireBoardIntegration(unittest.TestCase):
    def state(self):
        lines=(ROOT/'before.txt').read_text().splitlines();nodes=parse(lines)
        graph=SimpleNamespace(nodes=nodes['nodes'],reference={int(l.split()[1]):l for l in lines[1:-1]})
        signals=SimpleNamespace(types=types_parse((ROOT/'types-before.txt').read_text().splitlines()))
        wires=WireState();wires.reference={};identity=None
        for line in (ROOT/'wires-before.txt').read_text().splitlines()[1:-1]:
            if line.startswith('VWF_FILTER '):identity=int(line.split()[1]);wires.reference[identity]=''
            wires.reference[identity]+=line+'\n'
        observer=RawWireState();observer.set_reference((ROOT/'raw-reference.txt').read_text().splitlines(),graph,signals,wires)
        raw,_=block((ROOT/'raw-delta-before.txt').read_text().splitlines())
        state=dict(rawWire=raw,wires=dict(mode='D',tick=0,total=len(wires.reference),rows={}),threads=dict(tick=0),reduction={'marker':'unchanged'})
        return observer,graph,wires,state
    def test_bindings_and_tick_cache(self):
        observer,graph,wires,state=self.state();observer.observe(state,graph,wires)
        self.assertGreater(observer.result()['maximumRawWireFilters'],0)
        for key in ('rawWire','wires','threads'):state[key]['tick']=20
        observer.observe(state,graph,wires);self.assertEqual(observer.image(state['rawWire'])['tick'],20)
        with self.assertRaisesRegex(ValueError,'reset'):observer.set_reference([],graph,None,wires)
    def test_hidden_collision_and_prior_views(self):
        observer,graph,wires,before=self.state();identity=next(iter(observer.reference));row=observer.reference[identity].split();row[5]='88'+row[5][2:]
        after=copy.deepcopy(before);after['rawWire']['rows']={identity:(0,0,' '.join(row)+'\n')}
        observer.changed(before,after,'raw-wire');observer.observe(after,graph,wires)
        self.assertNotEqual(observer.image(before['rawWire']),observer.image(after['rawWire']))
        after['reduction']['marker']='changed'
        with self.assertRaisesRegex(ValueError,'preceding'):observer.changed(before,after,'raw-wire')
    def test_rebound_graph(self):
        observer,graph,wires,state=self.state();identity=next(iter(observer.expected));graph.nodes[identity-1]['filter']+=1
        with self.assertRaisesRegex(ValueError,'binding'):observer.observe(state,graph,wires)
    def test_unadmitted_growth(self):
        observer,graph,wires,state=self.state();identity=max(observer.reference)+1;row=next(iter(observer.reference.values())).split();row[1]=str(identity);row[2]='0x110';row[3]='0x120'
        state['rawWire']['total']+=1;state['rawWire']['rows'][identity]=(0,0,' '.join(row)+'\n')
        with self.assertRaisesRegex(ValueError,'admitted profile'):observer.observe(state,graph,wires)
    def test_legacy_payload_disagreement(self):
        observer,graph,wires,state=self.state();identity=next(iter(observer.reference));row=observer.reference[identity].split();row[5]='66'+row[5][2:]
        state['rawWire']['rows']={identity:(0,0,' '.join(row)+'\n')}
        with self.assertRaisesRegex(ValueError,'payload differs'):observer.observe(state,graph,wires)
    def test_preceding_layers_and_fault_restore(self):
        header=raw_wire_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for layer in ('ports','output','start','assignment','primitive','island','filter','thread','wait','code','scope','operand','array','net','wire','signal','mux','gate','arithmetic','reduction','raw_wire'):
            self.assertIn('robotron_'+layer+'_inventory(f, ctx)',header)
        self.assertLess(header.index('    robotron_raw_wire_reference(ctx);'),header.index('    char *before = display_snapshot(ctx, api);'))
        restore=header.index('robotron_raw_wire_fault(ctx,raw_wire_field)!=1)exit(3)')
        self.assertLess(restore,header.index('int detected=',restore))
        self.assertIn('strcmp(mode,"reduction-size-corrupt")',header)

if __name__=='__main__':unittest.main()
