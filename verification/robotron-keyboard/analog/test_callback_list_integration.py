import copy,unittest
from pathlib import Path
from unittest.mock import patch
from callback_list_board import CallbackListState
from callback_list_board_review import bundle
from callback_delta import block
from port_identity_review import snapshot
from build_callback_list_bridge import callback_header,HERE
ROOT=HERE/'reports/callback-delta-board-budget'


class CallbackListIntegration(unittest.TestCase):
    def state(self):
        bindings=(ROOT/'bindings.txt').read_text().splitlines()
        bindings=[f'VLB_BEGIN 1 {len(bindings)}']+[l.replace('CB_BIND ','VLB_LINK ') for l in bindings]+['VLB_END']
        tracker=CallbackListState();tracker.set_bindings(bindings);tracker.set_reference((ROOT/'callback-reference.txt').read_text().splitlines())
        ports=snapshot((ROOT/'ports.txt').read_text().splitlines())
        state=dict(threads=dict(tick=0),portState=ports,outputCallbacks=[dict(port=r['index'],callbackId=r['id']) for r in tracker.bindings],callbackListFrame=block((ROOT/'callback-delta-before.txt').read_text().splitlines())[0])
        return tracker,state

    def test_actual_initialized_bridge_bindings(self):
        o,s=self.state();o.observe(s);o.observe(s);self.assertEqual(o.result()['boundOutputCallbacks'],len(o.bindings))

    def test_changed_callback_user_rejected(self):
        o,s=self.state();identity,row=next((i,r) for i,r in o.reference.items() if 'VCL_CALLBACK ' in r);lines=row.splitlines();i=next(i for i,l in enumerate(lines) if l.startswith('VCL_CALLBACK '));a=lines[i].split();a[7]='0x1';lines[i]=' '.join(a);s['callbackListFrame']['rows'][identity]=(0,0,'\n'.join(lines)+'\n')
        with self.assertRaisesRegex(ValueError,'referents'):o.observe(s)

    def test_changed_prior_callback_binding_rejected(self):
        o,s=self.state();s['outputCallbacks'][0]['callbackId']+=999
        with self.assertRaisesRegex(ValueError,'lifetimes'):o.observe(s)

    def test_input_only_port_cannot_own_output_callback(self):
        o,s=self.state();s['portState']['ports'][0]['direction']=2
        with self.assertRaisesRegex(ValueError,'directions'):o.observe(s)

    def test_reference_owner_retirement_cannot_be_reversed(self):
        o,s=self.state();o.observe(s);identity=next(i for i,r in o.reference.items() if 'VCL_CALLBACK ' not in r)
        gone=copy.deepcopy(s);gone['callbackListFrame']['removed']=[identity];gone['callbackListFrame']['total']-=1;o.observe(gone)
        with self.assertRaisesRegex(ValueError,'lifetime'):o.observe(s)

    def test_unsupported_net_array_profile_rejected(self):
        o,s=self.state();identity,row=next((i,r) for i,r in o.reference.items() if 'VCL_CALLBACK ' not in r)
        a=row.splitlines()[0].split();a[5]='0x1';a[7]='1';row=' '.join(a)+'\nVCL_WORD 1 0x1 0x0 0x2 0\n';s['callbackListFrame']['rows'][identity]=(0,0,row)
        with self.assertRaisesRegex(ValueError,'Net-array'):o.observe(s)

    def test_callback_section_preserves_all_previous_records(self):
        prior=['VA_BEGIN','VAR_BEGIN 1 0','VAR_END 0'];delta=(ROOT/'callback-delta-before.txt').read_text().splitlines()
        with patch('callback_list_board_review.prior_bundle',return_value={'threads':{'tick':0},'assignmentRaw':{'sentinel':True}}) as parent:
            state=bundle(prior+delta+['VA_END'],{})
            parent.assert_called_once_with(prior+['VA_END'],{});self.assertEqual(state['assignmentRaw'],{'sentinel':True})

    def test_bridge_preserves_layers_and_restores_before_termination(self):
        h=callback_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for layer in ('ports','output','start','assignment','primitive','island','filter','thread','wait','code','scope','operand','array','net','wire','signal','mux','gate','arithmetic','reduction','raw_wire','concat','resolver','raw_island','raw_assignment','callback'):
            self.assertIn('robotron_'+layer+'_inventory(f, ctx)',h)
        restore=h.index('robotron_output_fault(callback_list_field)!=1)exit(3)')
        self.assertLess(restore,h.index('int direct_rejected=',restore))
        self.assertIn('char*direct=robotron_callback_text(ctx);',h)
        self.assertIn('direct_rejected&&rejected&&equal?2:3',h)


if __name__=='__main__':unittest.main()
