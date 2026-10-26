import shutil,tempfile,unittest
from pathlib import Path
from private_sync_family_probe import HERE,review,snapshot,symbols
ROOT=HERE/'reports/private-sync-family'


class CallbackFamilyTests(unittest.TestCase):
    def test_actual_display_and_canceled_callbacks(self):
        result=review(ROOT)
        self.assertFalse(result['qualified'])
        self.assertTrue(result['displayFunctionIdentifiedByModuleOffset'])
        self.assertEqual(result['modeMutationsDetectedAndRestored'],6)

    def test_unset_fields_and_missing_code_cannot_be_admitted(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines()
        start=next(i for i,s in enumerate(lines) if s.startswith('VF_BEGIN'))
        end=next(i for i,s in enumerate(lines[start:],start) if s=='VF_END')
        original=lines[start:end+1];snapshot(original)
        for index in (8,9,10):
            bad=original[:];a=bad[1].split();self.assertEqual(a[index],'-1');a[index]='0';bad[1]=' '.join(a)
            with self.assertRaises(ValueError):snapshot(bad)
        with self.assertRaises(ValueError):snapshot([s for s in original if not s.startswith('VF_CODE 1 ')])
        with self.assertRaises(ValueError):symbols('0001 t _strobe_cb\n0002 t _strobe_cb\n')

    def test_changed_code_output_and_fault_results_rejected(self):
        text=(ROOT/'enabled.stdout').read_text();code=next(s for s in text.splitlines() if s.startswith('VF_CODE 1 '))
        a=code.split();a[-1]=format(int(a[-1],16)+1,'x')
        cases=[('enabled.stdout',code,' '.join(a)),('disabled.stdout','STROBE 2000','STROBE 2001'),
               ('corrupt.stdout','VF_FAULT 1','VF_FAULT 0'),('disabled.stdout','VF_API 1','VF_API 0')]
        for name,before,after in cases:
            with self.subTest(change=before),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)
                for p in ROOT.iterdir():
                    if p.is_file():shutil.copyfile(p,out/p.name)
                p=out/name;s=p.read_text();self.assertIn(before,s);p.write_text(s.replace(before,after,1))
                with self.assertRaises(ValueError):review(out)


if __name__=='__main__':unittest.main()
