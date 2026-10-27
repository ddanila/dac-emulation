"""Guard native raw-cache identity and legacy cross-view agreement."""
import copy,json,unittest
from pathlib import Path
import wire_raw_board as board
HERE=Path(__file__).resolve().parent
ROOT=HERE/'reports/wire-raw-board-budget'

class RawWireBoardTests(unittest.TestCase):
    def state(self):
        return (board.graph_parse((ROOT/'before.txt').read_text().splitlines()),
                board.parse((ROOT/'types-before.txt').read_text().splitlines()),
                board.parse_wires((ROOT/'wires-before.txt').read_text().splitlines()),
                board.parse_raw((ROOT/'raw-before.txt').read_text().splitlines()))

    def test_retained(self):
        self.assertEqual(board.review(ROOT),json.loads((ROOT/'assessment.json').read_text()))

    def test_missing_and_rebound(self):
        nodes,types,old,raw=self.state()
        bad=copy.deepcopy(raw);bad['filters'].pop()
        with self.assertRaisesRegex(ValueError,'Missing'):board.bind_raw(nodes,types,old,bad)
        for key in ('node','pointer','id'):
            bad=copy.deepcopy(raw);bad['filters'][0][key]+=1
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'binding'):
                board.bind_raw(nodes,types,old,bad)

    def test_wrong_time_and_class(self):
        nodes,types,old,raw=self.state()
        raw['tick']+=1
        with self.assertRaisesRegex(ValueError,'time mismatch'):board.bind_raw(nodes,types,old,raw)
        raw['tick']-=1
        next(n for n in types['nodes'] if n['filterClass']=='vvp_wire_vec8')['filterClass']='vvp_wire_real'
        with self.assertRaisesRegex(ValueError,'binding'):board.bind_raw(nodes,types,old,raw)

    def test_payload_cross_view(self):
        nodes,types,old,raw=self.state()
        vector=raw['filters'][0]['vectors'][0]
        raw['filters'][0]['vectors'][0]=bytes([0x66])+vector[1:]
        with self.assertRaisesRegex(ValueError,'payload mismatch'):board.bind_raw(nodes,types,old,raw)

    def test_logical_collision_does_not_erase_raw_state(self):
        nodes,types,old,raw=self.state();bad=copy.deepcopy(raw)
        target=next(f for f in bad['filters'] if 0 in f['vectors'][0])
        value=bytearray(target['vectors'][0]);value[value.index(0)]=136;target['vectors'][0]=bytes(value)
        # Both encodings legitimately agree with the old view; raw snapshots must remain distinct.
        self.assertEqual(board.bind_raw(nodes,types,old,raw),board.bind_raw(nodes,types,old,bad))
        self.assertNotEqual(raw,bad)

if __name__=='__main__':unittest.main()
