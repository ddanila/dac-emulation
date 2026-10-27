import json,shutil,tempfile,unittest
from pathlib import Path
from callback_list_preflight import HERE,review
from retained_evidence import check
ROOT=HERE/'reports/callback-list-preflight'


class CallbackListPreflight(unittest.TestCase):
    def test_real_board_startup_faults_replay_all_layers(self):
        check(ROOT);self.assertEqual(json.loads(json.dumps(review(ROOT))),json.loads((ROOT/'assessment.json').read_text()))

    def test_preflight_cannot_be_claimed_as_normal_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/'callback-list-user-corrupt/run.json';r=json.loads(p.read_text());r['startupOnly']=False;p.write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'startup fault'):review(root)

    def test_unexpected_success_exit_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/'callback-list-user-corrupt/run.json';r=json.loads(p.read_text());r['exitCode']=0;p.write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'startup fault'):review(root)


if __name__=='__main__':unittest.main()
