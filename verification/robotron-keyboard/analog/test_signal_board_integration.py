"""Signal board integration preserves identity, assignment links and prior state."""
import copy,unittest
from pathlib import Path
from types import SimpleNamespace
from signal_board_review import SignalState
from signal_delta_probe import block
from net_probe import parse
from build_signal_bridge import signal_header,HERE
ROOT=HERE/'reports/signal-delta-budget'

class SignalBoardIntegration(unittest.TestCase):
    def setup_state(self):
        lines=(ROOT/'before.txt').read_text().splitlines();parsed=parse(lines)
        graph=SimpleNamespace(nodes=parsed['nodes'],reference={int(l.split()[1]):l for l in lines[1:-1]})
        signals=SignalState((ROOT/'board.vvp').read_text())
        signals.set_types((ROOT/'types-before.txt').read_text().splitlines(),graph)
        signals.set_reference((ROOT/'signal-reference.txt').read_text().splitlines())
        frame,_=block((ROOT/'signal-delta-before.txt').read_text().splitlines())
        return signals,graph,dict(signals=frame,threads=dict(tick=0))
    def test_complete_native_bindings(self):
        signals,graph,state=self.setup_state();signals.observe(state,graph)
        self.assertGreater(signals.result()['maximumSignalFunctors'],0)
        with self.assertRaisesRegex(ValueError,'reset'):signals.set_reference((ROOT/'signal-reference.txt').read_text().splitlines())
    def test_wrong_graph_functor_rejected(self):
        signals,graph,state=self.setup_state();identity=signals.expected[0]['id']
        next(n for n in graph.nodes if n['id']==identity)['fun']=4
        with self.assertRaisesRegex(ValueError,'binding'):signals.observe(state,graph)
    def test_exact_fault_and_preceding_state(self):
        signals,graph,before=self.setup_state();identity=next(iter(signals.reference))
        row=signals.reference[identity].split();row[4]=str(int(row[4])^1)
        after=copy.deepcopy(before);after['signals']['rows']={identity:(0,0,' '.join(row)+'\n')}
        signals.changed(before,after,'signal-init')
        after['threads']['tick']=1
        with self.assertRaisesRegex(ValueError,'preceding'):signals.changed(before,after,'signal-init')
    def test_assignment_source_requires_port_one_fanout(self):
        signals,graph,state=self.setup_state();signal=copy.deepcopy(signals.image(state['signals'])['signals'][0])
        target=next(n for n in graph.nodes if n['id']==signal['id'])
        source=next(n for n in graph.nodes if n['id']!=signal['id'])
        signal['link']=source['key'];source['out']=(target['key'],target['id'],1);target['ports'][1]=(0,0,0)
        signals.assignment_link(signal,graph.nodes)
        source['out']=(target['key'],target['id'],0);target['ports'][0]=(0,0,0)
        with self.assertRaisesRegex(ValueError,'port-1'):signals.assignment_link(signal,graph.nodes)
        signal['link']=4
        with self.assertRaisesRegex(ValueError,'Unallocated'):signals.assignment_link(signal,graph.nodes)
    def test_bridge_all_layers_and_restore(self):
        header=signal_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for name in ('ports','output','start','assignment','primitive','island','filter','thread','wait','code','scope','operand','array','net','wire','signal'):
            self.assertIn('robotron_'+name+'_inventory(f, ctx)',header)
        self.assertIn('robotron_vvp_net_types',header)
        self.assertLess(header.index('    robotron_signal_reference(ctx);'),header.index('    char *before = display_snapshot(ctx, api);'))
        restore=header.index('robotron_signal_fault(ctx,signal_field)!=1)exit(3)')
        self.assertLess(restore,header.index('int detected=',restore))

if __name__=='__main__':unittest.main()
