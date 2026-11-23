"""Keep the page-18 physical pin inventory tied to fresh terminal exports."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page18_pin_coverage_audit as coverage
import page18_vertical_rail_terminals_compare as rails


class Page18PinCoverageTests(unittest.TestCase):
    def test_source_inventory_and_rail_terminal_export(self):
        source_pdf = ROOT.parents[1] / 'build/monitor/phase-a/sources/older.pdf'
        rail_report = rails.run(source_pdf)
        self.assertTrue(rail_report['passed'])
        self.assertEqual(rail_report['exported_nets'],
                         {'012-6931:X21': {'1': 'p12'},
                          '012-6931:X22': {'1': '0'}})
        audit = coverage.run()
        self.assertTrue(audit['audit_passed'])
        self.assertTrue(audit['physical_endpoint_comparison_complete'])
        self.assertEqual(audit['source_endpoint_count'], 70)
        self.assertEqual(audit['uncovered'], [])
        self.assertFalse(audit['a1_page18_complete'])


if __name__ == '__main__':
    unittest.main()
