import unittest
from fixture_grid_review import validate_receipts, bus_if_complete, validate_nested_inputs
from local_refinement_grid import grids
from sampling_grid import add_sampling_grid
import copy,json,tempfile
from pathlib import Path
from fixture_grid_review import validate_anchor_build, validate_anchor_grids, retain_generator
from ttl7406_probe import sha
from fixture_grid_review import validate_truncation_decks, validate_truncation_baseline
from transient_error_control import set_truncation_tolerance

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
 def test_nested_decks_reject_physical_changes_and_missing_points(self):
  assessment={'refinementPairs':[{'signals':{'v':{'unit':'V','timeSeconds':5e-7}}}]}
  common={'timesSeconds':[1e-7]}
  sampling={'control':common,**dict(zip(('25','12.5','6.25'),grids(assessment,common,1000)))}
  decks={name:add_sampling_grid('Vfixture_clock clock 0 5\nR1 a 0 100\n.tran 25n 1000n\n',grid['timesSeconds'],1000) for name,grid in sampling.items()}
  validate_nested_inputs(decks,sampling,assessment,1000)
  bad=dict(decks);bad['6.25']=bad['6.25'].replace('R1 a 0 100','R1 a 0 101')
  with self.assertRaises(ValueError):validate_nested_inputs(bad,sampling,assessment,1000)
  bad=copy.deepcopy(sampling);bad['6.25']['timesSeconds'].pop()
  with self.assertRaises(ValueError):validate_nested_inputs(decks,bad,assessment,1000)
 def test_nested_receipts_retain_candidate_constraints(self):
  runs=self.receipts('sampling')
  for name,run in runs.items():
   run.update(samplingGridSha256=name,toleranceScale=.1,toleranceComponents=['reltol'],mpfrStartNs=0,mpfrTransitionBits='256',conservativeCap=True,passiveAssembly=True)
  validate_receipts(runs,'nested-local')
  runs['control']['mpfrStartNs']=1
  with self.assertRaises(ValueError):validate_receipts(runs,'nested-local')
 def test_anchored_receipts_allow_only_declared_flag_and_grid(self):
  root=Path(__file__).resolve().parent/'reports/dac-anchored-startup'
  runs={name:json.loads((root/('disabled' if name=='control' else name)/'run.json').read_text()) for name in ('control','25','12.5','6.25')}
  for run in runs.values():run['haltNs']=None
  validate_receipts(runs,'dac-anchored')
  for field,value in [('dacAnchored',False),('haltNs',12),('dacStateAudit',True),('inputs',{}),('runtime',{})]:
   bad=copy.deepcopy(runs);bad['6.25'][field]=value
   with self.assertRaises(ValueError):validate_receipts(bad,'dac-anchored')
 def test_dense_anchored_full_window_and_retained_grids(self):
  root=Path(__file__).resolve().parent/'reports/startup-tight-tolerance'
  runs={name:json.loads((root/('25' if name=='control' else name)/'run.json').read_text()) for name in ('control','25','12.5','6.25')}
  for name,run in runs.items():run.update(haltNs=None,dacAnchored=name!='control',startupTruncAudit=False)
  validate_receipts(runs,'dense-anchored');validate_anchor_grids(runs,'dense-anchored')
  for field,value in [('toleranceScale',.1),('stopNs',2000),('haltNs',2000),('startupTruncAudit',True),('dacAnchored',False)]:
   bad=copy.deepcopy(runs);bad['6.25'][field]=value
   with self.assertRaises(ValueError):validate_receipts(bad,'dense-anchored')
  bad=copy.deepcopy(runs);bad['6.25']['samplingGridSha256']=runs['25']['samplingGridSha256']
  with self.assertRaises(ValueError):validate_anchor_grids(bad,'dense-anchored')
 def transient_inputs(self):
  root=Path(__file__).resolve().parent/'reports/dense-anchored-refinement'
  runs={name:json.loads((root/('25' if name=='control' else name)/'run.json').read_text()) for name in ('control','25','12.5','6.25')}
  decks={name:set_truncation_tolerance((root/('25' if name=='control' else name)/'io.cir').read_text(),1 if name=='control' else .25) for name in runs}
  for name,run in runs.items():run.update(filterTruncAudit=False,truncationTolerance=1 if name=='control' else .25)
  return runs,decks
 def test_transient_error_receipts_and_baseline(self):
  runs,decks=self.transient_inputs()
  validate_receipts(runs,'transient-error');validate_anchor_grids(runs,'transient-error')
  validate_truncation_decks(decks);validate_truncation_baseline(runs['control'],decks['control'])
  for field,value in [('truncationTolerance',1),('filterTruncAudit',True),('dacAnchored',False),('haltNs',2000),('stopNs',2000),('toleranceScale',.1),('runtime',{}),('generatorSha256','changed')]:
   bad=copy.deepcopy(runs);bad['6.25'][field]=value
   with self.assertRaises(ValueError):validate_receipts(bad,'transient-error')
 def test_transient_error_decks_reject_extra_options_and_physical_changes(self):
  runs,decks=self.transient_inputs()
  for edit in (lambda d:d.replace('trtol=0.25','trtol=0.5'),lambda d:d+'\n.options trtol=.25\n',lambda d:d+'\nset xtrtol=7\n',lambda d:d+'\nRunexpected a 0 100\n'):
   bad=dict(decks);bad['6.25']=edit(bad['6.25'])
   with self.assertRaises(ValueError):validate_truncation_decks(bad)
 def test_explicit_baseline_rejects_changed_inputs(self):
  runs,decks=self.transient_inputs();run=runs['control'];deck=decks['control']
  for field,value in [('truncationTolerance',.25),('filterTruncAudit',True),('inputs',{}),('runtime',{}),('haltNs',2000)]:
   bad=copy.deepcopy(run);bad[field]=value
   with self.assertRaises(ValueError):validate_truncation_baseline(bad,deck)
  with self.assertRaises(ValueError):validate_truncation_baseline(run,deck+'\nRunexpected a 0 100\n')
 def test_retains_exact_generator_and_rejects_missing_source(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);out=root/'report';out.mkdir()
   current=root/'current.py';current.write_text('newer runner\n')
   frozen=root/'frozen.py';frozen.write_text('capture runner\n')
   expected=sha(frozen)
   receipt=retain_generator((current,frozen),out,expected)
   self.assertEqual(receipt,{'path':'capture-generator.py','sha256':expected})
   self.assertEqual((out/receipt['path']).read_bytes(),frozen.read_bytes())
   frozen.write_text('changed runner\n')
   with self.assertRaises(ValueError):retain_generator((current,frozen),out,expected)
 def test_anchored_build_fingerprints(self):
  root=Path(__file__).resolve().parent/'reports/dac-anchored-startup'
  run=json.loads((root/'25/run.json').read_text());build=json.loads((root/'build.json').read_text())
  validate_anchor_build(run,build)
  for key in ('digital.cm','spinit'):
   bad=copy.deepcopy(build);bad['outputs'][key]='changed'
   with self.assertRaises(ValueError):validate_anchor_build(run,bad)
  bad=copy.deepcopy(build);bad['dacAnchorHeaderSha256']='changed'
  with self.assertRaises(ValueError):validate_anchor_build(run,bad)
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
