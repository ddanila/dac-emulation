import json
import shutil
import tempfile
import unittest
from pathlib import Path
from callback_delta_families import HERE, review
from retained_evidence import check

ROOT = HERE / 'reports/callback-delta-families'


class CallbackDeltaFamilyControls(unittest.TestCase):
    def test_retained_native_controls(self):
        check(ROOT)
        self.assertEqual(review(ROOT), json.loads((ROOT / 'assessment.json').read_text()))

    def tamper(self, name, change):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'report'
            shutil.copytree(ROOT, root)
            path = root / (name + '.stdout')
            old = path.read_text()
            new = change(old)
            self.assertNotEqual(old, new)
            path.write_text(new)
            with self.assertRaises(ValueError):
                review(root)

    def test_late_registration_must_revoke_admission(self):
        self.tamper('part-late-observe', lambda s: s.replace('FAM_STAGE 1 -1', 'FAM_STAGE 1 0', 1))

    def test_cancellation_is_not_native_deletion(self):
        self.tamper('word-early-observe', lambda s: s.replace('FAM_STAGE 6 -1', 'FAM_STAGE 6 0', 1))

    def test_refusal_cannot_emit_partial_state(self):
        self.tamper('array-part-early-observe', lambda s: s.replace('FAM_REFUSED_EMPTY', 'VCL_BEGIN 1 1000', 1))

    def test_compact_refusal_cannot_be_omitted(self):
        self.tamper('owner-late-observe', lambda s: s.replace('VLD_REFUSED_EMPTY\n', '', 1))

    def test_unknown_empty_owner_must_refuse(self):
        self.tamper('owner-early-observe', lambda s: s.replace('FAM_STAGE 0 -1', 'FAM_STAGE 0 0', 1))

    def test_part_history_uses_full_parent_value(self):
        self.tamper('part-early-observe', lambda s: s.replace('VALUE 4000 F 3 0 -1', 'VALUE 4000 F 1 0 -1', 1))

    def test_whole_array_word_index_is_significant(self):
        self.tamper('array-early-observe', lambda s: s.replace('VALUE 4000 F 2 0 1', 'VALUE 4000 F 2 0 0', 1))

    def test_original_subclass_behavior_is_required(self):
        self.tamper('owner-late-original', lambda s: s.replace('PRIVATE_VALUE 0', 'PRIVATE_VALUE 1', 1))

    def test_known_callback_must_survive(self):
        self.tamper('array-late-observe', lambda s: s.replace('VALUE 8000 K 5 0 -1\n', '', 1))


if __name__ == '__main__':
    unittest.main()
