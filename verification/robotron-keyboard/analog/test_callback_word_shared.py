import json
import shutil
import tempfile
import unittest
from pathlib import Path
from callback_word_shared import HERE, review
from retained_evidence import check

ROOT = HERE / 'reports/callback-word-shared'


class CallbackWordSharedControls(unittest.TestCase):
    def test_retained_native_controls(self):
        check(ROOT)
        self.assertEqual(review(ROOT), json.loads((ROOT / 'assessment.json').read_text()))

    def test_adapter_changes_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'report'; shutil.copytree(ROOT, root)
            p = root / 'probe.vvp'; p.write_text(p.read_text() + '# unrecorded edit\n')
            with self.assertRaisesRegex(ValueError, 'adapter'):
                review(root)

    def test_shared_driver_mapping_is_required(self):
        self.tamper('enabled', lambda s: s.replace('WORD_SOURCE aliases 1 ', 'WORD_SOURCE aliases 2 ', 1))

    def tamper(self, mode, change):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'report'
            shutil.copytree(ROOT, root)
            p = root / (mode + '.stdout')
            old = p.read_text(); new = change(old)
            self.assertNotEqual(old, new)
            p.write_text(new)
            with self.assertRaises(ValueError):
                review(root)

    def test_vpi_base_pointer_cannot_replace_native_array(self):
        def change(s):
            lines = s.splitlines()
            i = next(i for i, line in enumerate(lines) if line.startswith('WORD_ARRAY words '))
            fields = lines[i].split(); fields[2] = hex(int(fields[2], 16) + 16)
            lines[i] = ' '.join(fields)
            return '\n'.join(lines) + '\n'
        self.tamper('enabled', change)

    def test_word_owner_binding_is_required(self):
        self.tamper('enabled', lambda s: s.replace('WORD_SOURCE words 0 ', 'WORD_SOURCE words 1 ', 1))

    def test_word_index_fault_is_not_ignored(self):
        def change(s):
            before, tail = s.split('WORD_FAULT 1 0 0\n', 1)
            lines = tail.splitlines()
            i = next(i for i, line in enumerate(lines) if line.startswith('VCL_WORD 1 '))
            fields = lines[i].split(); fields[-1] = str(int(fields[-1]) ^ 1)
            lines[i] = ' '.join(fields)
            return before + 'WORD_FAULT 1 0 0\n' + '\n'.join(lines) + '\n'
        self.tamper('corrupt', change)

    def test_invalid_link_must_refuse(self):
        self.tamper('corrupt', lambda s: s.replace('WORD_FAULT 1 2 -1', 'WORD_FAULT 1 2 0', 1))

    def test_fault_restoration_is_required(self):
        self.tamper('corrupt', lambda s: s.replace('WORD_RESTORED\n', '', 1))

    def test_dynamic_selection_is_independent_expectation(self):
        self.tamper('baseline', lambda s: s.replace('VALUE 3000 1100 0011', 'VALUE 3000 0011 0011', 1))

    def test_xz_continuation_is_preserved(self):
        self.tamper('enabled', lambda s: s.replace('VALUE 7000 10xz 10xz', 'VALUE 7000 1000 1000', 1))


if __name__ == '__main__':
    unittest.main()
