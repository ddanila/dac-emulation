import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page9_sync_input_compare


class Page9SyncInputCompareTests(unittest.TestCase):
    def test_source_endpoints_match_fresh_kicad_export(self):
        source = json.loads(page9_sync_input_compare.SOURCE.read_text())
        saved = json.loads((ROOT/'reference/k7222-11/page9-sync-input-comparison.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            xml = Path(directory)/'sync-filter.xml'
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                            'kicadxml', '-o', str(xml),
                            str(page9_sync_input_compare.SHEET)],
                           check=True, capture_output=True, text=True)
            self.assertEqual(page9_sync_input_compare.compare(source, xml), saved)
            self.assertTrue(saved['passed'])
            self.assertEqual(saved['matched_endpoints'], 8)

            # The first image reading mistakenly joined C2 to incoming SYNC.
            wrong_crossing = copy.deepcopy(source)
            wrong_crossing['nets']['0'].remove('C2:L')
            wrong_crossing['nets']['SYNC_IN'].append('C2:L')
            changed = page9_sync_input_compare.compare(wrong_crossing, xml)
            self.assertFalse(changed['passed'])
            self.assertEqual(changed['missing_or_changed_parts'][0]['source_id'],
                             '012-6931:C2')


if __name__ == '__main__':
    unittest.main()
