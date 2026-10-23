#!/usr/bin/env python3
import hashlib,json,lzma,unittest
from pathlib import Path
from output_switch_review import review
ROOT=Path(__file__).parent/'reports/output-switch'
class OutputSwitchTest(unittest.TestCase):
 def test_replay_and_failure_attribution(self):
  expected=json.loads((ROOT/'assessment.json').read_text());data=(ROOT/'later-truncation-audit/ngspice.log.xz').read_bytes()
  self.assertEqual(expected.pop('logSha256'),hashlib.sha256(data).hexdigest())
  actual=review(lzma.decompress(data).decode());self.assertEqual(expected,actual)
  self.assertTrue(all(t['result']==0 for t in actual['trials']))
  self.assertEqual(actual['trials'][-1]['stateChanges'],0)
  late=actual['lateTruncation'];self.assertEqual(late['lastLimitingInstance']['name'],'l1.1')
  self.assertEqual(late['lastEstimator']['proposalRelativeRoundingError'],0)
  self.assertLess(late['lastEstimator']['exactHistoryProposalSeconds'],late['lastEstimator']['deltaSeconds'])
 def test_unchanged_waveforms(self):
  control=json.loads((ROOT.parent/'switching-events/live-reset-crossings25/trace.json').read_text())['sha256']
  for name in ('output-switch-audit','later-truncation-audit'):
   self.assertEqual(json.loads((ROOT/name/'trace.json').read_text())['sha256'],control)
if __name__=='__main__':unittest.main()
