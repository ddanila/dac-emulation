"""Combined reduction observations preserve prior layers and native admission."""
import copy,unittest
from types import SimpleNamespace
from reduction_board_review import ReductionState
from reduction_delta_probe import block
from net_probe import parse
from net_types_probe import parse as types_parse
from build_reduction_bridge import reduction_header,HERE
ROOT=HERE/'reports/reduction-delta-budget'

class ReductionBoardIntegration(unittest.TestCase):
    def setup_state(self):
        lines=(ROOT/'before.txt').read_text().splitlines();parsed=parse(lines)
        graph=SimpleNamespace(nodes=parsed['nodes'],reference={int(l.split()[1]):l for l in lines[1:-1]})
        signals=SimpleNamespace(types=types_parse((ROOT/'types-before.txt').read_text().splitlines()))
        reduction=ReductionState((ROOT/'board.vvp').read_text())
        reduction.set_reference((ROOT/'reduction-reference.txt').read_text().splitlines(),graph,signals)
        frame,_=block((ROOT/'reduction-delta-before.txt').read_text().splitlines())
        return reduction,graph,dict(reduction=frame,threads=dict(tick=0),gates=dict(marker='unchanged'))
    def test_native_bindings_and_current_tick(self):
        observer,graph,state=self.setup_state();observer.observe(state,graph)
        self.assertGreater(observer.result()['maximumReductionFunctors'],0)
        state['reduction']['tick']=state['threads']['tick']=20;observer.observe(state,graph)
        self.assertEqual(observer.image(state['reduction'])['tick'],20)
        with self.assertRaisesRegex(ValueError,'reset'):observer.set_reference([],graph,None)
    def test_foreign_allocation(self):
        observer,graph,state=self.setup_state();identity=next(iter(observer.expected))
        next(n for n in graph.nodes if n['id']==identity)['fun']=4
        with self.assertRaisesRegex(ValueError,'binding'):observer.observe(state,graph)
    def test_each_fault_and_prior_state(self):
        for field,name in enumerate(('bit','size')):
            observer,graph,before=self.setup_state()
            target=next(n for n in observer.image(before['reduction'])['nodes'] if field==1 or n['bits'])
            identity=target['id'];row=observer.reference[identity].split()
            if field==1:row[5]=str(int(row[5])+1);row[6]='3'*int(row[5])
            else:row[6]=('0' if row[6][0]=='1' else '1')+row[6][1:]
            after=copy.deepcopy(before);after['reduction']['rows']={identity:(0,0,' '.join(row)+'\n')}
            observer.changed(before,after,'reduction-'+name)
            after['gates']['marker']='changed'
            with self.assertRaisesRegex(ValueError,'preceding'):observer.changed(before,after,'reduction-'+name)
    def test_initially_empty_cache_can_grow(self):
        observer,graph,state=self.setup_state()
        target=next(n for n in observer.image(state['reduction'])['nodes'] if not n['bits'])
        identity=target['id'];row=observer.reference[identity].split();row[5]='80';row[6]='0'*80
        state['reduction']['rows']={identity:(0,0,' '.join(row)+'\n')}
        observer.observe(state,graph)
        self.assertEqual(next(n for n in observer.image(state['reduction'])['nodes'] if n['id']==identity)['bits'],'0'*80)
    def test_unadmitted_growth(self):
        observer,graph,state=self.setup_state();identity=max(observer.reference)+1;row=next(iter(observer.reference.values())).split()
        row[1]=str(identity);row[2]='0x110';row[3]='0x120'
        state['reduction']['total']+=1;state['reduction']['rows'][identity]=(0,0,' '.join(row)+'\n')
        with self.assertRaisesRegex(ValueError,'admitted profile'):observer.observe(state,graph)
    def test_all_layers_and_restore_order(self):
        header=reduction_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for name in ('ports','output','start','assignment','primitive','island','filter','thread','wait','code','scope','operand','array','net','wire','signal','mux','gate','arithmetic','reduction'):
            self.assertIn('robotron_'+name+'_inventory(f, ctx)',header)
        self.assertLess(header.index('    robotron_reduction_reference(ctx);'),header.index('    char *before = display_snapshot(ctx, api);'))
        restore=header.index('robotron_reduction_fault(ctx,reduction_field)!=1)exit(3)')
        self.assertLess(restore,header.index('int detected=',restore))
        self.assertIn('sscanf(line,"VRD_NODE %llu %*s %*s %d"',header)
        for name in ('bit','size'):self.assertIn('reduction-'+name+'-corrupt',header)
        self.assertIn('strcmp(mode,"arithmetic-width-corrupt")',header)

if __name__=='__main__':unittest.main()
