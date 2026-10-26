import shutil,tempfile,unittest
from pathlib import Path
from executing_wrapper_probe import HERE,bundle,review
ROOT=HERE/'reports/executing-wrapper'


class ExecutingWrapperTests(unittest.TestCase):
    def test_real_wrapper_mutations_and_all_callback_regions(self):
        r=review(ROOT)
        self.assertEqual(r['callbackReasons'],[6,7,9])
        self.assertEqual(r['deletionFlagMutationsDetectedAndRestored'],9)
        self.assertEqual(r['emptyFrameObservations'],12)
        self.assertFalse(r['qualified'])

    def test_wrong_or_missing_executing_link_rejected(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines()
        starts=[i for i,l in enumerate(lines) if l=='VX_BEGIN'];start=starts[2]
        original=lines[start:lines.index('VX_END',start)+1];bundle(original)
        frame=next(l for l in original if l.startswith('VE_FRAME '));fields=frame.split()
        wrong=fields[:];wrong[3]='9999'
        with self.assertRaises(ValueError):bundle([l.replace(frame,' '.join(wrong)) for l in original])
        with self.assertRaises(ValueError):bundle([l for l in original if l!=frame])
        with self.assertRaises(ValueError):bundle([l.replace('VE_BEGIN 1 1','VE_BEGIN 1 0') for l in original])

    def test_unrestored_flags_wrong_output_and_missing_fault_rejected(self):
        text=(ROOT/'corrupt.stdout').read_text();changed=next(l for l in text.splitlines() if l.startswith('VE_FRAME ') and l.endswith(' 1'))
        cases=[('corrupt.stdout',changed,changed[:-1]+'0'),
               ('corrupt.stdout','VX_FAULT 1','VX_FAULT 0'),
               ('baseline.stdout','CALLBACK 0 2000 6 2','CALLBACK 0 2000 7 2'),
               ('enabled.stdout','VX_API 1','VX_API 0')]
        for name,before,after in cases:
            with self.subTest(change=before),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)
                for p in ROOT.iterdir():
                    if p.is_file():shutil.copyfile(p,out/p.name)
                p=out/name;s=p.read_text();self.assertIn(before,s);p.write_text(s.replace(before,after))
                with self.assertRaises(ValueError):review(out)


if __name__=='__main__':unittest.main()
