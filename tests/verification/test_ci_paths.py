"""Exercise the keyboard workflow's ordered path selection with representative inputs."""
import fnmatch
from pathlib import Path
import unittest


class KeyboardWorkflowPaths(unittest.TestCase):
    def test_push_and_pull_request_dependencies(self):
        workflow = Path(__file__).resolve().parents[2] / '.github/workflows/keyboard-controller.yml'
        # The workflow uses literal quoted path entries, with no YAML aliases.
        blocks = workflow.read_text().split('    paths:\n')[1:]
        self.assertEqual(len(blocks), 2)
        for block in blocks:
            patterns = []
            for line in block.splitlines():
                if line and not line.startswith('      '):
                    break
                if line.strip().startswith("- '"):
                    patterns.append(line.strip()[3:-1])
            def selected(path):
                included = False
                for pattern in patterns:
                    glob = pattern.removeprefix('!')
                    if fnmatch.fnmatchcase(path, glob) or ('**/' in glob and fnmatch.fnmatchcase(path, glob.replace('**/', ''))):
                        included = not pattern.startswith('!')
                return included
            for path in ['machines/juku/keyboard.inc', 'machines/vjuga/vjuga.c',
                         'verification/robotron-keyboard/README.md']:
                self.assertFalse(selected(path), path)
            for path in ['machines/robotron1715m/keyboard_board.c',
                         'machines/robotron1715m/generated/keyboard_cpu/decode.h',
                         'common/cpu/z80.c', 'third_party/cpu/tv80/core.v',
                         'tools/generate_keyboard_cpu.py', 'Makefile',
                         'verification/robotron-keyboard/digital/run.py',
                         '.github/workflows/keyboard-controller.yml']:
                self.assertTrue(selected(path), path)
