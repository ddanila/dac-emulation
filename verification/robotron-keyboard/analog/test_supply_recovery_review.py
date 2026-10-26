import unittest
import json
from pathlib import Path
from supply_recovery_review import observe, assess


def row(t,v,r):return [t,v,r,r,0,0,0,0]


class RecoveryTests(unittest.TestCase):
    def test_retained_complete_traces_and_assessment(self):
        here=Path(__file__).resolve().parent
        result=assess(here/'reports/reset-brownout')
        self.assertEqual(result,json.loads((here/'reports/supply-recovery-screen/assessment.json').read_text()))
        self.assertTrue(result['allClosedRecoveriesLackSampledAssertion'])
        self.assertTrue(result['allIsolatedRecoveriesRemainSampledLow'])
        self.assertFalse(result['qualified'])

    def test_reset_below_rated_supply_cannot_establish_recovery(self):
        result=observe([row(0,0,0),row(1,5,0),row(2,5,5),row(3,2,0),row(4,5,5),row(5,5,5)],5)
        self.assertTrue(result['validSupplyEpochs'][0]['sampledLowThenHigh'])
        self.assertFalse(result['validSupplyEpochs'][1]['sampledLowThenHigh'])
        self.assertEqual(result['recoveryEpochsWithSampledResetSequence'],0)

    def test_assertion_must_precede_release_in_same_valid_supply_epoch(self):
        values=[row(0,0,0),row(1,5,5),row(2,2,0),row(3,5,0),row(4,5,5)]
        self.assertEqual(observe(values,4)['recoveryEpochsWithSampledResetSequence'],1)
        for r in (0,1.5,6):
            changed=values[:-1]+[row(4,5,r)]
            self.assertEqual(observe(changed,4)['recoveryEpochsWithSampledResetSequence'],0)
        self.assertEqual(observe(values[:-1]+[row(4,2,5),row(5,5,5)],5)['recoveryEpochsWithSampledResetSequence'],0)

    def test_missing_endpoint_order_and_nonfinite_samples_fail(self):
        good=[row(0,0,0),row(1,5,5)]
        for bad in (good[1:],good+[row(.5,5,5)],good+[row(2,float('nan'),5)]):
            with self.assertRaises(ValueError):observe(bad,2)
        with self.assertRaises(ValueError):observe(good,2)


if __name__=='__main__':unittest.main()
