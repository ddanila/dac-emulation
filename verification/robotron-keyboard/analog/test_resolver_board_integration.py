import copy,unittest
from types import SimpleNamespace
from resolver_board_review import ResolverState
from resolver_delta_probe import block
from net_probe import parse
from net_types_probe import parse as types_parse
from build_resolver_bridge import resolver_header,HERE
ROOT=HERE/'reports/resolver-delta-budget'

class ResolverBoardIntegration(unittest.TestCase):
    def state(self):
        lines=(ROOT/'before.txt').read_text().splitlines();nodes=parse(lines)
        graph=SimpleNamespace(nodes=nodes['nodes'],reference={int(l.split()[1]):l for l in lines[1:-1]})
        signals=SimpleNamespace(types=types_parse((ROOT/'types-before.txt').read_text().splitlines()))
        observer=ResolverState((ROOT/'board.vvp').read_text());observer.set_reference((ROOT/'resolver-reference.txt').read_text().splitlines(),graph,signals)
        frame,_=block((ROOT/'resolver-delta-before.txt').read_text().splitlines())
        return observer,graph,dict(resolver=frame,threads=dict(tick=0),concat={'marker':'unchanged'})
    def row(self,observer,state,identity,alter):
        rows=[line.split() for line in observer.reference[identity].splitlines()];alter(rows)
        state['resolver']['rows'][identity]=(0,0,''.join(' '.join(row)+'\n' for row in rows))
    def test_initial_binding_and_current_tick(self):
        o,g,s=self.state();o.observe(s,g);self.assertGreater(o.result()['maximumResolverFunctors'],0)
        s['threads']['tick']=s['resolver']['tick']=42;o.observe(s,g);self.assertEqual(o.image(s['resolver'])['tick'],42)
        with self.assertRaisesRegex(ValueError,'reset'):o.set_reference([],g,None)
    def test_allocation_fault_and_prior_layers(self):
        o,g,before=self.state();after=copy.deepcopy(before);identity=next(iter(o.reference))
        self.row(o,after,identity,lambda rows:rows[0].__setitem__(7,'0x0'))
        o.changed(before,after,'resolver-allocation')
        with self.assertRaisesRegex(ValueError,'binding'):o.observe(after,g)
        after['concat']['marker']='changed'
        with self.assertRaisesRegex(ValueError,'preceding'):o.changed(before,after,'resolver-allocation')
    def test_raw_collision_fault(self):
        o,g,before=self.state();after=copy.deepcopy(before)
        target=next((n,i) for n in o.image(before['resolver'])['nodes'] for i,v in enumerate(n['vectors']) if any(b in (0,136) for b in v))
        def alter(rows):
            row=rows[target[1]+1];value=bytearray.fromhex(row[3]);i=next(i for i,b in enumerate(value) if b in (0,136));value[i]^=136;row[3]=value.hex()
        self.row(o,after,target[0]['id'],alter);o.changed(before,after,'resolver-raw')
    def test_cache_fault(self):
        o,g,before=self.state();after=copy.deepcopy(before)
        node,index=next((n,i) for n in o.image(before['resolver'])['nodes'] for i,v in enumerate(n['vectors']) if v)
        def alter(rows):
            row=rows[index+1];v=bytearray.fromhex(row[3]);v[0]=0x66 if v[0]==0xee else 0xee;row[3]=v.hex()
        self.row(o,after,node['id'],alter);o.changed(before,after,'resolver-cache')
    def test_cache_width_growth_is_not_allocation_rebinding(self):
        o,g,s=self.state();identity=next(iter(o.reference))
        self.row(o,s,identity,lambda rows:rows[1].__setitem__(slice(2,4),['9','00'*9]))
        o.observe(s,g);self.assertGreaterEqual(o.result()['maximumResolverCacheBytes'],9)
    def test_graph_rebinding(self):
        o,g,s=self.state();identity=next(iter(o.expected));g.nodes[identity-1]['fun']+=1
        with self.assertRaisesRegex(ValueError,'binding'):o.observe(s,g)
    def test_new_allocation_requires_readmission(self):
        o,g,s=self.state();identity=max(o.reference)+1;rows=[l.split() for l in next(iter(o.reference.values())).splitlines()];rows[0][1:4]=[str(identity),'0x110','0x120']
        s['resolver']['total']+=1;s['resolver']['rows'][identity]=(0,0,''.join(' '.join(row)+'\n' for row in rows))
        with self.assertRaisesRegex(ValueError,'admitted profile'):o.observe(s,g)
    def test_layer_order_and_restored_faults(self):
        h=resolver_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for layer in ('ports','output','start','assignment','primitive','island','filter','thread','wait','code','scope','operand','array','net','wire','signal','mux','gate','arithmetic','reduction','raw_wire','concat','resolver'):
            self.assertIn('robotron_'+layer+'_inventory(f, ctx)',h)
        self.assertLess(h.index('    robotron_resolver_reference(ctx);'),h.index('    char *before = display_snapshot(ctx, api);'))
        restore=h.index('robotron_resolver_fault(ctx,resolver_field)!=1)exit(3)');self.assertLess(restore,h.index('int detected=',restore))
        self.assertIn('toggle(saved,field,saved_index)',h)
        self.assertIn('strcmp(mode,"concat-raw-corrupt")',h)

if __name__=='__main__':unittest.main()
