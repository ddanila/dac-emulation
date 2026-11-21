"""The saved MAA723 corner result must follow the live internal models."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import maa723_internal_corner_screen as screen


class MAA723InternalCornerTests(unittest.TestCase):
    def test_saved_screen_and_pass_device_dependency(self):
        saved = json.loads((ROOT/'reference/k7222-11/maa723-internal-corner-screen.json').read_text())
        self.assertEqual(saved, screen.run())
        self.assertEqual(saved['cases'], 9)
        self.assertEqual(saved['failed_cases'], 4)
        for row in saved['rows'][1:]:
            self.assertEqual(row['all_proxy_checks_pass'], row['groups']['M723_PASS'] == 'high')
            for result in row['temperatures']:
                if not row['all_proxy_checks_pass']:
                    self.assertEqual([key for key, passed in result['checks'].items() if not passed],
                                     ['output_150ma'])


if __name__ == '__main__':
    unittest.main()
