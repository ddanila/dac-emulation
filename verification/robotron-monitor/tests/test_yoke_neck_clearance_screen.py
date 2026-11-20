import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import yoke_neck_clearance_screen as screen


class YokeNeckClearanceScreenTests(unittest.TestCase):
    def test_narrower_aperture_requires_shorter_field(self):
        profile = json.loads(screen.PROFILE.read_text())
        current_class = json.loads(screen.YOKE_CLASS.read_text())[
            'conditional_current_proxy']['line_family_envelope_app']
        long_field = screen.case(profile, .23, .025, .009, current_class)
        short_field = screen.case(profile, .23, .020, .009, current_class)
        self.assertFalse(long_field['reaches_210mm_width'])
        self.assertTrue(short_field['reaches_210mm_width'])
        self.assertFalse(short_field['inside_90_degree_current_proxy'])
        self.assertGreater(short_field['target_current_pp_a'], current_class[1])

    def test_wrong_outline_is_rejected(self):
        sources = ROOT.parents[1] / 'build/monitor/phase-a/sources'
        with tempfile.TemporaryDirectory() as directory:
            wrong = Path(directory) / 'wrong.gif'
            wrong.write_bytes(b'not the B31-G outline')
            with self.assertRaisesRegex(ValueError, 'source scan or B31-G outline'):
                screen.run(sources / 'older.pdf', wrong)


if __name__ == '__main__':
    unittest.main()
