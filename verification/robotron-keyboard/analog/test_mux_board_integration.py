"""Combined mux observations preserve prior layers and native ownership."""
import copy,unittest
from pathlib import Path
from types import SimpleNamespace
from mux_board_review import MuxState
from mux_delta_probe import block
from net_probe import parse
from net_types_probe import parse as types_parse
from build_mux_bridge import mux_header,HERE
ROOT=HERE/'reports/mux-delta-budget'

class MuxBoardIntegration(unittest.TestCase):
    def setup_state(self):
        lines=(ROOT/'before.txt').read_text().splitlines();parsed=parse(lines)
        graph=SimpleNamespace(nodes=parsed['nodes'],reference={int(l.split()[1]):l for l in lines[1:-1]})
        signals=SimpleNamespace(types=types_parse((ROOT/'types-before.txt').read_text().splitlines()))
        muxes=MuxState((ROOT/'board.vvp').read_text())
        muxes.set_reference((ROOT/'mux-reference.txt').read_text().splitlines(),graph,signals)
        frame,_=block((ROOT/'mux-delta-before.txt').read_text().splitlines())
        return muxes,graph,dict(muxes=frame,threads=dict(tick=0),signals=dict(marker='unchanged'))
    def test_complete_native_bindings(self):
        muxes,graph,state=self.setup_state();muxes.observe(state,graph)
        self.assertGreater(muxes.result()['maximumMuxFunctors'],0)
        with self.assertRaisesRegex(ValueError,'reset'):muxes.set_reference([],graph,None)
    def test_foreign_class_binding(self):
        muxes,graph,state=self.setup_state();identity=next(iter(muxes.expected))
        next(n for n in graph.nodes if n['id']==identity)['fun']=4
        with self.assertRaisesRegex(ValueError,'binding'):muxes.observe(state,graph)
    def test_fault_exact_and_prior_layers_unchanged(self):
        muxes,graph,before=self.setup_state();identity=next(iter(muxes.reference))
        row=muxes.reference[identity].split();row[9]=('0' if row[9][0]=='1' else '1')+row[9][1:]
        after=copy.deepcopy(before);after['muxes']['rows']={identity:(0,0,' '.join(row)+'\n')}
        muxes.changed(before,after,'mux-a')
        after['signals']['marker']='changed'
        with self.assertRaisesRegex(ValueError,'preceding'):muxes.changed(before,after,'mux-a')
    def test_cached_images_include_wrappers(self):
        muxes,graph,state=self.setup_state();self.assertFalse(muxes.image(state['muxes'])['events'])
        frame=copy.deepcopy(state['muxes']);key=muxes.image(frame)['muxes'][0]['event']
        frame['events']=[f'VXM_EVENT -2 executing 0 999 {hex(key)} 0']
        self.assertEqual(len(muxes.image(frame)['events']),1)
        self.assertFalse(muxes.image(state['muxes'])['events'])
        frame['tick']=100
        self.assertEqual(muxes.image(frame)['tick'],100)
    def test_unadmitted_growth(self):
        muxes,graph,state=self.setup_state();identity=max(muxes.reference)+1
        row=next(iter(muxes.reference.values())).split();row[1]=str(identity)
        row[2]='0x110';row[3]='0x120';row[4]='0x128';row[5]='0x0'
        state['muxes']['total']+=1;state['muxes']['rows'][identity]=(0,0,' '.join(row)+'\n')
        with self.assertRaisesRegex(ValueError,'admitted profile'):muxes.observe(state,graph)
    def test_bridge_preserves_layers_and_restores_before_verdict(self):
        header=mux_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for name in ('ports','output','start','assignment','primitive','island','filter','thread','wait','code','scope','operand','array','net','wire','signal','mux'):
            self.assertIn('robotron_'+name+'_inventory(f, ctx)',header)
        self.assertEqual(header.count('dlsym(ctx->vvp_handle,"robotron_vvp_net_types")'),1)
        self.assertLess(header.index('    robotron_mux_reference(ctx);'),header.index('    char *before = display_snapshot(ctx, api);'))
        restore=header.index('robotron_mux_fault(ctx,mux_field)!=1)exit(3)')
        self.assertLess(restore,header.index('int detected=',restore))
        self.assertIn('VB_MUX_FAULT',header)
        for name in ('a','b','select','run'):self.assertIn('mux-'+name+'-corrupt',header)

if __name__=='__main__':unittest.main()
