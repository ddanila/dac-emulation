import shutil,tempfile,unittest
from pathlib import Path
from display_payload_probe import HERE,review,snapshot
ROOT=HERE/'reports/display-payload'


class DisplayPayloadTests(unittest.TestCase):
    def test_typed_payload_lifecycle_and_real_mutations(self):
        r=review(ROOT)
        self.assertFalse(r['qualified'])
        self.assertEqual(r['destinationMutationsDetectedAndRestored'],3)
        self.assertTrue(r['deferredArgumentsFollowNonblockingAssignments'])

    def test_missing_items_and_invalid_lifecycle_rejected(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines()
        start=next(i for i,l in enumerate(lines) if l.startswith('VD_BEGIN'))
        end=next(i for i,l in enumerate(lines[start:],start) if l=='VD_END')
        original=lines[start:end+1];snapshot(original)
        with self.assertRaises(ValueError):snapshot([l for l in original if not l.startswith('VD_ITEM 1 2 ')])
        bad=original[:];bad[0]='VD_BEGIN 1 1 1 1'
        with self.assertRaises(ValueError):snapshot(bad)

    def test_metadata_code_module_and_restoration_errors_rejected(self):
        cases=[('enabled.stdout','VD_FORMAT -9 2 8 0','VD_FORMAT -9 3 8 0'),
               ('enabled.stdout','VD_INFO 1 0 10 3 1 4','VD_INFO 1 0 10 4 1 4'),
               ('enabled.stdout','VD_ITEM 1 2 48','VD_ITEM 1 2 47'),
               ('corrupt.stdout','VD_FAULT 1','VD_FAULT 0'),
               ('disabled.stdout','VD_API 1','VD_API 0'),
               ('rebuilt.stdout','STROBE 2.00 ns b0','STROBE 2.00 ns a0')]
        for name,before,after in cases:
            with self.subTest(change=before),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)
                for p in ROOT.iterdir():
                    if p.is_file():shutil.copyfile(p,out/p.name)
                p=out/name;s=p.read_text();self.assertIn(before,s);p.write_text(s.replace(before,after))
                with self.assertRaises(ValueError):review(out)


if __name__=='__main__':unittest.main()
