#!/usr/bin/env python3
import unittest
import hashlib,json
from pathlib import Path
from fixture_crossing_grid import add_crossings
from network_trace import observe_network
from network_refinement_review import normalized,events
BASE='''Vfixture_clock fixture_clock 0 PULSE(0 5 500n 1n 1n 499n 1u)
Vfixture_reset fixture_reset 0 PWL(0 0 1000000n 0 1000001n 5)
.model clock_receiver adc_bridge(in_low=1.4 in_high=1.4)
Rtest a 0 10
.options reltol=1e-6 vntol=1e-9 abstol=1e-15
.save v(n_D1)
.control
.tran 25n 1160000n
wrdata witness.txt v(n_D1)
.endc
'''
class NetworkRefinementTest(unittest.TestCase):
 def test_retained_evidence_and_qualification_boundary(self):
  root=Path(__file__).resolve().parent/'reports/inductor-chain'
  for name,digest in json.loads((root/'manifest.json').read_text()).items():
   self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),digest,name)
  result=json.loads((root/'network-refinement.json').read_text())
  self.assertTrue(result['completed'])
  self.assertFalse(result['qualified'])
  self.assertAlmostEqual(result['endSeconds'],.00116,places=17)
  self.assertTrue(result['firmwareDataMatches'])
  self.assertTrue(result['firmwareLatchesMatch'])
  self.assertLessEqual(result['maximumFirmwareEdgeDifferencePs'],1)
  self.assertGreater(result['signals']['v(n_TA_DATEN)']['maximumAbsoluteDifference'],4)
  for label,directory in (('coarse','network-full25'),('fine','network-full12')):
   for name,digest in result['artifacts'][label].items():
    path=root/directory/name
    if not path.exists():path=path.with_name(path.name+'.xz')
    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)
 def test_normalization_preserves_physical_differences(self):
  coarse=add_crossings(BASE,1)
  fine=add_crossings(BASE.replace('25n','12.5n').replace('1e-6','5e-7').replace('1e-9','5e-10').replace('1e-15','5e-16'),.5)
  self.assertEqual(normalized(coarse),normalized(fine))
  self.assertNotEqual(normalized(coarse),normalized(fine.replace('Rtest a 0 10','Rtest a 0 11')))
 def test_observations_leave_components_and_analysis_unchanged(self):
  observed=observe_network(BASE)
  original=[s for s in BASE.splitlines() if not s.startswith('.save')]
  actual=[s for s in observed.splitlines() if not s.startswith(('.save','wrdata network_witness'))]
  self.assertEqual(original,actual)
 def test_picosecond_event_alignment_and_unknowns(self):
  log='BUS_EDGE_PS 4123\nBUS_SAMPLE 4000 0000 af 0 1 0\nBUS_LATCH 4000 af af\n'
  self.assertEqual(events(log)['edgeTimesPs'],[4123])
  self.assertTrue(events(log)['latchesMatch'])
  self.assertFalse(events(log.replace('af af','xx xx'))['latchesMatch'])
  with self.assertRaises(ValueError):events(log.replace('BUS_EDGE_PS 4123\n',''))
if __name__=='__main__':unittest.main()
