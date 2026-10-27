"""Combined arithmetic observations preserve prior layers and native admission."""
import copy,unittest
from types import SimpleNamespace
from arithmetic_board_review import ArithmeticState
from arithmetic_delta_probe import block
from net_probe import parse
from net_types_probe import parse as types_parse
from build_arithmetic_bridge import arithmetic_header,HERE
ROOT=HERE/'reports/arithmetic-delta-budget'

class ArithmeticBoardIntegration(unittest.TestCase):
    def setup_state(self):
        lines=(ROOT/'before.txt').read_text().splitlines();parsed=parse(lines)
        graph=SimpleNamespace(nodes=parsed['nodes'],reference={int(l.split()[1]):l for l in lines[1:-1]})
        signals=SimpleNamespace(types=types_parse((ROOT/'types-before.txt').read_text().splitlines()))
        arithmetic=ArithmeticState((ROOT/'board.vvp').read_text())
        arithmetic.set_reference((ROOT/'arithmetic-reference.txt').read_text().splitlines(),graph,signals)
        frame,_=block((ROOT/'arithmetic-delta-before.txt').read_text().splitlines())
        return arithmetic,graph,dict(arithmetic=frame,threads=dict(tick=0),gates=dict(marker='unchanged'))
    def test_native_bindings_and_current_tick(self):
        observer,graph,state=self.setup_state();observer.observe(state,graph)
        self.assertGreater(observer.result()['maximumArithmeticFunctors'],0)
        state['arithmetic']['tick']=state['threads']['tick']=20;observer.observe(state,graph)
        self.assertEqual(observer.image(state['arithmetic'])['tick'],20)
        with self.assertRaisesRegex(ValueError,'reset'):observer.set_reference([],graph,None)
    def test_foreign_allocation(self):
        observer,graph,state=self.setup_state();identity=next(iter(observer.expected))
        next(n for n in graph.nodes if n['id']==identity)['fun']=4
        with self.assertRaisesRegex(ValueError,'binding'):observer.observe(state,graph)
    def test_each_fault_and_prior_state(self):
        for field,name in enumerate(('input0','input1','fallback','width')):
            observer,graph,before=self.setup_state();identity=next(iter(observer.reference));row=observer.reference[identity].split()
            if field==3:row[5]=str(int(row[5])^1)
            else:
                col=7+field*2;row[col]=('0' if row[col][0]=='1' else '1')+row[col][1:]
            after=copy.deepcopy(before);after['arithmetic']['rows']={identity:(0,0,' '.join(row)+'\n')}
            observer.changed(before,after,'arithmetic-'+name)
            if field>=2:
                with self.assertRaises(ValueError):observer.observe(after,graph)
            after['gates']['marker']='changed'
            with self.assertRaisesRegex(ValueError,'preceding'):observer.changed(before,after,'arithmetic-'+name)
    def test_unadmitted_growth(self):
        observer,graph,state=self.setup_state();identity=max(observer.reference)+1;row=next(iter(observer.reference.values())).split()
        row[1]=str(identity);row[2]='0x110';row[3]='0x120'
        state['arithmetic']['total']+=1;state['arithmetic']['rows'][identity]=(0,0,' '.join(row)+'\n')
        with self.assertRaisesRegex(ValueError,'admitted profile'):observer.observe(state,graph)
    def test_all_layers_and_restore_order(self):
        header=arithmetic_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for name in ('ports','output','start','assignment','primitive','island','filter','thread','wait','code','scope','operand','array','net','wire','signal','mux','gate','arithmetic'):
            self.assertIn('robotron_'+name+'_inventory(f, ctx)',header)
        self.assertLess(header.index('    robotron_arithmetic_reference(ctx);'),header.index('    char *before = display_snapshot(ctx, api);'))
        restore=header.index('robotron_arithmetic_fault(ctx,arithmetic_field)!=1)exit(3)')
        self.assertLess(restore,header.index('int detected=',restore))
        self.assertIn('sscanf(line,"VAR_NODE %llu %*s %*s %d"',header)
        for name in ('input0','input1','fallback','width'):self.assertIn('arithmetic-'+name+'-corrupt',header)
        self.assertIn('strcmp(mode,"gate-invert-corrupt")',header)

if __name__=='__main__':unittest.main()
