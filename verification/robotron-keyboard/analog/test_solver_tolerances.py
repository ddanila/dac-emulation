import unittest
from live_transition_probe import tighten_tolerances

class ToleranceTests(unittest.TestCase):
 def test_independent_tightening(self):
  deck='.options reltol=1e-6 vntol=1e-9 abstol=1e-15\n'
  for name in ('reltol','vntol','abstol'):
   result=tighten_tolerances(deck,.1,[name])
   for other in ('reltol','vntol','abstol'):
    before=float(deck.split(other+'=')[1].split()[0]);after=float(result.split(other+'=')[1].split()[0])
    self.assertEqual(after,before*(.1 if other==name else 1))
 def test_reject_ambiguous_or_relaxed_controls(self):
  for scale,names in ((2,['reltol']),(.1,[]),(.1,['reltol','reltol']),(.1,['unknown'])):
   with self.assertRaises(ValueError):tighten_tolerances('reltol=1e-6',scale,names)
  with self.assertRaises(ValueError):tighten_tolerances('reltol=1e-6 reltol=1e-5',.1,['reltol'])

if __name__=='__main__':unittest.main()
