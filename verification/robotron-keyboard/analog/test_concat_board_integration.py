import copy,unittest
from types import SimpleNamespace
from concat_board_review import ConcatState
from concat_delta_probe import block
from net_probe import parse
from net_types_probe import parse as types_parse
from build_concat_bridge import concat_header,HERE
ROOT=HERE/'reports/concat-delta-budget'

class ConcatBoardIntegration(unittest.TestCase):
    def state(self):
        lines=(ROOT/'before.txt').read_text().splitlines();nodes=parse(lines)
        graph=SimpleNamespace(nodes=nodes['nodes'],reference={int(l.split()[1]):l for l in lines[1:-1]})
        signals=SimpleNamespace(types=types_parse((ROOT/'types-before.txt').read_text().splitlines()))
        observer=ConcatState((ROOT/'board.vvp').read_text());observer.set_reference((ROOT/'concat-reference.txt').read_text().splitlines(),graph,signals)
        frame,_=block((ROOT/'concat-delta-before.txt').read_text().splitlines())
        return observer,graph,dict(concat=frame,threads=dict(tick=0),rawWire={'marker':'unchanged'})
    def row(self,observer,state,identity,alter):
        row=observer.reference[identity].split();alter(row);state['concat']['rows'][identity]=(0,0,' '.join(row)+'\n')
    def test_initial_binding_and_current_tick(self):
        o,g,s=self.state();o.observe(s,g);self.assertGreater(o.result()['maximumConcatFunctors'],0)
        s['threads']['tick']=s['concat']['tick']=42;o.observe(s,g);self.assertEqual(o.image(s['concat'])['tick'],42)
        with self.assertRaisesRegex(ValueError,'reset'):o.set_reference([],g,None)
    def test_width_fault_and_prior_layers(self):
        o,g,before=self.state();after=copy.deepcopy(before);identity=next(iter(o.reference))
        self.row(o,after,identity,lambda r:r.__setitem__(7,str(int(r[7])^1)))
        o.changed(before,after,'concat-width')
        with self.assertRaisesRegex(ValueError,'binding'):o.observe(after,g)
        after['rawWire']['marker']='changed'
        with self.assertRaisesRegex(ValueError,'preceding'):o.changed(before,after,'concat-width')
    def test_raw_collision_fault(self):
        o,g,before=self.state();after=copy.deepcopy(before)
        node=next(n for n in o.image(before['concat'])['nodes'] if n['kind']==8 and any(b in (0,136) for b in bytes.fromhex(n['bits'])))
        def alter(r):
            value=bytearray.fromhex(r[12]);i=next(i for i,b in enumerate(value) if b in (0,136));value[i]^=136;r[12]=value.hex()
        self.row(o,after,node['id'],alter);o.changed(before,after,'concat-raw')
    def test_graph_rebinding(self):
        o,g,s=self.state();identity=next(iter(o.expected));g.nodes[identity-1]['fun']+=1
        with self.assertRaisesRegex(ValueError,'binding'):o.observe(s,g)
    def test_new_allocation_requires_readmission(self):
        o,g,s=self.state();identity=max(o.reference)+1;row=next(iter(o.reference.values())).split();row[1]=str(identity);row[2]='0x110';row[3]='0x120';row[5]='0x128'
        s['concat']['total']+=1;s['concat']['rows'][identity]=(0,0,' '.join(row)+'\n')
        with self.assertRaisesRegex(ValueError,'admitted profile'):o.observe(s,g)
    def test_pending_and_executing_bindings(self):
        o,g,s=self.state();identity=next(iter(o.reference));node=o.image(s['concat'])['nodes'][0]
        self.row(o,s,identity,lambda r:r.__setitem__(6,r[2]))
        with self.assertRaisesRegex(ValueError,'without wrapper'):o.observe(s,g)
        s['concat']['events']=[f"VXM_EVENT 0 active 0 100 {hex(node['event'])} 0"];o.observe(s,g)
        s['concat']['rows']={};s['concat']['events']=[f"VXM_EVENT -2 executing 0 100 {hex(node['event'])} 0"];o.observe(s,g)
        s['concat']['events']=[f"VXM_EVENT -2 executing 0 100 {hex(node['event'])} 1"]
        with self.assertRaisesRegex(ValueError,'wrapper'):o.observe(s,g)
    def test_layer_order_and_restored_faults(self):
        h=concat_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for layer in ('ports','output','start','assignment','primitive','island','filter','thread','wait','code','scope','operand','array','net','wire','signal','mux','gate','arithmetic','reduction','raw_wire','concat'):
            self.assertIn('robotron_'+layer+'_inventory(f, ctx)',h)
        self.assertLess(h.index('    robotron_concat_reference(ctx);'),h.index('    char *before = display_snapshot(ctx, api);'))
        restore=h.index('robotron_concat_fault(ctx,concat_field)!=1)exit(3)');self.assertLess(restore,h.index('int detected=',restore))
        self.assertIn('strcmp(mode,"raw-wire-delayed-corrupt")',h)

if __name__=='__main__':unittest.main()
