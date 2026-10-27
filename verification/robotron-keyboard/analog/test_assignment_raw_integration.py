import copy,unittest
from types import SimpleNamespace
from unittest.mock import patch
from raw_assignment_board_review import RawAssignmentState,FAULTS,bundle
from assignment_raw import mutation
from assignment_raw_board import HERE,graph_parse,parse_types,parse_raw,parse_snapshot
from build_raw_assignment_bridge import raw_assignment_header
from wire_raw_probe import triplet
ROOT=HERE/'reports/assignment-raw-board-budget'

class RawAssignmentIntegration(unittest.TestCase):
    def state(self):
        g=graph_parse((ROOT/'before.txt').read_text().splitlines());types=parse_types((ROOT/'types-before.txt').read_text().splitlines())
        state=dict(assignmentRaw=parse_raw((ROOT/'assignment_raw-before.txt').read_text().splitlines()),assignments=parse_snapshot((ROOT/'assignment-legacy-before.txt').read_text().splitlines()),threads=dict(tick=0),islandRaw={'marker':'unchanged'})
        return RawAssignmentState(),SimpleNamespace(nodes=g['nodes']),SimpleNamespace(types=types),state
    def fault(self,state,op):
        out=copy.deepcopy(state);target=state['assignmentRaw']['events'][0];out['assignmentRaw']=mutation(state['assignmentRaw'],target['id'],op);new=out['assignmentRaw']['events'][0]
        e=next(e for e in out['assignments']['events'] if e['id']==target['id']);e.update(port=new['port'],size=len(new['raw']),bits=''.join(triplet(b) for b in new['raw']) or '-')
        return out
    def test_admission_and_consumption(self):
        o,g,t,s=self.state();o.observe(s,g,t);self.assertGreater(o.result()['pendingRawAssignments'],0)
        empty=copy.deepcopy(s);empty['assignmentRaw']['events']=[];empty['assignments']['events']=[e for e in empty['assignments']['events'] if e['kind']!=8];o.observe(empty,g,t)
        with self.assertRaisesRegex(ValueError,'lifetime'):o.observe(s,g,t)
    def test_all_board_faults_and_prior_layers(self):
        for kind,op in FAULTS.items():
            o,g,t,s=self.state();after=self.fault(s,op);o.changed(s,after,kind);after['islandRaw']['marker']='changed'
            with self.assertRaisesRegex(ValueError,'preceding'):o.changed(s,after,kind)
    def test_unrelated_four_state_assignment_protected(self):
        o,g,t,s=self.state();after=self.fault(s,0);e=next(e for e in after['assignments']['events'] if e['kind']==4);e['port']^=1
        with self.assertRaisesRegex(ValueError,'unrelated'):o.changed(s,after,'raw-assignment-byte')
    def test_changed_raw_collision_rejected_even_if_legacy_equal(self):
        o,g,t,s=self.state();e=s['assignmentRaw']['events'][0];e['raw']=b'\x00';next(a for a in s['assignments']['events'] if a['id']==e['id'])['bits']='200';o.observe(s,g,t)
        e['raw']=b'\x88'
        with self.assertRaisesRegex(ValueError,'payload changed'):o.observe(s,g,t)
    def test_executing_transfer_keeps_lifetime(self):
        o,g,t,s=self.state();o.observe(s,g,t);e=s['assignmentRaw']['events'][0];s['assignments']['events']=[a for a in s['assignments']['events'] if a['id']!=e['id']];e.update(slot=-2,region='executing',ordinal=0);o.observe(s,g,t);self.assertEqual(o.result()['executingRawAssignments'],1)
    def test_unknown_graph_target_rejected(self):
        o,g,t,s=self.state();e=s['assignmentRaw']['events'][0];e['target']='0x4';next(a for a in s['assignments']['events'] if a['id']==e['id'])['target']='0x4'
        with self.assertRaisesRegex(ValueError,'graph/classes'):o.observe(s,g,t)
    def test_bridge_contains_prior_layers_and_restores_faults(self):
        h=raw_assignment_header((HERE/'fixtures/display_board_bridge.h').read_text())
        for layer in ('net','wire','signal','mux','gate','arithmetic','reduction','raw_wire','concat','resolver','raw_island','raw_assignment'):self.assertIn('robotron_'+layer+'_inventory(f, ctx)',h)
        for mode in FAULTS:self.assertIn('strcmp(mode,"'+mode+'-corrupt")',h)
        restore=h.index('robotron_raw_assignment_fault(ctx,raw_assignment_op)!=1)exit(3)');self.assertLess(restore,h.index('int detected=',restore))
    def test_raw_section_does_not_consume_compact_array_records(self):
        prior=['VA_BEGIN','VAC_BEGIN 1 0','VAR_ARRAY preserved','VAC_END 1 0','VIX_BEGIN D 0 0 0','VIX_END 0']
        raw=(ROOT/'assignment_raw-before.txt').read_text().splitlines()
        with patch('raw_assignment_board_review.prior_bundle',return_value={'threads':{'tick':0}}) as parent:
            state=bundle(prior+raw+['VA_END'],{})
            parent.assert_called_once_with(prior+['VA_END'],{});self.assertEqual(state['assignmentRaw'],parse_raw(raw))

if __name__=='__main__':unittest.main()
