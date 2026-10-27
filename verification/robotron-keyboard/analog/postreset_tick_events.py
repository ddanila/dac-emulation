#!/usr/bin/env python3
"""Retain logged output-event timing around failed absolute-tick refinement peaks."""
import argparse,json,math,hashlib
from pathlib import Path
from trace_io import open_binary
from ttl7406_probe import sha
from postreset_tick_peaks import PAIRS,targets


def parse(line):
    fields=dict(x.split('=',1) for x in line.split()[2:])
    if set(fields)!={'actual','target','base','port'}:raise ValueError('Unexpected output-event fields')
    if not all(math.isfinite(float(fields[n])) for n in ('actual','target','base')):raise ValueError('Nonfinite event time')
    return fields


def review(root):
    full=json.loads((root/'full-assessment.json').read_text());centers=targets(full);runs={}
    for label in ('coarse','fine','finest'):
        d=json.loads((root/(label+'.json')).read_text())
        if not d['events'] or d['sourceReceiptSha256']!=full['receipts'][label]:raise ValueError('Missing or unbound output events')
        for event in d['events']:parse('TIME_AUDIT output '+' '.join(k+'='+v for k,v in event.items()))
        runs[label]=d['events']
    pairs={}
    for pair,(left,right) in PAIRS.items():
        a,b=runs[left],runs[right];same=[e['port'] for e in a]==[e['port'] for e in b]
        changed=[]
        if same:
            for i,(x,y) in enumerate(zip(a,b)):
                if any(x[n]!=y[n] for n in ('actual','target','base')):changed.append(dict(ordinal=i,left=x,right=y))
        pairs[pair]=dict(samePortSequence=same,counts=[len(a),len(b)],changedTimes=changed)
    contexts=[]
    for t in centers:
        context={}
        for label,events in runs.items():
            context[label]=[dict(ordinal=i,**e) for i,e in enumerate(events)
                            if e['port'] in ('bus_high','bus_low','wr_high','wr_low') and t-30e-9<=float(e['target'])<=t+10e-9]
        contexts.append(dict(peakSeconds=t,events=context))
    return dict(qualified=False,fullAssessmentSha256=sha(root/'full-assessment.json'),pairs=pairs,peakContexts=contexts,
                scope='Complete logged output-event sequence and explicit target-time neighborhoods. String times retained without rounding; comparisons do not align trajectories. TIME_AUDIT omits output values and input threshold history, so matching events do not prove matching internal state or causality.')


def extract(assessment,folders,out):
    out.mkdir(exist_ok=False);(out/'full-assessment.json').write_bytes(assessment.read_bytes());full=json.loads(assessment.read_text())
    for label,folder in folders.items():
        if sha(folder/'run.json')!=full['receipts'][label]:raise ValueError('Wrong reviewed log')
        source=folder/'ngspice.log.xz';before=sha(source)
        events=[];digest=hashlib.sha256();size=0
        with open_binary(folder/'ngspice.log') as stream:
            for raw in stream:
                digest.update(raw);size+=len(raw)
                if raw.strip().startswith(b'TIME_AUDIT output '):events.append(parse(raw.decode('ascii').strip()))
        receipt=json.loads((folder/'run.json').read_text())
        if digest.hexdigest()!=receipt['log']['sha256'] or size!=receipt['log']['bytes']:raise ValueError('Changed full reviewed log')
        if sha(source)!=before:raise ValueError('Log changed during extraction')
        (out/(label+'.json')).write_text(json.dumps(dict(sourceReceiptSha256=sha(folder/'run.json'),sourceCompressedSha256=before,events=events),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('assessment','coarse','fine','finest','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed event assessment')
    else:
        if not all((a.assessment,a.coarse,a.fine,a.finest,a.out)):p.error('Need reviewed captures and fresh output')
        extract(a.assessment,{n:getattr(a,n) for n in ('coarse','fine','finest')},a.out)
