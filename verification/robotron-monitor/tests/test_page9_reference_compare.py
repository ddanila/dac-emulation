import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page9_reference_compare


class Page9ReferenceCompareTests(unittest.TestCase):
    def test_saved_result_matches_fresh_kicad_export(self):
        source = json.loads(page9_reference_compare.SOURCE.read_text())
        saved = json.loads((ROOT/'reference/k7222-11/page9-reference-comparison.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            xml = Path(directory)/'regulator5.xml'
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                            'kicadxml', '-o', str(xml), str(page9_reference_compare.SHEET)],
                           check=True, capture_output=True, text=True)
            self.assertEqual(page9_reference_compare.compare(source, xml), saved)
            changed = copy.deepcopy(source)
            changed['nets']['V4_COLLECTOR'].remove('R11:2')
            changed['nets']['12P_FUSED'].append('R11:2')
            result = page9_reference_compare.compare(changed, xml)
            self.assertFalse(result['passed'])
            self.assertEqual(result['missing_or_changed_pins'][0]['source_id'],
                             '012-6931:R11')


if __name__ == '__main__':
    unittest.main()
