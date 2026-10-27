"""Signal admission must cover every native signal and refuse other storage."""
import copy,json,shutil,tempfile,unittest
from pathlib import Path
import signal_board as board
import signal_family_probe as families
HERE=Path(__file__).resolve().parent
ROOT=HERE/'reports/signal-board-budget'

class SignalAdmission(unittest.TestCase):
    def state(self):
        return (board.graph_parse((ROOT/'before.txt').read_text().splitlines()),
                board.parse((ROOT/'types-before.txt').read_text().splitlines()),
                board.parse_signals((ROOT/'signals-before.txt').read_text().splitlines()),
                (ROOT/'board.vvp').read_text())
    def test_retained(self):
        self.assertEqual(board.review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
        root=HERE/'reports/signal-families'
        self.assertEqual(families.review(root),json.loads((root/'assessment.json').read_text()))
    def test_missing_binding_or_unallocated_source(self):
        graph,types,signals,compiled=self.state()
        bad=copy.deepcopy(signals);bad['signals'].pop()
        with self.assertRaisesRegex(ValueError,'Missing'):board.bind_signals(graph,types,bad,compiled)
        for field in ('node','fun','link'):
            bad=copy.deepcopy(signals);bad['signals'][0][field]=4
            with self.subTest(field=field),self.assertRaises(ValueError):board.bind_signals(graph,types,bad,compiled)
    def test_wrong_width_and_class(self):
        graph,types,signals,compiled=self.state();signals['signals'][0]['width']+=1
        with self.assertRaisesRegex(ValueError,'widths'):board.bind_signals(graph,types,signals,compiled)
        graph,types,signals,compiled=self.state()
        next(n for n in types['nodes'] if n['funClass']=='vvp_fun_signal4_sa')['funClass']='vvp_fun_signal_real_sa'
        with self.assertRaisesRegex(ValueError,'class/graph'):board.bind_signals(graph,types,signals,compiled)
    def test_partial_refusal_not_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'report';shutil.copytree(HERE/'reports/signal-families',root)
            p=root/'real-observe.stdout';p.write_text(p.read_text()+'VSG_BEGIN 1 0\n')
            with self.assertRaisesRegex(ValueError,'partial'):families.review(root)

if __name__=='__main__':unittest.main()
