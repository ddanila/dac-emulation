import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import sf127c_vertical_check as check


class Sf127cVerticalCheckTests(unittest.TestCase):
    def test_saved_report_checks_live_vertical_v18_against_group_c(self):
        report = check.run()
        saved = report
        self.assertTrue(report['passed'])
        self.assertEqual(report['assembly_source_id'], '012-6931:V18')
        self.assertEqual(report['data_book_targets']['hFE_50ma']['range'], [56, 140])


if __name__ == '__main__':
    unittest.main()
