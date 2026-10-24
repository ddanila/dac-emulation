#!/usr/bin/env python3
"""Retain bounded live reset-release controls without qualifying failed prefixes."""
import argparse
import hashlib
import json
import math
import re
import shutil
from pathlib import Path
from failure_evidence import solver_diagnostic
from ttl7406_probe import sha
from trace_io import open_binary

HERE=Path(__file__).resolve().parent
CASES=('trap','gear','dac-corners','corners-25','corners-12.5','corners-6.25')
TRACES=('witness.txt','bus-trace.txt','driver-trace.txt','wr-trace.txt','network_witness.txt')

def trace_summary(path):
    first=last=None;count=0;valid=True;tail=[]
    digest=hashlib.sha256();size=0
    with open_binary(path) as stream:
        raw=next(stream);digest.update(raw);size+=len(raw)
        header=raw.decode('ascii').split()
        if len(header)<2 or header[0]!='time':raise ValueError('Missing waveform header')
        for line in stream:
            digest.update(line);size+=len(line)
            row=list(map(float,line.split()))
            if len(row)!=len(header) or not all(map(math.isfinite,row)):raise ValueError('Invalid waveform values')
            if last is not None and row[0]<=last:valid=False
            if first is None:first=row[0]
            last=row[0];count+=1;tail.append(row)
            if len(tail)>8:tail.pop(0)
    return {'sha256':digest.hexdigest(),'bytes':size,'samples':count,'firstSeconds':first,
            'lastSeconds':last,'strictlyIncreasing':valid,'columns':header,'tail':tail}

def completed(run, traces, diagnostic):
    if run['timedOut'] or run['exitCode']!=0 or diagnostic or set(traces)!=set(TRACES):return False
    end=run['stopNs']*1e-9
    return all(t['samples']>=2 and t['strictlyIncreasing'] and t['firstSeconds']==0 and
               t['lastSeconds'] is not None and math.isfinite(t['lastSeconds']) and abs(t['lastSeconds']-end)<=1e-15
               for t in traces.values())

def retain(root,out):
    out.mkdir(parents=True,exist_ok=False)
    cases={};identity=None
    for name in CASES:
        source=root/name;run=json.loads((source/'run.json').read_text());deck=(source/'io.cir').read_text();log=(source/'ngspice.log').read_text()
        if sha(source/'io.cir')!=run['deckSha256']:raise ValueError('Changed deck')
        for file,digest in run['inputs'].items():
            if sha(source/file)!=digest:raise ValueError('Changed runtime input')
        current=(run['sourceDeckSha256'],run['runtime'],run['inputs'])
        if identity is not None and current!=identity:raise ValueError('Different circuit inputs or simulator runtime')
        identity=current
        if run['toleranceScale']!=1 or not run['physicalDriverTrace'] or run['matrixBoundarySubstitution']:
            raise ValueError('Different live circuit or tolerances')
        traces={p:trace_summary(source/p) for p in TRACES if (source/p).exists()}
        diagnostic=solver_diagnostic(log)
        target=out/name;target.mkdir()
        for file in ('io.cir','run.json','ngspice.log'):shutil.copyfile(source/file,target/file)
        (target/'trace-endpoints.json').write_text(json.dumps(traces,indent=2)+'\n')
        failure=re.search(r'Timestep too small; time = ([\d.eE+-]+)',log)
        reset=re.findall(r'RESET (\d+) 1',log)
        cases[name]={'requiredEndSeconds':run['stopNs']*1e-9,'completed':completed(run,traces,diagnostic),
            'stepNs':run['stepNs'],'method':run['method'],'dacCorners':run['enabled'],
            'solverDiagnostic':diagnostic,'reportedFailureSeconds':float(failure[1]) if failure else None,
            'resetReleaseEventsPs':[int(t) for t in reset],
            'observedLastSeconds':{p:t['lastSeconds'] for p,t in traces.items()},
            'files':{str(p.relative_to(out)):sha(p) for p in sorted(target.iterdir())}}
    ready=all(cases[n]['completed'] for n in CASES if n.startswith('corners-'))
    result={'schema':1,'cases':cases,'refinementCapturesComplete':ready,
        'numericallyQualified':False,'electricallyQualified':False,'productionDefaultChangeAuthorized':False,
        'comparison':{'performed':False,'reason':'Waveform comparison requires complete matching refinement windows; failed or truncated traces cannot substitute.' if not ready else 'Complete captures require a separate all-saved waveform and firmware comparison.'},
        'scope':'Original live CPU/HDL, standard S600, direct drivers, matrix and host/filter circuit. Only stop time, maximum step, integration method and the existing opt-in DAC-corner fix vary. No model parameters or solver tolerances are relaxed. Trace tails are diagnostic evidence, not complete captures; raw traces remain in the local run directories with hashes retained here.',
        'runtimeLimit':'The original runner fingerprints ngspice, code models, bytecode and ROM. External VPI/shared-library dependencies were not independently fingerprinted before these runs; this investigation cannot admit production runtime equivalence.',
        'nextAction':'Investigate the live boundary at the first post-reset data-bus drive. Any fix must complete both finer steps and its disabled controls before full-repeat testing.',
        'sources':{name:sha(HERE/name) for name in ('reset_release_driver_review.py','live_transition_probe.py','network_trace.py','failure_evidence.py')}}
    (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--runs',type=Path,required=True);parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    result=retain(args.runs,args.out)
    print(json.dumps({n:{k:v for k,v in r.items() if k in ('completed','reportedFailureSeconds','stepNs')} for n,r in result['cases'].items()},indent=2))
