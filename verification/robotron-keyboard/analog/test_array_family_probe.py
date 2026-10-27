import shutil
import tempfile
import unittest
from pathlib import Path
import array_family_probe as probe
ROOT=Path(__file__).resolve().parent/'reports/array-families'


class ArrayFamilies(unittest.TestCase):
    def test_retained_native_refusals(self):
        result=probe.review(ROOT)
        self.assertTrue(result['controlsPassed'])
        self.assertTrue(result['aliasStorageSharingExercised'])
        self.assertEqual(set(result['unsupportedProfilesRefused']),{'alias','net','real','string'})
    def test_missing_alias_and_partial_inventory_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for p in ROOT.iterdir():
                if p.is_file():shutil.copy2(p,root/p.name)
            original=(root/'alias.vvp').read_text()
            (root/'alias.vvp').write_text((root/'alias-original.vvp').read_text())
            with self.assertRaises(ValueError):probe.review(root)
            (root/'alias.vvp').write_text(original)
            p=root/'net-compact.stdout';p.write_text(p.read_text()+'VAC_BEGIN 1 1000\n')
            with self.assertRaises(ValueError):probe.review(root)
    def test_alias_injection_requires_unique_source(self):
        source=(ROOT/'alias-original.vvp').read_text()
        with self.assertRaises(ValueError):probe.alias_program(source+source)
        with self.assertRaises(ValueError):probe.alias_program(probe.alias_program(source))


if __name__=='__main__':unittest.main()
