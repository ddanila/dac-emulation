import copy
import shutil
import tempfile
import unittest
from pathlib import Path
import scope_probe as probe

ROOT = Path(__file__).resolve().parent / 'reports/scope-membership'


class ScopeControls(unittest.TestCase):
    def first(self):
        lines = (ROOT / 'enabled.stdout').read_text().splitlines()
        start = lines.index('VTM_BEFORE') + 1
        end = next(i for i in range(start, len(lines)) if lines[i].startswith('VSC_END '))
        return probe.parse_snapshot(lines[start:end + 1])

    def test_replay(self):
        result = probe.review(ROOT)
        self.assertTrue(result['scopeMembershipControlsPassed'])
        self.assertTrue(result['automaticScopeRefusalPassed'])

    def test_missing_or_wrong_membership(self):
        before = self.first()
        probe.validate(before)
        changed = copy.deepcopy(before)
        scope = next(s for s in changed['scopes'] if s['members'])
        scope['members'][0] = 999999
        with self.assertRaises(ValueError):
            probe.validate(changed)
        changed = copy.deepcopy(before)
        next(s for s in changed['scopes'] if s['members'])['members'].pop(0)
        probe.changed_snapshot(before, changed)
        changed['scopes'][0]['kind'] += 1
        with self.assertRaises(ValueError):
            probe.changed_snapshot(before, changed)

    def test_missing_restore_and_false_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for p in ROOT.iterdir():
                if p.suffix in ('.stdout', '.stderr') or p.name in ('probe.vvp', 'run.json'):
                    shutil.copy2(p, root / p.name)
            p = root / 'corrupt.stdout'
            original = p.read_text()
            start = original.index('VTM_CHANGED 12\n')
            a = original.index('VTM_RESTORED\n', start)
            b = original.index('VTM_FAULT 12', a)
            p.write_text(original[:a] + original[b:])
            with self.assertRaises(ValueError):
                probe.review(root)
            p.write_text(original)
            (root / 'unsupported-enabled.stdout').write_text('VTM_API 0 1\nVTM_DONE 0\n')
            with self.assertRaises(ValueError):
                probe.review(root)


if __name__ == '__main__':
    unittest.main()
