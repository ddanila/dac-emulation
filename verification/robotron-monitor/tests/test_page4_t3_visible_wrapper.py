"""Verify the scoped source-visible T3 wrapper and its conductor checks."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page4_t3_visible_wrapper as wrapper


class Page4T3VisibleWrapperTests(unittest.TestCase):
    def test_saved_export_and_reversed_upper_conductor(self):
        pdf = ROOT.parents[1] / 'build/monitor/phase-a/sources/older.pdf'
        saved = json.loads(wrapper.OUTPUT.read_text())
        self.assertEqual(wrapper.CANDIDATE_SHEET.read_text(), wrapper.candidate_sheet())
        self.assertEqual(wrapper.run(pdf), saved)
        self.assertTrue(saved['passed'])

        with tempfile.TemporaryDirectory() as directory:
            sheet = Path(directory) / 'page4-candidate.kicad_sch'
            xml = Path(directory) / 'page4-candidate.xml'
            original_xml = Path(directory) / 'page4-original.xml'
            candidate = wrapper.candidate_sheet()
            candidate = wrapper.replace_once(
                candidate, '(label "h_upper2" (at 135 490.64 0)',
                '(label "wrong_upper_return" (at 135 490.64 0)')
            sheet.write_text(candidate)
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                            'kicadxml', '-o', str(xml), str(sheet)],
                           check=True, capture_output=True, text=True)
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                            'kicadxml', '-o', str(original_xml), str(wrapper.SHEET)],
                           check=True, capture_output=True, text=True)
            source = json.loads(wrapper.SOURCE.read_text())
            graph = json.loads(wrapper.GRAPH.read_text())
            changed = wrapper.compare(xml, original_xml, source, graph, sheet)
            self.assertFalse(changed['passed'])
            self.assertFalse(changed['checks']['x1_2_to_x2_3'])


if __name__ == '__main__':
    unittest.main()
