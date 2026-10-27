import copy,json,unittest
from assignment_raw_board import HERE,review,bind_assignments,graph_parse,parse_types,parse_raw,parse_snapshot
from retained_evidence import check
ROOT=HERE/'reports/assignment-raw-board-budget'

class AssignmentRawBoard(unittest.TestCase):
    def state(self):
        return [graph_parse((ROOT/'before.txt').read_text().splitlines()),parse_types((ROOT/'types-before.txt').read_text().splitlines()),parse_raw((ROOT/'assignment_raw-before.txt').read_text().splitlines()),parse_snapshot((ROOT/'assignment-legacy-before.txt').read_text().splitlines()),(ROOT/'queue-before.txt').read_text().splitlines()]
    def test_native_budget_replay(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_missing_native_assignment_rejected(self):
        args=self.state();e=args[2]['events'].pop();args[3]['events']=[a for a in args[3]['events'] if a['id']!=e['id']]
        with self.assertRaisesRegex(ValueError,'queue positions'):bind_assignments(*args)
    def test_wrong_destination_rejected(self):
        args=self.state();e=args[2]['events'][0];e['target']='0x4';next(a for a in args[3]['events'] if a['id']==e['id'])['target']='0x4'
        with self.assertRaisesRegex(ValueError,'destination'):bind_assignments(*args)
    def test_native_class_rebinding_rejected(self):
        args=self.state();args[1]['nodes'][0]['fun']+=8
        with self.assertRaisesRegex(ValueError,'binding'):bind_assignments(*args)
    def test_missing_legacy_payload_rejected(self):
        args=self.state();args[3]['events']=[e for e in args[3]['events'] if e['kind']!=8]
        with self.assertRaisesRegex(ValueError,'Legacy'):bind_assignments(*args)
    def test_queue_time_mismatch_rejected(self):
        args=self.state();args[2]['tick']=args[3]['tick']=1
        with self.assertRaisesRegex(ValueError,'time'):bind_assignments(*args)

if __name__=='__main__':unittest.main()
