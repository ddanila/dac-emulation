import shutil,tempfile,unittest
from pathlib import Path
from display_association_probe import HERE,bundle,review
ROOT=HERE/'reports/display-association'


class DisplayAssociationTests(unittest.TestCase):
    def test_real_callback_pointer_swaps_rejected_despite_equal_payloads(self):
        result=review(ROOT)
        self.assertFalse(result['qualified'])
        self.assertTrue(result['payloadValuesUnchangedDuringRejectedSwap'])
        self.assertEqual(result['payloadPointerSwapsRejectedAndRestored'],3)

    def test_missing_and_aliased_associations_rejected(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines();start=lines.index('VA_BEGIN');end=lines.index('VA_END',start)
        original=lines[start:end+1];bundle(original)
        with self.assertRaises(ValueError):bundle([l for l in original if l!='VJ_LINK 2 2'])
        with self.assertRaises(ValueError):bundle([l.replace('VJ_LINK 2 2','VJ_LINK 2 1') for l in original])
        with self.assertRaises(ValueError):bundle([l.replace('VJ_LINK 2 2','VJ_LINK 3 2') for l in original])

    def test_wrong_links_continuation_and_false_negative_control_rejected(self):
        cases=[('enabled.stdout','VJ_LINK 1 1','VJ_LINK 1 2'),
               ('corrupt.stdout','rejected=1','rejected=0'),
               ('corrupt.stdout','restored=1','restored=0'),
               ('rebuilt.stdout','FIRST 2.00 ns b0','FIRST 2.00 ns d0'),
               ('disabled.stdout','VA_API 1','VA_API 0')]
        for name,before,after in cases:
            with self.subTest(change=before),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)
                for p in ROOT.iterdir():
                    if p.is_file():shutil.copyfile(p,out/p.name)
                p=out/name;s=p.read_text();self.assertIn(before,s);p.write_text(s.replace(before,after))
                with self.assertRaises(ValueError):review(out)


if __name__=='__main__':unittest.main()
