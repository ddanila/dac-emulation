import unittest
from bus_device_review import assess,classify_input
class DeviceAdmissionTests(unittest.TestCase):
 def test_absolute_rating_cannot_replace_operating_range(self):
  r=classify_input(5.000002,5,True)
  self.assertTrue(r['logicThresholdPassed']);self.assertTrue(r['withinAbsoluteInputRatings'])
  self.assertFalse(r['staticInputRangePassed']);self.assertFalse(r['transientAllowanceEstablished'])
  self.assertFalse(classify_input(7.1,5,True)['withinAbsoluteInputRatings'])
 def test_supply_and_logic_are_independent(self):
  self.assertFalse(classify_input(4.5,4.5,True)['ratedSupplyPassed'])
  self.assertFalse(classify_input(1.5,5,True)['logicThresholdPassed'])
  self.assertTrue(classify_input(1.5,5,True)['staticInputRangePassed'])
 def test_nonfinite_rejected(self):
  with self.assertRaises(ValueError):classify_input(float('nan'),5,True)
 def test_nominal_endpoint_does_not_admit_supply_envelope(self):
  r=assess();self.assertFalse(r['qualified'])
  for d in r['drivers']:
   self.assertTrue(d['points'][1]['endpointPassed'])
   self.assertFalse(d['fullSupplyEndpointEnvelopePassed']);self.assertFalse(d['admitted'])
   self.assertGreater(d['points'][0]['highDeficitVolts'],.2)
if __name__=='__main__':unittest.main()
