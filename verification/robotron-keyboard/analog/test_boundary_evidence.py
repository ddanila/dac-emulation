#!/usr/bin/env python3
import hashlib,json,re,unittest
from pathlib import Path
from unknown_output_probe import assess
from io_scenario import load,observe
from boundary_campaign_review import review
HERE=Path(__file__).resolve().parent
ROOT=HERE/'reports/boundary-refinement'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
class BoundaryEvidenceTest(unittest.TestCase):
 def test_completed_series_preserve_the_qualification_boundary(self):
  expected=json.loads((ROOT/'assessment.json').read_text())
  self.assertEqual(review(ROOT),expected)
  self.assertTrue(expected['completedRefinementSeries']);self.assertFalse(expected['qualified'])
  for comparison in expected['comparisons']:
   self.assertTrue(comparison['firmwareReadsPreserved'])
   self.assertGreater(comparison['candidatePeaks']['v(n_TA_DATEN)']['value'],4)
  checked={}
  for kind in ('zero','adc'):
   report=json.loads((ROOT/f'{kind}-series.json').read_text())
   for pair,levels in zip(report['pairs'],((25,12),(12,6))):
    for label,level in zip(('coarse','fine'),levels):
     for name,digest in pair['artifacts'][label].items():
      p=ROOT/f'network-{kind}{level}'/name
      if not p.exists():p=p.with_name(p.name+'.xz')
      if p not in checked:checked[p]=sha(p)
      self.assertEqual(checked[p],digest)
 def test_undefined_threshold_memory(self):
  root=ROOT/'unknown-output';report=json.loads((root/'assessment.json').read_text())
  self.assertFalse(report['qualified'])
  for run in report['runs']:
   p=root/str(run['stepNs'])
   for name,digest in run['artifacts'].items():self.assertEqual(sha(p/name),digest)
   rows=[list(map(float,l.split())) for l in (p/'trace.txt').read_text().splitlines()[1:]]
   self.assertEqual(assess(rows),run['plateaus'])
 def test_analytic_crossings_and_disabled_controls(self):
  for label,tolerance in (('adc-crossing',1e-15),('adc-crossing-rc',1e-12)):
   p=ROOT/label;report=json.loads((p/'assessment.json').read_text())
   self.assertTrue(report['crossingRegressionPassed']);self.assertFalse(report['qualified'])
   for run in report['runs']:
    q=p/f'{"on" if run["enabled"] else "off"}-{run["stepNs"]}'
    for name,digest in run['artifacts'].items():self.assertEqual(sha(q/name),digest)
    events=[(float.fromhex(t),int(state)) for t,state in re.findall(r'ADC_CROSS time=(\S+) node=source value=\S+ old=\d+ new=(\d+)',(q/'ngspice.log').read_text())]
    self.assertEqual(events,[(e['timeSeconds'],e['new']) for e in run['events']])
    if run['enabled']:
     self.assertEqual(len(events),len(run['expectedTimesNs']))
     self.assertLessEqual(max(abs(e[0]-t*1e-9) for e,t in zip(events,run['expectedTimesNs'])),tolerance)
  for run in json.loads((ROOT/'adc-crossing/disabled-control.json').read_text())['controls']:
   for label in ('original','off'):self.assertEqual(sha(ROOT/'adc-crossing'/f'{label}-{run["stepNs"]}'/'trace.txt'),run['traceSha256'])
 def test_traffic_is_reference_only_and_observations_are_exercised(self):
  root=ROOT/'traffic';report=json.loads((root/'assessment.json').read_text())
  self.assertTrue(report['preflightPassed']);self.assertFalse(report['qualified'])
  left,right=report['resetPlacement']['uninterruptedNeighborBits'];cycle=report['resetPlacement']['cycle']
  self.assertLess(left[0],cycle);self.assertLess(cycle,right[0])
  for name,case in report['cases'].items():
   p=root/name;scenario=load(p/'scenario.json')
   events=[(int(t),int(bit)) for t,bit in re.findall(r'^BIT (\d+) ([01])$',(p/'reference.log').read_text(),re.M)]
   self.assertEqual(observe(scenario,events),case['referenceCoverage'])
   self.assertTrue(case['referenceCoverage']['passed']);self.assertFalse(case['electricalExecuted'])
   for name,digest in case['preparedArtifacts'].items():
    if name!='io.vvp':self.assertEqual(sha(p/name),digest)
if __name__=='__main__':unittest.main()
