"""Guard datasheet load direction and distinct low/high input conditions."""
import json
from pathlib import Path
import unittest
from ttl7404_probe import fixtures

class FixtureTests(unittest.TestCase):
    def test_datasheet_current_is_into_device_not_load(self):
        limits=json.loads(Path(__file__).with_name('d104_limits.json').read_text())
        cases={c['name']:c for c in fixtures(limits)}
        # VOH must source current into a load; VOL must sink externally supplied current.
        self.assertGreater(float(cases['VOH']['output'].split()[-1]),0)
        self.assertLess(float(cases['VOL']['output'].split()[-1]),0)
        self.assertEqual(cases['IIL']['inputV'],.4)
        self.assertEqual(cases['IIH']['inputV'],2.4)
        self.assertNotEqual(cases['ICCH']['input'],cases['ICCL']['input'])

if __name__=='__main__':unittest.main()
