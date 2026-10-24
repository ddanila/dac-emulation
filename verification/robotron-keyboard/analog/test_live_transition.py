import unittest
from live_transition_probe import reduce_matrix,initial_environment
from live_transition_review import audit_stats,diagnostic
class LiveTransitionTests(unittest.TestCase):
 def test_inherited_fault_and_future_diagnostics_cannot_leak_into_control(self):
  inherited={'PATH':'/tools','SPICE_SCRIPTS':'/models','ROBOTRON_FORCE_NEWTON_REJECT':'1',
             'ROBOTRON_ROLLBACK_AUDIT':'1','ROBOTRON_EVAL_CACHE':'on','ROBOTRON_FUTURE_OPTION':'1'}
  self.assertEqual(initial_environment(inherited),{'PATH':'/tools','SPICE_SCRIPTS':'/models','ROBOTRON_EVAL_CACHE':'off'})
  self.assertEqual(inherited['ROBOTRON_FORCE_NEWTON_REJECT'],'1')
 def test_reduction_keeps_live_bus_feedback_and_supply(self):
  before='title\nVhost supply 0 5\nR1_2 0 sense 910\nScontact0 col row key 0 CONTACT\nR10.1 supply clock 560\nC3.1 supply 0 47u\nAbus [D0] [di] adc\nAhdl [di] [do] cpu\nBbus_high_0 supply D0 I=V(do)\nSdata output 0 do 0 SW\n'
  after=reduce_matrix(before)
  for l in before.splitlines()[4:]:self.assertIn(l,after)
  self.assertNotIn('Scontact0',after);self.assertIn('Vmatrix_boundary7',after)
 def test_numeric_audit_does_not_hide_real_errors(self):
  audit='TRUNC_AUDIT error time=0x1p-10 state=2 difference=-0x1p-30'
  self.assertIsNone(diagnostic(audit))
  self.assertIsNotNone(diagnostic(audit+'\nError: real failure'))
  self.assertIsNotNone(diagnostic(audit+' Error: interleaved failure'))
 def test_lte_rejection_is_not_newton_failure(self):
  log='TRUNC_AUDIT solver time=0x1p-10 result=0\nTRUNC_AUDIT device type=Inductor\nTRUNC_AUDIT step time=0x1p-10 delta=0x1p-20 proposed=0x1p-30\n'
  r=audit_stats(log);self.assertTrue(r['allAuditedNewtonSolvesConverged']);self.assertEqual(r['lastRejection']['lastLimitingDevice'],'Inductor')
  self.assertFalse(audit_stats(log.replace('result=0','result=1'))['allAuditedNewtonSolvesConverged'])
  with self.assertRaises(ValueError):audit_stats('incomplete')
if __name__=='__main__':unittest.main()
