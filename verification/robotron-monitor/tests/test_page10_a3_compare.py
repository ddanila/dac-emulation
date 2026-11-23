import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page10_a3_compare


class Page10A3CompareTests(unittest.TestCase):
    def test_saved_comparison_and_compensation_swap(self):
        source = json.loads(page10_a3_compare.SOURCE.read_text())
        with tempfile.TemporaryDirectory() as directory:
            xml = Path(directory) / 'vertical-output.xml'
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                            'kicadxml', '-o', str(xml), str(page10_a3_compare.SHEET)],
                           check=True, capture_output=True, text=True)
            saved = page10_a3_compare.compare(source, xml)
            self.assertTrue(saved['passed'])
            self.assertEqual(saved['source_pins'], 15)

            changed = copy.deepcopy(source)
            changed['nets']['COMP_A'].remove('R54:2')
            changed['nets']['COMP_SERIES'].remove('R54:1')
            changed['nets']['COMP_A'].append('R54:1')
            changed['nets']['COMP_SERIES'].append('R54:2')
            result = page10_a3_compare.compare(changed, xml)
            self.assertFalse(result['passed'])
            self.assertEqual({row['pin'] for row in result['missing_or_changed_pins']
                              if row['source_id'] == '012-6931:R54'}, {'1', '2'})


if __name__ == '__main__':
    unittest.main()
