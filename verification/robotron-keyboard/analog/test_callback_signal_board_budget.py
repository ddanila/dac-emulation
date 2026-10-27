import json,shutil,tempfile,unittest
from pathlib import Path
from callback_signal_board_budget import HERE,review
from retained_evidence import check
ROOT=HERE/'reports/callback-signal-board-budget'


class CallbackSignalBoardBudget(unittest.TestCase):
    def test_real_board_links_and_full_preflight_budget(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_link_cost_is_not_mislabeled_as_handle_cost(self):
        r=review(ROOT);self.assertNotIn('scanTimings',r['initializedBindings']);self.assertNotIn('initialStateProjection',r['initializedBindings']);self.assertGreater(r['linkScanTimings']['meanSeconds'],0)
    def mutate_link(self,index,value):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root)
            for name in ('links-before.txt','links-after.txt'):
                p=root/name;lines=p.read_text().splitlines();a=lines[1].split();self.assertNotEqual(a[index],value);a[index]=value;lines[1]=' '.join(a);p.write_text('\n'.join(lines)+'\n')
            with self.assertRaises(ValueError):review(root)
    def test_registered_filter_required(self):self.mutate_link(7,'0x1')
    def test_registered_owner_required(self):self.mutate_link(5,'99999')
    def test_signal_handle_identity_required(self):self.mutate_link(3,'99999')
    def test_callback_allocation_required(self):self.mutate_link(2,'0x1')
    def test_graph_node_lifetime_required(self):self.mutate_link(8,'99999')


if __name__=='__main__':unittest.main()
