#!/usr/bin/env python3
"""Retain tight-startup stamping controls and the extended live candidate."""
import argparse
import json
import lzma
import shutil
from pathlib import Path
from reset_release_driver_review import trace_summary, completed, TRACES
from live_transition_review import diagnostic
from network_refinement_review import events
from ttl7406_probe import sha

HERE=Path(__file__).resolve().parent
CASES={'precision':'tight-startup-2us','capacitor':'tight-startup-2us-cap',
       'passive':'tight-startup-2us-passive','extended':'tight-passive-full-25'}


def validate_controls(receipts):
    if set(receipts)!=set(CASES):raise ValueError('Missing control')
    identity=None;short_decks=set()
    for name,run in receipts.items():
        expected=(name!='precision',name in ('passive','extended'))
        if (run['conservativeCap'],run['passiveAssembly'])!=expected:raise ValueError('Unexpected stamping controls')
        if run['stopNs']!=(1006000 if name=='extended' else 2000) or run['mpfrStartNs']!=0 or run['toleranceScale']!=.1 or run['toleranceComponents']!=['reltol']:
            raise ValueError('Unexpected window or tolerance')
        ignored={'elapsedSeconds','exitCode','timedOut','solverDiagnostic','deckSha256','stopNs','conservativeCap','passiveAssembly'}
        current={k:v for k,v in run.items() if k not in ignored}
        if identity is not None and identity!=current:raise ValueError('Different runtime, circuit or stimulus')
        identity=current
        if name!='extended':short_decks.add(run['deckSha256'])
    if len(short_decks)!=1:raise ValueError('Short control decks differ')


def retain(root,out):
    out.mkdir(parents=True,exist_ok=False)
    cases={};receipts={}
    for name,folder in CASES.items():
        src=root/folder;dst=out/name;dst.mkdir()
        run=json.loads((src/'run.json').read_text())
        receipts[name]=run
        if not run.get('externalDependencies') or sha(src/'io.cir')!=run['deckSha256']:raise ValueError('Missing runtime or changed deck')
        for file,digest in run['inputs'].items():
            if sha(src/file)!=digest:raise ValueError('Changed executable input')
        if sha(src/'sampling-grid.json')!=run['samplingGridSha256']:raise ValueError('Changed sampling grid')
        for file in ('io.cir','run.json','sampling-grid.json'):shutil.copyfile(src/file,dst/file)
        log=(src/'ngspice.log').read_text()
        with lzma.open(dst/'ngspice.log.xz','wt') as stream:stream.write(log)
        traces={file:trace_summary(src/file) for file in TRACES if any(Path(str(src/file)+suffix).exists() for suffix in ('','.gz','.xz'))}
        (dst/'trace-endpoints.json').write_text(json.dumps(traces,indent=2)+'\n')
        done=completed(run,traces,diagnostic(log))
        cases[name]={'completed':done,'timedOut':run['timedOut'],'diagnostic':diagnostic(log),
            'elapsedSeconds':run['elapsedSeconds'],'requiredEndSeconds':run['stopNs']*1e-9,
            'lastSeconds':{file:t['lastSeconds'] for file,t in traces.items()},
            'bus':events(log) if done and name=='extended' else None}
    validate_controls(receipts)
    result={'schema':1,'cases':cases,'shortControlDecksIdentical':True,
        'numericallyQualified':False,'electricallyQualified':False,'productionDefaultChangeAuthorized':False,
        'scope':'Identical 2 us decks isolate precision-only, exact capacitor loading, and exact capacitor plus later passive additions. The extended candidate preserves physical source inputs, precision and tolerances but changes observation duration and scheduled fixture crossings. Completion is not timestep refinement, full-repeat coverage, or physical model admission. Failed and timed-out controls remain failures.',
        'sources':{name:sha(HERE/name) for name in ('startup_passive_review.py','live_transition_probe.py','reset_release_driver_review.py','live_transition_review.py','network_refinement_review.py','trace_io.py')}}
    (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'manifest.json').write_text(json.dumps({str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()},indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runs',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--check',action='store_true');args=p.parse_args()
    if args.check:
        for name,digest in json.loads((args.out/'manifest.json').read_text()).items():
            if sha(args.out/name)!=digest:raise ValueError('Changed retained evidence: '+name)
        print('Startup passive evidence hashes verified')
    else:
        if args.runs is None:p.error('--runs is required')
        result=retain(args.runs,args.out);print(json.dumps(result['cases'],indent=2))
