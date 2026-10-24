#!/usr/bin/env python3
"""Apply the unchanged three-level voltage gate to complete raw scenario captures."""
import argparse
from itertools import zip_longest
import json
from pathlib import Path
import re
from full_scenario_review import review as capture_review
from raw_pair_review import compare_raw
from trace_io import open_text


def event_records(path):
    with open_text(path) as stream:
        for line in stream:
            line=line.strip()
            if line.startswith(('BUS_EDGE_PS ','BUS_SAMPLE ','BUS_LATCH ','SERIAL_TX ','SERIAL_RX ')):
                yield line


def same_events(paths):
    count=0
    for records in zip_longest(*(event_records(p) for p in paths)):
        if any(r is None or r!=records[0] for r in records):
            raise ValueError('Firmware/bus/serial events differ across refinements')
        count+=1
    if not count:raise ValueError('Missing firmware observations')
    return count


def review(directories):
    if len(directories)!=3:raise ValueError('Need three successive refinement levels')
    captures=[capture_review(p) for p in directories]
    if not all(c['serialWindowsPassed'] for c in captures):raise ValueError('Scenario serial coverage failed')
    receipts=[json.loads((p/'run.json').read_text()) for p in directories]
    first=receipts[0]
    # Compare every experimental option rather than maintain an incomplete allowlist.
    varying={'stepNs','deckSha256','elapsedSeconds','compressedOutput','generatorSha256'}
    invariant=lambda r:{k:v for k,v in r.items() if k not in varying}
    for r in receipts[1:]:
        if invariant(r)!=invariant(first):raise ValueError('Different runtime, input, scope or experimental option')
    steps=[r['stepNs'] for r in receipts]
    if not steps[0]>0 or steps[0]!=2*steps[1] or steps[1]!=2*steps[2]:
        raise ValueError('Expected two successive maximum-step halvings')
    decks=[]
    for p,r in zip(directories,receipts):
        deck=(p/'io.cir').read_text()
        matches=re.findall(r'^\.tran (\S+) ',deck,re.M)
        if matches!=[f'{r["stepNs"]:g}n']:raise ValueError('Transient timestep differs from receipt')
        decks.append(re.sub(r'^(\.tran) \S+ ',r'\1 STEP ',deck,flags=re.M))
    if not all(d==decks[0] for d in decks):raise ValueError('Circuit differs beyond timestep')
    end=captures[0]['endSeconds']
    comparisons=[compare_raw(directories[i]/'waveform.raw',directories[i+1]/'waveform.raw',
        [captures[i]['samples'],captures[i+1]['samples']],end) for i in (0,1)]
    previous,finest=[c['signals'] for c in comparisons]
    if previous.keys()!=finest.keys():raise ValueError('Different observed signals')
    failures={name:{'previous':previous[name]['maximumAbsoluteDifference'],
                    'finest':v['maximumAbsoluteDifference']}
              for name,v in finest.items() if v['unit']=='V' and
              (v['maximumAbsoluteDifference']>.01 or
               v['maximumAbsoluteDifference']>previous[name]['maximumAbsoluteDifference'])}
    count=same_events([p/'ngspice.log' for p in directories])
    return {'voltageGatePassed':not failures,'voltageFailures':failures,'comparisons':comparisons,
            'firmwareEventRecordsCompared':count,'captures':captures,'qualified':False,
            'boundary':'Three complete scenario captures on absolute sample grids; unchanged 10 mV and per-node nonincreasing voltage gate. Separate disabled controls, bus acceptance, coupled rollback and device admission are still required.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('runs',nargs=3,type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.write_text(json.dumps(review(a.runs),indent=2)+'\n')
