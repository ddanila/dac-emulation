import json,os,shutil,tempfile,unittest
from pathlib import Path
from native_teardown_clear_review import review
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
class ClearReview(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'report'
        shutil.copytree(Path(os.environ.get('TEARDOWN_REPORT',HERE/'reports/native-teardown-clear')),self.root)
    def tearDown(self):self.tmp.cleanup()
    def test_complete(self):self.assertEqual(review(self.root),json.loads((self.root/'assessment.json').read_text()))
    def test_stale_registry(self):
        p=self.root/'enabled.stdout';p.write_text(p.read_text().replace('TEARDOWN_REGISTRIES after 0 0','TEARDOWN_REGISTRIES after 0 4'))
        with self.assertRaisesRegex(ValueError,'Stale'):review(self.root)
    def test_changed_source(self):
        p=self.root/'runtime/vvp/vpi_scope.cc';p.write_text(p.read_text().replace('robotron_initialized_scopes.clear();','robotron_next_object_id=0;'))
        b=self.root/'build.json';r=json.loads(b.read_text());r['outputs']['vvp/vpi_scope.cc']=sha(p);b.write_text(json.dumps(r))
        with self.assertRaisesRegex(ValueError,'Unreviewed'):review(self.root)
    def test_regression_runtime(self):
        p=self.root/'memory-regression/build.json';r=json.loads(p.read_text());r['commit']='foreign';p.write_text(json.dumps(r))
        with self.assertRaisesRegex(ValueError,'runtime mismatch'):review(self.root)
    def test_lost_postcleanup_refusal(self):
        p=self.root/'enabled.stdout';p.write_text(p.read_text().replace('POST_RESULT robotron_vvp_parameter_inventory -1 0','POST_RESULT robotron_vvp_parameter_inventory 0 0'))
        with self.assertRaisesRegex(ValueError,'refusals'):review(self.root)
if __name__=='__main__':unittest.main()
