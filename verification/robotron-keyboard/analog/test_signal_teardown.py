import json,shutil,tempfile,unittest
from pathlib import Path
from signal_teardown_complete_review import review
HERE=Path(__file__).resolve().parent
class SignalTeardown(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'report';shutil.copytree(HERE/'reports/signal-teardown-clear',self.root)
    def tearDown(self):self.tmp.cleanup()
    def alter(self,fn):
        p=self.root/'enabled.stdout';s=p.read_text();changed=fn(s);self.assertTrue(changed!=s);p.write_text(changed)
    def test_replay(self):
        for name in ('trace','clear'):
            p=HERE/('reports/signal-teardown-'+name);self.assertEqual(review(p),json.loads((p/'assessment.json').read_text()))
    def test_missing_signal_release(self):
        self.alter(lambda s:'\n'.join(l for i,l in enumerate(s.splitlines()) if i!=next(j for j,l in enumerate(s.splitlines()) if l.startswith('TEARDOWN_SIGNAL_RELEASED ')))+'\n')
        with self.assertRaisesRegex(ValueError,'Missing native signal release'):review(self.root)
    def test_stale_registration(self):
        self.alter(lambda s:s.replace('TEARDOWN_SIGNAL_POOLS_DONE 0','TEARDOWN_SIGNAL_POOLS_DONE 1'))
        with self.assertRaisesRegex(ValueError,'registration count'):review(self.root)
    def test_open_observation(self):
        def change(s):
            lines=s.splitlines();i=next(i for i,l in enumerate(lines) if l.startswith('TEARDOWN_SIGNAL_BEGIN '));lines[i]=lines[i][:-1]+'1';return '\n'.join(lines)+'\n'
        self.alter(change)
        with self.assertRaisesRegex(ValueError,'open observation'):review(self.root)
    def test_changed_source(self):
        p=self.root/'after-source.cc';p.write_text(p.read_text()+'\n')
        with self.assertRaisesRegex(ValueError,'selected signal source'):review(self.root)
    def test_missing_refusal(self):
        self.alter(lambda s:s.replace('POST_RESULT robotron_vvp_signal_handle_inventory -1 0','POST_RESULT robotron_vvp_signal_handle_inventory 0 0'))
        with self.assertRaisesRegex(ValueError,'post-cleanup refusal'):review(self.root)
if __name__=='__main__':unittest.main()
