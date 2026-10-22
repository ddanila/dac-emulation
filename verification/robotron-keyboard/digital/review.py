#!/usr/bin/env python3
"""Retain raw timing while assessing an identical half-open observation interval."""
import argparse
from collections import Counter
import json
from pathlib import Path
from qualify import BOARD,ROOT,sha,parse,assess,scenarios

def observation_window(values,stop):
    inside={k:[e for e in v if 0<=int(e[0])<stop] for k,v in values.items()}
    outside={k:[e for e in v if not 0<=int(e[0])<stop] for k,v in values.items()}
    return inside,outside

def review(report,directory):
    for name,digest in report['sources'].items():
        if sha(ROOT/name)!=digest:raise ValueError('Changed producer source: '+name)
    if not report['allScenariosRun'] or {c['scenario']['id'] for c in report['cases']}!={c['id'] for c in scenarios()}:raise ValueError('Incomplete scenario coverage')
    rows=[]
    for case in report['cases']:
        spec=case['scenario'];folder=directory/spec['id']
        for name,digest in case['artifacts'].items():
            if sha(folder/name)!=digest:raise ValueError('Changed capture: '+str(folder/name))
        events=[parse(folder/(lang+'.txt')) for lang in ('c','hdl')];boundary={};trimmed=[]
        for lang,values in zip(('c','hdl'),events):
            inside,boundary[lang]=observation_window(values,spec['cycles']);trimmed.append(inside)
        row=assess(spec,*trimmed)
        row['postResetSerialAgreement']=all([e[1:] for e in trimmed[0]['BIT'] if int(e[0])>=event[0]+16]==[e[1:] for e in trimmed[1]['BIT'] if int(e[0])>=event[0]+16] for event in spec['events'] if event[1]=='reset')
        row['outsideObservationInterval']=boundary;row['busAssertionTiming']={}
        for flag,name in [('5','ioRead'),('3','ioWrite'),('2','memoryWrite')]:
            c,h=[[e for e in v['BUS'] if e[1]==flag] for v in trimmed]
            row['busAssertionTiming'][name]={'cCount':len(c),'hdlCount':len(h),'addressesEquivalent':[e[2] for e in c]==[e[2] for e in h],'offsetCounts':dict(sorted(Counter(int(y[0])-int(x[0]) for x,y in zip(c,h)).items()))}
        rows.append(row)
    base=json.loads((BOARD/'reports/full-audit.json').read_text())
    for name,digest in {**base['sources'],**base['cpuSources']}.items():
        if sha(ROOT/name)!=digest:raise ValueError('Stale baseline: '+name)
    if base['firmware']['romSha256']!=report['romSha256']:raise ValueError('Different ROM')
    contacts={(e[2],e[3]) for c in rows if c['scenario']['id'].startswith('column-') for e in c['scenario']['events'] if e[1]=='key'}
    gates={
      'fullBusAudit':base['bus']['equivalent'],
      'virtualBridgeService':base['service']['equivalent'],
      'allMatrixPositionsExercised':contacts=={(c,r) for c in range(13) for r in range(8)},
      'repeatReleaseBaseline':base['firmware']['stimulusCoveragePassed'],
      'expandedFunctionalAgreement':all(r['functionalAgreement'] for r in rows),
      'rawCycleAgreement':base['firmware']['serialCycleOffsets']==[0] and set(base['firmware']['ledCycleOffsetCounts'])=={'0'} and all(r['rawCycleAgreement'] for r in rows),
      'postResetSerialRecovery':all(r['postResetSerialAgreement'] for r in rows),
      'resetDuringFrameWitnessed':all(v['partial26BitFrame'] and v['postResetBits']>=26 for r in rows for w in r['resetWitnesses'] for v in w.values()),
    }
    return {'schema':1,'romSha256':report['romSha256'],'gates':gates,'digitalComplete':all(gates.values()),'electricallyQualified':False,'specimenQualified':False,'observationInterval':'0 <= fixture cycle < declared stop; out-of-window observations are retained separately, with no phase shift or interior-event deletion.','cases':rows,'producerSha256':sha(directory/'assessment.json'),'baselineSha256':sha(BOARD/'reports/full-audit.json'),'reviewerSha256':sha(Path(__file__)),'boundary':'Matching output sequences establish only the declared stimuli and digital boundaries. CPU read and write assertion phases remain independently visible; this comparison cannot choose which CPU is faithful to U880 pin timing.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    report=review(json.loads((a.run/'assessment.json').read_text()),a.run)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report['gates'],indent=2))
    return 0 if report['digitalComplete'] else 1
if __name__=='__main__':raise SystemExit(main())
