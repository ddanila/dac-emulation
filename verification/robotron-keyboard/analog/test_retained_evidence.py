import json,tempfile,unittest
from pathlib import Path
from retained_evidence import check
from ttl7406_probe import sha

class RetainedEvidenceTests(unittest.TestCase):
    def test_nested_manifest_is_checked_and_extra_files_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);nested=root/'parts';nested.mkdir();p=nested/'manifest.json';p.write_text('{}')
            (root/'manifest.json').write_text(json.dumps({'files':{'parts/manifest.json':sha(p)},'sources':{}}))
            check(root)
            p.write_text('{"changed":true}')
            with self.assertRaises(ValueError):check(root)
            p.write_text('{}');extra=root/'unrecorded';extra.write_text('extra')
            with self.assertRaises(ValueError):check(root)
            extra.unlink();p.unlink()
            with self.assertRaises(ValueError):check(root)

if __name__=='__main__':unittest.main()
