import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import device_model_coverage


class DeviceModelCoverageTests(unittest.TestCase):
    def test_all_frame_path_device_instances_are_accounted_for(self):
        report = device_model_coverage.run()
        saved = json.loads((ROOT/'reference/k7222-11/device-model-coverage.json').read_text())
        self.assertEqual(report, saved)
        self.assertEqual(report['inventory_device_instances'], 77)
        self.assertEqual(report['frame_path_device_instances'],
                         report['assembled_instances']+len(report['absent_from_assembly']))
        self.assertEqual(report['assembled_instances'],
                         report['registered_instances']+len(report['unregistered_assembled']))
        self.assertEqual(len({row['id'] for row in report['devices']}),
                         report['frame_path_device_instances'])


if __name__ == '__main__':
    unittest.main()
