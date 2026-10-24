import unittest
from fixture_grid_review import validate_receipts, bus_if_complete

class MatchedControls(unittest.TestCase):
 def receipts(self,experiment):
  return {name:{'stepNs':25 if name=='control' else float(name),
    'method':'gear' if experiment=='integration' and name!='control' else 'trap',
    'fixtureCrossingGuardPs':None if experiment=='crossings' and name=='control' else .25,
    'samplingGridSha256':'grid-hash' if experiment=='sampling' and name!='control' else None,
    'runtime':{'digest':'same'},'mpfrStartNs':1001000,'toleranceScale':1}
    for name in ('control','25','12.5','6.25')}
 def test_declared_controls(self):
  for experiment in ('crossings','integration','sampling'):
   validate_receipts(self.receipts(experiment),experiment)
 def test_tight_passive_refinement(self):
  runs=self.receipts('sampling');del runs['control']
  for run in runs.values():run.update(toleranceScale=.1,toleranceComponents=['reltol'],mpfrStartNs=0,mpfrTransitionBits='256',conservativeCap=True,passiveAssembly=True)
  validate_receipts(runs,'tight-passive')
  for run in runs.values():run['passiveAssembly']=False
  with self.assertRaises(ValueError):validate_receipts(runs,'tight-passive')
 def test_incomplete_capture_does_not_require_bus_reads(self):
  self.assertIsNone(bus_if_complete('run simulation(s) aborted',False))
  with self.assertRaises(ValueError):bus_if_complete('No bus observations',True)
 def test_reject_unmatched_or_wrong_controls(self):
  for experiment in ('crossings','integration','sampling'):
   for field,value in [('runtime',{'digest':'different'}),('mpfrStartNs',1002000),
                       ('toleranceScale',2),('fixtureCrossingGuardPs',.5),('stepNs',100),
                       ('samplingGridSha256','other'),('method','unknown')]:
    runs=self.receipts(experiment);runs['6.25'][field]=value
    with self.assertRaises(ValueError):validate_receipts(runs,experiment)

if __name__=='__main__':unittest.main()
