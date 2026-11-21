import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import t3_drive_voltage_audit as audit


class T3DriveVoltageAuditTests(unittest.TestCase):
    def test_saved_audit_tracks_source_read_h2_return(self):
        saved = json.loads((ROOT / 'reference/k7222-11/t3-drive-voltage-audit.json').read_text())
        self.assertEqual(audit.run(), saved)
        self.assertEqual(saved['source_read_return_branch']['H2_EXTERNAL_RETURN'],
                         ['C31:other_plate', 'C32:other_plate', 'X5:5'])
        self.assertEqual(saved['candidate_assembly_nets']['H2/X5:5'], 'hy2')


if __name__ == '__main__':
    unittest.main()
