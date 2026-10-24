import unittest
from fixture_grid_review import validate_receipts

class MatchedControls(unittest.TestCase):
 def receipts(self,experiment):
  return {name:{'stepNs':25 if name=='control' else float(name),
    'method':'gear' if experiment=='integration' and name!='control' else 'trap',
    'fixtureCrossingGuardPs':None if experiment=='crossings' and name=='control' else .25,
    'runtime':{'digest':'same'},'mpfrStartNs':1001000,'toleranceScale':1}
    for name in ('control','25','12.5','6.25')}
 def test_declared_controls(self):
  for experiment in ('crossings','integration'):
   validate_receipts(self.receipts(experiment),experiment)
 def test_reject_unmatched_or_wrong_controls(self):
  for experiment in ('crossings','integration'):
   for field,value in [('runtime',{'digest':'different'}),('mpfrStartNs',1002000),
                       ('toleranceScale',2),('fixtureCrossingGuardPs',.5),('stepNs',100),
                       ('method','unknown')]:
    runs=self.receipts(experiment);runs['6.25'][field]=value
    with self.assertRaises(ValueError):validate_receipts(runs,experiment)

if __name__=='__main__':unittest.main()
