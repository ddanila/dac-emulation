import copy,unittest
from types import SimpleNamespace
from raw_island_board_review import RawIslandState,FAULTS
from island_raw_delta import block
from island_raw_probe import mutation
from island_probe import parse_snapshot
from net_probe import parse
from net_types_probe import parse as types_parse
from wire_raw_probe import triplet
from build_raw_island_bridge import raw_island_header,HERE
ROOT=HERE/'reports/island-raw-board-budget'

class RawIslandBoardIntegration(unittest.TestCase):
    def state(self):
        lines=(ROOT/'before.txt').read_text().splitlines();nodes=parse(lines)
        graph=SimpleNamespace(nodes=nodes['nodes'],reference={int(l.split()[1]):l for l in lines[1:-1]})
        signals=SimpleNamespace(types=types_parse((ROOT/'types-before.txt').read_text().splitlines()))
        observer=RawIslandState((ROOT/'board.vvp').read_text());observer.set_reference((ROOT/'island_raw-reference.txt').read_text().splitlines(),graph,signals)
        frame,_=block((ROOT/'island_raw-delta-before.txt').read_text().splitlines())
        return observer,graph,dict(islandRaw=frame,islands=parse_snapshot((ROOT/'island-legacy-before.txt').read_text().splitlines()),threads=dict(tick=0),resolver={'marker':'unchanged'})
    def encode(self,observer,state,snapshot):
        rows={}
        for n in snapshot['islands']:
            lines=[f"VIR_ISLAND {n['id']} {hex(n['key'])} {len(n['ports'])}"]
            for p in n['ports']:
                lines.append(f"VIR_PORT {p['id']} {hex(p['net'])} {hex(p['functor'])} {hex(p['filter'])}")
                for f,name in enumerate(('in','out','scratch')):
                    v=p['vectors'][name];lines.append(f"VIR_VECTOR {f} {len(v)} {v.hex() if v else '-'}")
            row='\n'.join(lines)+'\n'
            if row!=observer.reference.get(n['id']):rows[n['id']]=(0,0,row)
        state['islandRaw']['rows']=rows;state['islandRaw']['total']=len(snapshot['islands'])
        for n,legacy in zip(snapshot['islands'],state['islands']['islands']):
            for p,q in zip(n['ports'],legacy['ports']):
                q['vectors']={name:dict(size=len(v),bits=''.join(triplet(b) for b in v) if v else '-') for name,v in p['vectors'].items()}
    def test_initial_binding_and_tick(self):
        o,g,s=self.state();o.observe(s,g);self.assertGreater(o.result()['rawIslandCount'],0)
        s['threads']['tick']=s['islandRaw']['tick']=s['islands']['tick']=42;o.observe(s,g)
        self.assertEqual(o.image(s['islandRaw'])['tick'],42)
        with self.assertRaisesRegex(ValueError,'reset'):o.set_reference([],g,None)
    def test_faults_preserve_other_layers(self):
        for kind,field,op in [('raw-island-cache',0,0),('raw-island-width',1,2),('raw-island-raw',0,1)]:
            o,g,before=self.state();after=copy.deepcopy(before);self.encode(o,after,mutation(o.image(before['islandRaw']),field,op));o.changed(before,after,kind)
            after['resolver']['marker']='changed'
            with self.assertRaisesRegex(ValueError,'preceding'):o.changed(before,after,kind)
    def test_raw_collision_leaves_legacy_equal(self):
        o,g,before=self.state();after=copy.deepcopy(before);self.encode(o,after,mutation(o.image(before['islandRaw']),0,1));self.assertEqual(before['islands'],after['islands']);o.changed(before,after,'raw-island-raw')
    def test_raw_fault_cannot_change_topology(self):
        o,g,before=self.state();after=copy.deepcopy(before);self.encode(o,after,mutation(o.image(before['islandRaw']),0,0));after['islands']['islands'][0]['flag']^=1
        with self.assertRaisesRegex(ValueError,'topology'):o.changed(before,after,'raw-island-cache')
    def test_vector_growth_preserves_allocation(self):
        o,g,s=self.state();snap=copy.deepcopy(o.image(s['islandRaw']));snap['islands'][0]['ports'][0]['vectors']['in']=bytes(9);self.encode(o,s,snap);o.observe(s,g);self.assertGreaterEqual(o.result()['maximumRawIslandCacheBytes'],9)
    def test_graph_rebinding_rejected_after_admission(self):
        o,g,s=self.state();o.observe(s,g);key=o.image(s['islandRaw'])['islands'][0]['ports'][0]['net'];next(n for n in g.nodes if n['key']==key)['fun']+=8
        with self.assertRaisesRegex(ValueError,'binding'):o.observe(s,g)
    def test_unknown_island_requires_readmission(self):
        o,g,s=self.state();snap=copy.deepcopy(o.image(s['islandRaw']));n=copy.deepcopy(snap['islands'][-1]);n['id']+=1;n['key']+=16;snap['islands'].append(n);self.encode(o,s,snap)
        with self.assertRaisesRegex(ValueError,'admitted profile'):o.observe(s,g)
    def test_combined_header_order_and_modes(self):
        h=raw_island_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for layer in ('island','filter','thread','net','wire','signal','mux','gate','arithmetic','reduction','raw_wire','concat','resolver','raw_island'):
            self.assertIn('robotron_'+layer+'_inventory(f, ctx)',h)
        self.assertLess(h.index('    robotron_raw_island_reference(ctx);'),h.index('    char *before = display_snapshot(ctx, api);'))
        restore=h.index('robotron_raw_island_fault(ctx,raw_island_field)!=1)exit(3)');self.assertLess(restore,h.index('int detected=',restore))
        for mode in FAULTS:self.assertIn('strcmp(mode,"'+mode+'-corrupt")',h)
        self.assertIn('strcmp(mode,"resolver-raw-corrupt")',h)

if __name__=='__main__':unittest.main()
