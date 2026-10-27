"""Reject missing or misbound wire state even when counts remain plausible."""
import copy,json,unittest
from pathlib import Path
import wire_board as board
HERE=Path(__file__).resolve().parent
ROOT=HERE/'reports/wire-board-budget'

class WireBoardTests(unittest.TestCase):
    def state(self):
        return (board.graph_parse((ROOT/'before.txt').read_text().splitlines()),
                board.parse((ROOT/'types-before.txt').read_text().splitlines()),
                board.parse_wires((ROOT/'wires-before.txt').read_text().splitlines()))

    def test_retained(self):
        self.assertEqual(board.review(ROOT),json.loads((ROOT/'assessment.json').read_text()))

    def test_missing_and_wrong_binding(self):
        graph,types,wires=self.state()
        bad=copy.deepcopy(wires);bad['filters'].pop()
        with self.assertRaisesRegex(ValueError,'Missing'):board.bind_wires(graph,types,bad)
        for key in ('node','pointer','id','kind'):
            bad=copy.deepcopy(wires);bad['filters'][0][key]+=1
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'binding'):
                board.bind_wires(graph,types,bad)

    def test_wrong_class_and_time(self):
        graph,types,wires=self.state()
        bad=copy.deepcopy(types)
        next(n for n in bad['nodes'] if n['filter'])['filterClass']='vvp_wire_real'
        with self.assertRaisesRegex(ValueError,'binding'):board.bind_wires(graph,bad,wires)
        wires['tick']+=1
        with self.assertRaisesRegex(ValueError,'time mismatch'):board.bind_wires(graph,types,wires)

if __name__=='__main__':unittest.main()
