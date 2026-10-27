#!/usr/bin/env python3
"""Isolate full-window coarse drain effects without claiming refinement acceptance."""
import argparse
import json
import lzma
from pathlib import Path
from postreset_drain_capture import experiment
from postreset_drain_review import validate
from raw_stream_review import compare_streams
from ttl7406_probe import sha

HERE=Path(__file__).resolve().parent


def assess(source,tick,drain):
    base=json.loads((source/'run.json').read_text());baseline_hash=sha(source/'run.json')
    if baseline_hash!=sha(HERE/'reports/postreset-adc/25/run.json'):raise ValueError('Changed baseline')
    runs=[json.loads((p/'run.json').read_text()) for p in (tick,drain)]
    build_hash=sha(tick/'candidate-build.json');bounded_hash=sha(tick/'bounded-assessment.json')
    if bounded_hash!=sha(HERE/'reports/output-drain-board/assessment.json'):raise ValueError('Changed bounded controls')
    def vpi(r):
        matches=[d for d in r['externalDependencies'] if Path(d['path']).name=='ivlng.vpi']
        if len(matches)!=1:raise ValueError('Ambiguous VPI identity')
        return matches[0]
    old,new=vpi(base),vpi(runs[0])
    if old==new or new['sha256']!=json.loads((tick/'candidate-build.json').read_text())['outputs']['ivlng.vpi']:
        raise ValueError('Unbound candidate')
    deps=sorted([new if d==old else d for d in base['externalDependencies']],key=lambda d:d['path'])
    for name,h in base['inputs'].items():
        if sha(source/name)!=h:raise ValueError('Changed baseline input')
    for p,r,mode in zip((tick,drain),runs,('tick','on')):
        validate(r,base,mode,25,baseline_hash,build_hash,bounded_hash)
        if sha(p/'candidate-build.json')!=build_hash or sha(p/'bounded-assessment.json')!=bounded_hash:
            raise ValueError('Changed runtime build/control')
        deck,env=experiment((source/'io.cir').read_text(),base['environment'],old['path'],new['path'],mode,25)
        if (p/'io.cir').read_text()!=deck or r['environment']!=env or r['externalDependencies']!=deps:
            raise ValueError('Unmatched experiment')
        for name,h in r['inputs'].items():
            if sha(p/name)!=h or (name!='io.cir' and h!=base['inputs'][name]):raise ValueError('Changed experiment input')
    counts=[r['logSummary']['count'] for r in runs]
    with lzma.open(tick/'waveform.raw.xz','rb') as a,lzma.open(drain/'waveform.raw.xz','rb') as b:
        result=compare_streams(a,b,.00116,lambda:counts,exact=True)
    for observed,r in zip(result['streams'],runs):
        if any(observed[k]!=r['storage']['waveform.raw'][k] for k in ('bytes','sha256')):
            raise ValueError('Changed captured waveform')
    return dict(completed=True,qualified=False,coarseSamplesExactlyEqual=True,comparison=result['comparison'],
        streams=result['streams'],receipts={name:sha(p/'run.json') for name,p in (('baseline',source),('tick',tick),('drain',drain))},
        candidateBuildSha256=build_hash,boundedAssessmentSha256=bounded_hash,
        sources={n:sha(HERE/n) for n in ('postreset_drain_coarse_review.py','postreset_drain_capture.py','postreset_drain_review.py','raw_stream_review.py')},
        scope='Matched 25-ns exact-tick-only and drain-enabled runs across the complete 1.16-ms ADC-enabled window. Every saved electrical sample is identical. This cannot establish internal scheduler-state identity, finer-level convergence, firmware equivalence or full campaign acceptance; those remain with the complete campaign reviewer.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','tick','drain','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();result=assess(a.source,a.tick,a.drain)
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
