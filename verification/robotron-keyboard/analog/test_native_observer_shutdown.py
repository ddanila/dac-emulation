import json,os,shutil,tempfile,unittest
from pathlib import Path
from native_observer_shutdown_review import review
HERE=Path(__file__).resolve().parent
class ShutdownGuard(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'report'
        shutil.copytree(Path(os.environ.get('SHUTDOWN_REPORT',HERE/'reports/native-observer-shutdown')),self.root)
    def tearDown(self):self.tmp.cleanup()
    def test_complete(self):self.assertEqual(review(self.root),json.loads((self.root/'assessment.json').read_text()))
    def test_post_acceptance(self):
        p=self.root/'after/robotron_vvp_net_inventory.stdout';p.write_text(p.read_text().replace('SWEEP_RESULT post -1 0','SWEEP_RESULT post 0 0'))
        with self.assertRaisesRegex(ValueError,'Unsafe'):review(self.root)
    def test_sanitizer_failure(self):
        (self.root/'after/robotron_vvp_net_inventory.stderr').write_text('ERROR: AddressSanitizer: heap-use-after-free\n')
        with self.assertRaisesRegex(ValueError,'Unsafe'):review(self.root)
    def test_missing_process(self):
        p=self.root/'after/run.json';r=json.loads(p.read_text());del r['runs']['robotron_vvp_thread_inventory'];p.write_text(json.dumps(r))
        with self.assertRaisesRegex(ValueError,'Missing sweep'):review(self.root)
    def test_changed_guard_source(self):
        p=self.root/'after-source/vvp/lib_main.cc';p.write_text(p.read_text().replace('robotron_observation_active=false','robotron_observation_active=true'))
        with self.assertRaisesRegex(ValueError,'Changed guard source'):review(self.root)
if __name__=='__main__':unittest.main()
