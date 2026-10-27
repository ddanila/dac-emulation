import copy
import shutil
import tempfile
import unittest
from pathlib import Path
import array_probe as probe

ROOT=Path(__file__).resolve().parent/'reports/array-state'


class ArrayControls(unittest.TestCase):
    def first(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines()
        start=lines.index('VAM_BEFORE')+1
        end=next(i for i in range(start,len(lines)) if lines[i].startswith('VAR_END '))
        return probe.parse(lines[start:end+1])

    def test_retained_native_controls(self):
        result=probe.review(ROOT)
        self.assertTrue(result['controlsPassed'])
        self.assertEqual(len(result['unsupportedProfilesRefused']),3)

    def test_port_ownership_and_exact_fault(self):
        before=self.first();probe.validate(before)
        changed=copy.deepcopy(before);i=probe.target(before,2)
        self.assertIsNotNone(i)
        changed['ports'][i]['next']=0
        probe.changed(before,changed,2)
        with self.assertRaises(ValueError):probe.validate(changed)
        changed['arrays'][0]['words'][0]='0'*changed['arrays'][0]['width']
        with self.assertRaises(ValueError):probe.changed(before,changed,2)

    def test_refusal_must_include_actual_unsupported_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for p in ROOT.iterdir():
                if p.is_file():shutil.copy2(p,root/p.name)
            p=root/'two.vvp';p.write_text(p.read_text().replace('.array/2u "other"','.array "other"'))
            with self.assertRaises(ValueError):probe.review(root)


if __name__=='__main__':unittest.main()
