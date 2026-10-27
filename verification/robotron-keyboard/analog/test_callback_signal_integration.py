import copy,json,unittest
from pathlib import Path
from types import SimpleNamespace
from callback_signal_board import SignalHandleState
from callback_signal_links import parse as link_parse
from signal_handles import parse as signal_parse
from callback_list_probe import parse as list_parse
from net_probe import parse as graph_parse,pointer
from port_identity_review import snapshot
from signal_handle_board_budget import scope_ids
from callback_signal_preflight import review,HERE
from retained_evidence import check
ROOT=HERE/'reports/callback-signal-preflight'
BOARD=HERE/'reports/callback-signal-board-budget'


class CallbackSignalIntegration(unittest.TestCase):
    def test_full_combined_startup_fault_replay(self):
        check(ROOT);self.assertEqual(json.loads(json.dumps(review(ROOT))),json.loads((ROOT/'assessment.json').read_text()))

    def native_state(self):
        read=lambda name:(BOARD/name).read_text().splitlines()
        tracker=SignalHandleState((BOARD/'io.vvp').read_text())
        bindings=read('handle-bindings.txt');tracker.set_bindings([f'VHB_BEGIN 1 {len(bindings)}',*[s.replace('SH_BIND','VHB_LINK') for s in bindings],'VHB_END'])
        lists=list_parse(read('callbacks-before.txt'));cb=[]
        for line in read('bindings.txt'):
            a=line.split();cb.append(dict(index=int(a[1]),id=int(a[2]),user=pointer(a[3]),pointer=pointer(a[4]),object=pointer(a[5]),function=pointer(a[6])))
        callbacks=SimpleNamespace(bindings=cb,previous={o['id'] for o in lists['owners']},identities={o['id']:(o['pointer'],o['kind']) for o in lists['owners']},callback_identities={c['id']:(o['id'],c['pointer'],c['time'],c['value']) for o in lists['owners'] for c in o['callbacks']})
        graph=SimpleNamespace(nodes=graph_parse(read('handle-graph.txt'))['nodes'])
        state=dict(threads={'tick':0},typedSignals=signal_parse(read('handles-before.txt')),callbackSignalLinks=link_parse(read('links-before.txt')),portState=snapshot(read('ports.txt')),scopes=[dict(id=i,pointer=p) for i,p in scope_ids(read('handle-scopes.txt')).items()])
        return tracker,state,graph,callbacks

    def test_native_board_state_is_admitted(self):
        tracker,state,graph,callbacks=self.native_state();tracker.observe(state,graph,callbacks);tracker.observe(state,graph,callbacks);self.assertEqual(tracker.result()['typedSignalObservations'],2)
    def test_signed_metadata_must_match_compiled_interface(self):
        tracker,state,graph,callbacks=self.native_state();state['typedSignals']['rows'][0]['signed']^=1
        with self.assertRaisesRegex(ValueError,'compiled'):tracker.observe(state,graph,callbacks)
    def test_missing_signal_handoff_rejected(self):
        tracker,state,graph,callbacks=self.native_state();tracker.bindings=None
        with self.assertRaisesRegex(ValueError,'handoff'):tracker.observe(state,graph,callbacks)
    def test_owner_lifetime_cross_binding_required(self):
        tracker,state,graph,callbacks=self.native_state();state['callbackSignalLinks']['rows'][0]['ownerId']=999999
        with self.assertRaisesRegex(ValueError,'owner lifetime'):tracker.observe(state,graph,callbacks)
    def test_filter_cross_binding_required(self):
        tracker,state,graph,callbacks=self.native_state();state['callbackSignalLinks']['rows'][0]['filter']=1
        with self.assertRaisesRegex(ValueError,'filter'):tracker.observe(state,graph,callbacks)
    def test_retired_owner_cannot_supply_link(self):
        tracker,state,graph,callbacks=self.native_state();callbacks.previous.remove(state['callbackSignalLinks']['rows'][0]['ownerId'])
        with self.assertRaisesRegex(ValueError,'owner lifetime'):tracker.observe(state,graph,callbacks)
    def test_native_time_must_match(self):
        tracker,state,graph,callbacks=self.native_state();state['typedSignals']['tick']=1
        with self.assertRaisesRegex(ValueError,'time'):tracker.observe(state,graph,callbacks)


if __name__=='__main__':unittest.main()
