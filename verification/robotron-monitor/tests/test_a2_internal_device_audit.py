"""Keep the A2 internal-device inventory tied to the active IC equivalents."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import a2_internal_device_audit as audit


class A2InternalDeviceAuditTests(unittest.TestCase):
    def test_active_internal_devices_and_saved_report(self):
        saved = json.loads((ROOT/'reference/k7222-11/a2-internal-device-audit.json').read_text())
        live = audit.run()
        self.assertEqual(saved, live)
        rows = {row['subcircuit']: row for row in live['rows']}
        self.assertEqual(set(rows), {'MAA723_BOUND', 'P09A_EQUIV'})
        self.assertEqual({device['reference'] for device in rows['MAA723_BOUND']['devices']},
                         {'Dupper', 'Dlower', 'Qpass', 'Qlimit'})
        self.assertEqual(rows['P09A_EQUIV']['devices'], [])
        self.assertEqual(live['instances_with_critical_defaults'], 4)


if __name__ == '__main__':
    unittest.main()
