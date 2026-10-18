import unittest
import math
from reset_supply_observation import observe


class ResetSupplyTests(unittest.TestCase):
    def test_undervoltage_does_not_count_as_reset_assertion(self):
        rows = [[0,0,0,0,0,0,0,0], [1,2,0,0,0,0,0,0],
                [2,5,0,0,0,0,0,0], [3,5,1,1,0,0,0,0],
                [4,5,4,4,0,0,0,0], [5,5,6,6,0,0,0,0]]
        report = observe(rows, {'pointsSecondsVolts': [[0,0],[1,2],[5,5]]})
        self.assertEqual(report['segments'][0]['validSupplySamples'], 0)
        self.assertEqual(report['segments'][0]['cpuResetStatesWithinSupplyRange']['low'], 0)
        self.assertEqual(report['segments'][1]['cpuResetStatesWithinSupplyRange'],
                         {'low':1, 'high':1, 'unknown':1, 'outsideInputRange':1})

    def test_endpoint_roundoff_is_not_a_missing_step(self):
        stimulus = {'pointsSecondsVolts': [[0,0],[1.6,5]]}
        end = math.nextafter(1.6, 0)
        observe([[0]*8, [end,5,4,4,0,0,0,0]], stimulus)
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            observe([[0]*8, [1.6-1e-6,5,4,4,0,0,0,0]], stimulus)

    def test_bad_trace_fails(self):
        row = [0]*8
        for rows in [[row], [row,row], [row,[1]*7], [row,[float('nan')]*8],
                     [row,[.5]*8]]:
            with self.assertRaises(ValueError):
                observe(rows, {'pointsSecondsVolts': [[0,0],[1,5]]})


if __name__ == '__main__':
    unittest.main()
