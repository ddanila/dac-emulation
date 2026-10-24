#!/usr/bin/env python3
"""Separate local-error tolerance controls without admitting failed captures."""
import argparse
import json
import lzma
import re
import shutil
from pathlib import Path
from reset_release_driver_review import trace_summary, completed, TRACES
from host_waveform_comparison import rows, compare_samples
from live_transition_review import diagnostic
from network_refinement_review import events
from ttl7406_probe import sha

HERE=Path(__file__).resolve().parent
CASES={'control':[], 'all':['reltol','vntol','abstol'],
       'reltol':['reltol'], 'vntol':['vntol'], 'abstol':['abstol']}


def normalized(deck, expected):
    for name,value in expected.items():
        matches=re.findall(r'\b'+name+r'=([0-9.eE+-]+)',deck)
        if len(matches)!=1 or float(matches[0])!=value:
            raise ValueError('Unexpected tolerance '+name)
        deck=re.sub(r'\b'+name+r'=[0-9.eE+-]+',name+'=<controlled>',deck)
    return deck


def startup_controls(root,out):
    cases={};identity=None
    for name,start in (('late',1001000),('early',0)):
        src=root/('tight-startup-'+name);dst=out/('startup-'+name);dst.mkdir()
        run=json.loads((src/'run.json').read_text())
        if run['mpfrStartNs']!=start or run['stopNs']!=100 or run['toleranceScale']!=.1 or run['toleranceComponents']!=['reltol']:
            raise ValueError('Unexpected startup control')
        ignored={'elapsedSeconds','exitCode','timedOut','solverDiagnostic','mpfrStartNs'}
        current={k:v for k,v in run.items() if k not in ignored}
        if identity is not None and current!=identity:raise ValueError('Unmatched startup controls')
        identity=current
        if sha(src/'io.cir')!=run['deckSha256']:raise ValueError('Changed startup deck')
        for file,digest in run['inputs'].items():
            if sha(src/file)!=digest:raise ValueError('Changed startup input')
        if sha(src/'sampling-grid.json')!=run['samplingGridSha256']:raise ValueError('Changed startup grid')
        for file in ('io.cir','run.json','sampling-grid.json'):shutil.copyfile(src/file,dst/file)
        log=(src/'ngspice.log').read_text()
        with lzma.open(dst/'ngspice.log.xz','wt') as stream:stream.write(log)
        traces={file:trace_summary(src/file) for file in TRACES if (src/file).exists()}
        (dst/'trace-endpoints.json').write_text(json.dumps(traces,indent=2)+'\n')
        cases[name]={'completed':completed(run,traces,diagnostic(log)),'timedOut':run['timedOut'],
                     'diagnostic':diagnostic(log),'elapsedSeconds':run['elapsedSeconds'],
                     'mpfrStartNs':start,'lastSeconds':{file:t['lastSeconds'] for file,t in traces.items()}}
    return {'cases':cases,'scope':'Matched 100 ns startup prefixes differing only in precision start. Shortening the observation window can change solver stepping; this is a separate startup control, not completion of the longer failed capture. No firmware traffic or refinement is qualified.'}


def retain(root,out):
    out.mkdir(parents=True,exist_ok=False)
    def source(name):
        return root/('fixture-grid-sampling-25' if name=='control' else 'fixture-grid-tolerance-'+('25' if name=='all' else name))
    cases={};receipts={};identity=None;canonical=None
    for name,components in CASES.items():
        src=source(name);dst=out/name;dst.mkdir()
        run=json.loads((src/'run.json').read_text());receipts[name]=run
        expected={key:value*(.1 if key in components else 1) for key,value in [('reltol',1e-6),('vntol',1e-9),('abstol',1e-15)]}
        deck=normalized((src/'io.cir').read_text(),expected)
        if canonical is not None and canonical!=deck:raise ValueError('Circuit differs beyond declared tolerances')
        canonical=deck
        if run['toleranceScale']!=(1 if name=='control' else .1):raise ValueError('Unexpected scale')
        if name!='control' and run.get('toleranceComponents',['reltol','vntol','abstol'])!=components:raise ValueError('Unexpected tolerance components')
        ignored={'elapsedSeconds','exitCode','timedOut','solverDiagnostic','deckSha256','toleranceScale','toleranceComponents','generatorSha256'}
        current={k:v for k,v in run.items() if k not in ignored}
        if identity is not None and current!=identity:raise ValueError('Unmatched runtime or stimulus')
        identity=current
        if not run.get('externalDependencies') or sha(src/'io.cir')!=run['deckSha256']:raise ValueError('Changed deck or missing runtime fingerprints')
        for file,digest in run['inputs'].items():
            if sha(src/file)!=digest:raise ValueError('Changed input')
        if sha(src/'sampling-grid.json')!=run['samplingGridSha256']:raise ValueError('Changed sampling grid')
        for file in ('io.cir','run.json','sampling-grid.json'):shutil.copyfile(src/file,dst/file)
        log=(src/'ngspice.log').read_text()
        with lzma.open(dst/'ngspice.log.xz','wt') as stream:stream.write(log)
        traces={file:trace_summary(src/file) for file in TRACES if any(Path(str(src/file)+suffix).exists() for suffix in ('','.gz','.xz'))}
        (dst/'trace-endpoints.json').write_text(json.dumps(traces,indent=2)+'\n')
        complete=completed(run,traces,diagnostic(log))
        cases[name]={'completed':complete,'timedOut':run['timedOut'],
                     'diagnostic':diagnostic(log),'bus':events(log) if complete else None,'tolerances':expected,
                     'lastSeconds':{file:record['lastSeconds'] for file,record in traces.items()}}
    comparisons={}
    for name in CASES:
        if name=='control' or not cases[name]['completed'] or not cases['control']['completed']:continue
        signals=receipts[name]['observationSignals']
        result=compare_samples(*(rows(source(n)/'network_witness.txt',signals,receipts[n]['stepNs']) for n in ('control',name)))
        comparisons[name]={'signals':{s:v for s,v in zip(signals,result['signals'])},'endSeconds':result['endSeconds'],
                           'busEventsIdentical':cases[name]['bus']==cases['control']['bus']}
    result={'schema':1,'startupPrecisionControls':startup_controls(root,out),'cases':cases,'completedControlComparisons':comparisons,
        'numericallyQualified':False,'electricallyQualified':False,'productionDefaultChangeAuthorized':False,
        'scope':'Independent tenfold tolerance tightening with unchanged physical model, sampling grid, integration method and precision window. Generator revisions differ only in selective-tolerance support; complete normalized decks and all other runtime/stimulus options are checked. Failed captures cannot establish refinement or full-repeat convergence.',
        'sources':{name:sha(HERE/name) for name in ('tolerance_controls_review.py','live_transition_probe.py','reset_release_driver_review.py','host_waveform_comparison.py','trace_io.py','sampling_grid.py')}}
    (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'manifest.json').write_text(json.dumps({str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()},indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runs',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--check',action='store_true');args=p.parse_args()
    if args.check:
        for name,digest in json.loads((args.out/'manifest.json').read_text()).items():
            if sha(args.out/name)!=digest:raise ValueError('Changed retained evidence: '+name)
        print('Tolerance control evidence hashes verified')
    else:
        if args.runs is None:p.error('--runs is required')
        result=retain(args.runs,args.out);print(json.dumps(result['cases'],indent=2))
