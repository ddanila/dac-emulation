import json,os,shutil,tempfile,unittest
from pathlib import Path
from native_teardown_trace import review
HERE=Path(__file__).resolve().parent
class TraceReview(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'report'
        shutil.copytree(Path(os.environ.get('TEARDOWN_REPORT',HERE/'reports/native-teardown-trace')),self.root)
    def tearDown(self):self.tmp.cleanup()
    def test_complete(self):self.assertEqual(review(self.root),json.loads((self.root/'assessment.json').read_text()))
    def test_missing_destructor(self):
        p=self.root/'enabled.stdout';lines=p.read_text().splitlines();index=next(i for i,l in enumerate(lines) if l.startswith('TEARDOWN_PARAMETER Binary'));del lines[index];p.write_text('\n'.join(lines)+'\n')
        with self.assertRaisesRegex(ValueError,'destruction'):review(self.root)
    def test_parameter_not_drained(self):
        p=self.root/'enabled.stdout';p.write_text(p.read_text().replace('TEARDOWN_PARAMETER_REMAIN 0','TEARDOWN_PARAMETER_REMAIN 1'))
        with self.assertRaisesRegex(ValueError,'drained'):review(self.root)
    def test_memory_not_drained(self):
        p=self.root/'enabled.stdout';lines=p.read_text().splitlines();index=next(i for i,l in enumerate(lines) if l.startswith('TEARDOWN_MEMORY') and l.endswith(' 0'));lines[index]=lines[index][:-1]+'1';p.write_text('\n'.join(lines)+'\n')
        with self.assertRaisesRegex(ValueError,'memory destruction'):review(self.root)
    def test_missing_native_roots(self):
        p=self.root/'enabled.stdout';p.write_text(p.read_text().replace('TEARDOWN_REGISTRIES after 0','TEARDOWN_REGISTRIES after 2'))
        with self.assertRaisesRegex(ValueError,'roots'):review(self.root)
if __name__=='__main__':unittest.main()
