import copy,json,unittest
from pathlib import Path
from island_raw_contract import profile,HERE
ROOT=HERE/'reports/island-raw-contract'
BOARD=HERE/'reports/resolver-board-budget/board.vvp'

class IslandRawContract(unittest.TestCase):
    def test_compiled_membership_replay(self):
        result=json.loads((ROOT/'assessment.json').read_text())
        self.assertEqual(profile(BOARD.read_text()),result['compiledProfile'])
        self.assertEqual(set(result['requiredRawStorage']),{'vvp_island_port.invalue','vvp_island_port.outvalue','vvp_island_port.value','assign_vector8_event_s.val'})
    def test_foreign_branch_port_rejected(self):
        text=BOARD.read_text();p=profile(text);branch=p['branches'][0];other=next(v for v in p['ports'] if v['island']!=branch['island'])
        text=text.replace(branch['a']+' '+branch['b']+',',other['label']+' '+branch['b']+',')
        with self.assertRaisesRegex(ValueError,'foreign port'):profile(text)
    def test_unsupported_family_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unsupported'):profile(BOARD.read_text().replace('.island tran;','.island unknown;',1))
    def test_duplicate_port_rejected(self):
        text=BOARD.read_text();line=next(l for l in text.splitlines() if ' .port ' in l)
        with self.assertRaisesRegex(ValueError,'aliased'):profile(text+'\n'+line+'\n')
    def test_dispatch_order_and_distinct_payload_evidence(self):
        e=json.loads((ROOT/'assessment.json').read_text())['evidence']
        body=e['outputThenScratchClear']['excerpt']
        self.assertLess(body.index('island_send_value(a, port->value)'),body.index('port->value = vvp_vector8_t::nil'))
        self.assertIn('vvp_vector8_t val;',e['assignmentPayloadAndDispatch']['excerpt'])
        self.assertNotIn('vvp_vector8_t',e['genericWrapper']['excerpt'])

if __name__=='__main__':unittest.main()
