import json,os,shutil,tempfile,unittest
from pathlib import Path
from native_observer_shutdown_board_review import review
from native_observer_shutdown_board_shutdown import review as shutdown
from trace_io import open_text
HERE=Path(__file__).resolve().parent
class BoardTeardown(unittest.TestCase):
    def setUp(self):
        self.source=Path(os.environ.get('TEARDOWN_BOARD_REPORT',HERE/'reports/native-observer-shutdown-board'))
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'mode'
        shutil.copytree(self.source/'parameter-lifecycle-binary',self.root)
        for name in ('observer-shutdown-sites.json','icarus-build.json'):shutil.copyfile(self.source/name,self.root.parent/name)
    def tearDown(self):self.tmp.cleanup()
    def change(self,fn):
        with open_text(self.root/'ngspice.log') as stream:text=stream.read()
        changed=fn(text);self.assertNotEqual(changed,text);(self.root/'ngspice.log').write_text(changed)
    def test_full_review(self):
        self.assertEqual(json.loads(json.dumps(review(self.source))),json.loads((self.source/'assessment.json').read_text()))
    def test_missing_parameter_destructor(self):
        def change(text):
            head,tail=text.split('TEARDOWN_BEGIN\n');lines=tail.splitlines();index=next(i for i,l in enumerate(lines) if l.startswith('TEARDOWN_PARAMETER '));del lines[index];return head+'TEARDOWN_BEGIN\n'+'\n'.join(lines)+'\n'
        self.change(change)
        with self.assertRaisesRegex(ValueError,'parameter destruction'):shutdown(self.root)
    def test_stale_registrations(self):
        self.change(lambda s:s.replace('TEARDOWN_REGISTRIES after 0 0','TEARDOWN_REGISTRIES after 0 32'))
        with self.assertRaisesRegex(ValueError,'Stale'):shutdown(self.root)
    def test_missing_postcleanup_refusal(self):
        self.change(lambda s:s.replace('POST_RESULT robotron_vvp_parameter_inventory -1 0','POST_RESULT robotron_vvp_parameter_inventory 0 0'))
        with self.assertRaisesRegex(ValueError,'refusals'):shutdown(self.root)
    def test_sanitizer_error(self):
        self.change(lambda s:s+'ERROR: AddressSanitizer: heap-use-after-free\n')
        with self.assertRaisesRegex(ValueError,'Sanitizer'):shutdown(self.root)
if __name__=='__main__':unittest.main()
