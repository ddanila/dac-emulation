"""Independent failure fixtures for external package-model import screening."""
import unittest
from ls00_ibis_audit import inspect


def fixture():
    lines = ['[Component] synthetic', '[Pin] signal_name model_name']
    for pin in range(1, 15):
        kind = 'sink' if pin in (3, 6, 8, 11) else 'GND' if pin == 7 else 'POWER' if pin == 14 else 'sense'
        lines.append(f'{pin} pin{pin} {kind}')
    return '\n'.join(lines + ['[Model] sense', 'Model_type Input', '[Model] sink', 'Model_type Output', '[End]'])


class AuditTests(unittest.TestCase):
    def test_valid_map_does_not_claim_device_qualification(self):
        result = inspect(fixture())
        self.assertTrue(result['pinAssignmentPassed'])
        self.assertFalse(result['qualified'])

    def test_swapped_input_and_output_roles_are_rejected(self):
        result = inspect(fixture().replace('2 pin2 sense', '2 pin2 sink').replace('3 pin3 sink', '3 pin3 sense'))
        self.assertEqual([e['pin'] for e in result['components']['synthetic']['errors']], [2, 3])

    def test_missing_unknown_and_supply_roles_are_rejected(self):
        for change in [lambda s: s.replace('1 pin1 sense\n', ''),
                       lambda s: s.replace('1 pin1 sense', '1 pin1 unknown'),
                       lambda s: s.replace('7 pin7 GND', '7 pin7 POWER')]:
            self.assertFalse(inspect(change(fixture()))['pinAssignmentPassed'])

    def test_duplicate_and_incomplete_model_definitions_fail(self):
        for text in [fixture().replace('2 pin2 sense', '1 pin2 sense'),
                     fixture().replace('Model_type Output', ''),
                     fixture() + '\n[Component] synthetic']:
            with self.assertRaises(ValueError):
                inspect(text)


if __name__ == '__main__':
    unittest.main()
