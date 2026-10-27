import math
import json
import unittest
from i8282_joint_constraints import HERE, assess, check_delays


class JointConstraintsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = assess(HERE / 'reports')

    def test_rejected_capacitances_cannot_be_rescued_by_zero_delay(self):
        for cap in (12., 30.):
            with self.assertRaises(ValueError):
                check_delays(self.report, 250., cap, data=0., strobe=0., disconnect=0.)

    def test_full_pin_limits_are_not_internal_delays(self):
        for key, value in [('data', 35e-9), ('strobe', 55e-9), ('disconnect', 25e-9)]:
            delays = dict(data=0., strobe=0., disconnect=0.)
            delays[key] = value
            with self.assertRaises(ValueError):
                check_delays(self.report, 125., 12., **delays)

    def test_joint_endpoints_preserve_every_retained_pin_limit(self):
        root = HERE / 'reports'
        propagation = json.loads((root / 'i8282-propagation-candidates/assessment.json').read_text())
        release = json.loads((root / 'i8282-release-candidates/assessment.json').read_text())
        for row in self.report['alternatives']:
            bounds = row['internalDelayIntervals']
            if bounds is None:
                continue
            for report, stage, fields in (
                (propagation, 'stageDelaySeconds', {'data': 35e-9, 'strobe': 55e-9}),
                (release, 'stageSeconds', {'disconnect': 25e-9}),
            ):
                for item in report['cases']:
                    case = item['case']
                    if (case['highOhms'], case['extraCapacitancePf']) != (row['highOhms'], row['extraCapacitancePf']):
                        continue
                    for key, pin_limit in fields.items():
                        self.assertLessEqual(bounds[key]['maximumSeconds'] + case[stage], pin_limit + 1e-23)

    def test_boundaries_and_refusals(self):
        for row in self.report['alternatives']:
            if not row['edgeConstraintsPassed']:
                continue
            delays = {k: b['maximumSeconds'] for k, b in row['internalDelayIntervals'].items()}
            result = check_delays(self.report, row['highOhms'], row['extraCapacitancePf'], **delays)
            self.assertFalse(result['deviceAdmitted'])
            self.assertFalse(result['enableQualified'])
            self.assertEqual(row['caseCounts'], dict(capacitance=6, propagation=6, release=18))
            for key in delays:
                for invalid in (-1e-12, math.nan, math.inf, delays[key] + 1e-12):
                    with self.assertRaises(ValueError):
                        check_delays(self.report, row['highOhms'], row['extraCapacitancePf'], **dict(delays, **{key: invalid}))
        with self.assertRaises(ValueError):
            check_delays(self.report, 125., 13., data=0., strobe=0., disconnect=0.)
        with self.assertRaises(ValueError):
            check_delays(self.report, 125., 12., data=0., strobe=0., disconnect=0., enable=0.)


if __name__ == '__main__':
    unittest.main()
