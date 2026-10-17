"""Backend identity includes code models, not just an unchanged version string."""
import tempfile
import unittest
from pathlib import Path
from ngspice_runtime import identify, verify


class RuntimeTests(unittest.TestCase):
    def fixture(self, directory):
        binary = directory / 'ngspice'
        binary.write_text('#!/bin/sh\nexit 0\n')
        binary.chmod(0o755)
        model = directory / 'digital.cm'
        model.write_bytes(b'baseline model')
        spinit = directory / 'spinit'
        spinit.write_text(f'* fixture\ncodemodel "{model}"\n')
        return binary, model, spinit

    def test_code_model_and_initialization_changes_are_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            binary, model, spinit = self.fixture(Path(temporary))
            runtime, env = identify(binary, spinit)
            self.assertEqual(env['SPICE_SCRIPTS'], str(spinit.parent.resolve()))
            verify(runtime)
            for path in (binary, model, spinit):
                old = path.read_bytes()
                path.write_bytes(old + b'\nchanged')
                with self.subTest(path=path.name), self.assertRaisesRegex(ValueError, 'changed during execution'):
                    verify(runtime)
                path.write_bytes(old)

    def test_untracked_model_paths_and_nested_scripts_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            binary, model, spinit = self.fixture(Path(temporary))
            for text in ('codemodel digital.cm\n', 'codemodel $libpath/digital.cm\n',
                         f'codemodel {model}\nsource other-init\n', '* no models\n'):
                spinit.write_text(text)
                with self.subTest(text=text), self.assertRaises(ValueError):
                    identify(binary, spinit)


if __name__ == '__main__':
    unittest.main()
