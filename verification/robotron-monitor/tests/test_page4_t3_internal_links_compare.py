"""Check the two source-visible page-4 T3 conductor links."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import page4_t3_internal_links_compare as check


class Page4T3InternalLinksTests(unittest.TestCase):
    def test_source_links_match_and_exchanged_pin_fails(self):
        pdf = ROOT.parents[1] / 'build/monitor/phase-a/sources/older.pdf'
        report = check.run(pdf, check.VIEW)
        saved = report
        self.assertTrue(report['passed'])

        with tempfile.TemporaryDirectory() as directory:
            xml = Path(directory) / 'output.xml'
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                            'kicadxml', '-o', str(xml), str(check.SHEET)],
                           check=True, capture_output=True)
            pins = check.booster.exported_pins(xml)
            transcription = json.loads(check.TRANSCRIPTION.read_text())
            source = json.loads(check.SOURCE.read_text())
            wrong = copy.deepcopy(pins)
            pin = str(transcription['ports'].index('X1_15') + 1)
            wrong['T3'][pin] = 'h_lower13'
            changed = check.compare(source, transcription, wrong)
            self.assertFalse(changed['passed'])
            self.assertFalse(changed['checks']['X2_10_to_X1_15'])
            self.assertTrue(changed['checks']['X2_11_to_X1_13'])

            wrong = copy.deepcopy(pins)
            pin = str(transcription['ports'].index('X1_13') + 1)
            wrong['T3'][pin] = 'h_boost'
            changed = check.compare(source, transcription, wrong)
            self.assertFalse(changed['passed'])
            self.assertTrue(changed['checks']['X2_10_to_X1_15'])
            self.assertFalse(changed['checks']['X2_11_to_X1_13'])


if __name__ == '__main__':
    unittest.main()
