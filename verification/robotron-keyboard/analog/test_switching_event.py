#!/usr/bin/env python3
"""Guard evidence integrity and keep short timing controls out of qualification."""
import hashlib,json,unittest
from pathlib import Path
ROOT=Path(__file__).parent/'reports/switching-events'
class SwitchingEventTest(unittest.TestCase):
 def test_artifacts(self):
  for name,digest in json.loads((ROOT/'manifest.json').read_text()).items():
   self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest,name)
 def test_scope_and_findings(self):
  r=json.loads((ROOT/'assessment.json').read_text())
  self.assertFalse(r['qualified'])
  self.assertLessEqual(r['maximumEdgeDifferencePs'],1)
  for key in ('firstRejection','terminalCollapse'):
   self.assertLess(r[key]['maximumAssemblySolutionChange'],1e-12)
   self.assertLess(r[key]['correctedPrecisionAgreement'],1e-50)
  for name in ('live-reset-crossings25','live-gear25'):
   self.assertIn('sdata',r['controls'][name]['solverDiagnostic'])
  tight=r['controls']['live-gear12']
  self.assertTrue(tight['timedOut'] or tight['solverDiagnostic'])
 def test_observation_preserves_disabled_waveform(self):
  hashes=[json.loads((ROOT/n/'trace.json').read_text())['sha256'] for n in ('live-cap-capture','live-edge-disabled')]
  self.assertEqual(hashes[0],hashes[1])
if __name__=='__main__':unittest.main()
