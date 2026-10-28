import json,os,re,shutil,tempfile,unittest
from pathlib import Path
from native_teardown_observers import review
HERE=Path(__file__).resolve().parent
class TeardownReview(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'report'
        shutil.copytree(Path(os.environ.get('TEARDOWN_REPORT',HERE/'reports/native-teardown-observers')),self.root)
    def tearDown(self):self.tmp.cleanup()
    def test_complete(self):
        self.assertEqual(review(self.root),json.loads((self.root/'assessment.json').read_text()))
    def test_missing_end_inventory(self):
        p=self.root/'enabled.stdout';p.write_text(re.sub(r'OBSERVER_BEGIN 12 robotron_vvp_parameter_inventory\n.*?OBSERVER_END\n','',p.read_text(),count=1,flags=re.S))
        with self.assertRaisesRegex(ValueError,'coverage'):review(self.root)
    def test_memory_population(self):
        p=self.root/'enabled.stdout';p.write_text(p.read_text().replace('VMM_END 2','VMM_END 1',1))
        with self.assertRaisesRegex(ValueError,'footer'):review(self.root)
    def test_sanitizer_diagnostic(self):
        (self.root/'enabled.stderr').write_text('ERROR: AddressSanitizer: heap-use-after-free\n')
        with self.assertRaisesRegex(ValueError,'Abnormal'):review(self.root)
    def test_continuation(self):
        p=self.root/'enabled.stdout';p.write_text(p.read_text().replace('CONTINUE','LOST'))
        with self.assertRaisesRegex(ValueError,'continuation'):review(self.root)
if __name__=='__main__':unittest.main()
