import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page10_feedback_compare as checker


class Page10FeedbackTests(unittest.TestCase):
    def test_saved_feedback_read_matches_fresh_export(self):
        pdf = ROOT.parent.parent / 'build/monitor/phase-a/sources/older.pdf'
        saved = checker.run(pdf)
        self.assertTrue(saved['passed'])
        self.assertEqual(saved['matched_pins'], 18)
        self.assertEqual(len(saved['source_conflicts']), 1)

    def test_moved_r46_return_is_detected(self):
        source = json.loads(checker.SOURCE.read_text())
        source['nets']['Y2_RETURN'].remove('R46:2')
        source['nets']['AMP_INV'].append('R46:2')
        with tempfile.TemporaryDirectory() as directory:
            xml = Path(directory) / 'live.xml'
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                            'kicadxml', '-o', str(xml), str(checker.SHEET)],
                           check=True, capture_output=True)
            report = checker.compare(source, xml)
        self.assertFalse(report['passed'])
        self.assertEqual(report['missing_or_changed_pins'][0]['source_id'], '012-6931:R46')

    def test_reversed_v23_is_detected(self):
        source = json.loads(checker.SOURCE.read_text())
        source['nets']['THRESHOLD_LOWER'].remove('V23:A')
        source['nets']['THRESHOLD_LOWER'].append('V23:K')
        source['nets']['THRESHOLD_UPPER'].remove('V23:K')
        source['nets']['THRESHOLD_UPPER'].append('V23:A')
        with tempfile.TemporaryDirectory() as directory:
            xml = Path(directory) / 'live.xml'
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                            'kicadxml', '-o', str(xml), str(checker.SHEET)],
                           check=True, capture_output=True)
            report = checker.compare(source, xml)
        self.assertFalse(report['passed'])
        self.assertEqual({row['source_id'] for row in report['missing_or_changed_pins']},
                         {'012-6931:V23'})


if __name__ == '__main__':
    unittest.main()
