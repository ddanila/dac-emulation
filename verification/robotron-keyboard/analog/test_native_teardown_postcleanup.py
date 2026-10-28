import json,os,shutil,tempfile,unittest
from pathlib import Path
from native_teardown_postcleanup import review
HERE=Path(__file__).resolve().parent
class PostCleanupReview(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'report'
        shutil.copytree(Path(os.environ.get('TEARDOWN_REPORT',HERE/'reports/native-teardown-postcleanup')),self.root)
    def tearDown(self):self.tmp.cleanup()
    def test_complete(self):self.assertEqual(review(self.root),json.loads((self.root/'assessment.json').read_text()))
    def test_acceptance_instead_of_refusal(self):
        p=self.root/'enabled.stdout';p.write_text(p.read_text().replace('POST_RESULT robotron_vvp_parameter_inventory -1 0','POST_RESULT robotron_vvp_parameter_inventory 0 0'))
        with self.assertRaisesRegex(ValueError,'refusals'):review(self.root)
    def test_partial_output(self):
        p=self.root/'enabled.stdout';p.write_text(p.read_text().replace('POST_RESULT robotron_vvp_array_inventory -1 0','POST_RESULT robotron_vvp_array_inventory -1 8'))
        with self.assertRaisesRegex(ValueError,'refusals'):review(self.root)
    def test_missing_return(self):
        p=self.root/'enabled.stdout';p.write_text(p.read_text().replace('POST_CLEANUP_RETURN\n',''))
        with self.assertRaisesRegex(ValueError,'refusals'):review(self.root)
    def test_failed_exit(self):
        p=self.root/'run.json';r=json.loads(p.read_text());r['runs']['enabled']['exitCode']=1;p.write_text(json.dumps(r))
        with self.assertRaisesRegex(ValueError,'Abnormal'):review(self.root)
if __name__=='__main__':unittest.main()
