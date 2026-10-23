#!/usr/bin/env python3
"""Replay the captured conservation defect and distinguish it from inductor rounding."""
import hashlib,json,lzma,unittest
from pathlib import Path
from inductor_chain_review import assess
ROOT=Path(__file__).parent/'reports/inductor-chain'
class InductorChainTest(unittest.TestCase):
 def test_frozen_chain(self):
  data=(ROOT/'frozen-system.log.xz').read_bytes();expected=json.loads((ROOT/'assessment.json').read_text())
  self.assertEqual(expected.pop('logSha256'),hashlib.sha256(data).hexdigest())
  actual=assess(lzma.decompress(data).decode());self.assertEqual(actual,expected)
  balance=actual['cableBalance'];self.assertEqual(balance['originalRhsSum'],2**-22);self.assertEqual(balance['pairedRhsSum'],0)
  self.assertEqual(set(balance['nonzeroColumnSums'].values()),{-1})
  self.assertLess(balance['pairedPrecisionAgreement'],1e-50)
  row=next(r for r in actual['inductors'] if r['name']=='l1.1')
  original=abs(row['replayedCurrent']-row['historyCurrent'])
  fixed=abs(row['pairedCorrectedCurrent']-row['historyCurrent'])
  self.assertGreater(original,1e-8);self.assertLess(fixed,original/10000)
  self.assertLess(abs(row['correctedCurrent']-row['replayedCurrent']),original/10000)
  self.assertFalse(actual['qualified'])
if __name__=='__main__':unittest.main()
