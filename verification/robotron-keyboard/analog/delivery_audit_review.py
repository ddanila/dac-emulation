#!/usr/bin/env python3
"""Validate logged delivery transitions and exact controls against the drain bridge."""
import argparse
import json
import math
from pathlib import Path
from trace_io import open_binary
from output_drain_board_review import assess as board_assess
from raw_pair_review import compare_raw
from audit_log import equal
from postreset_startup_review import FIRMWARE
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def scan(path):
    pending=None;counts={'input':0,'output-before':0,'output-after':0};clamped=0;input_ahead=0.
    with open_binary(path) as stream:
        for raw in stream:
            if not raw.startswith(b'DELIVERY_AUDIT '):continue
            fields=raw.decode('ascii').split();kind=fields[1];d=dict(x.split('=',1) for x in fields[2:])
            if kind not in counts or set(d)!={'actual','target','base','stop','port','aval','bval'}:raise ValueError('Malformed delivery audit')
            for key in ('actual','target','base'):
                d[key]=float(d[key])
                if not math.isfinite(d[key]) or d[key]<0:raise ValueError('Invalid delivery time')
            for key in ('stop','aval','bval'):d[key]=int(d[key])
            if d['stop'] not in (0,1) or any(not 0<=d[k]<=0xffffffff for k in ('aval','bval')):raise ValueError('Invalid callback state/value')
            counts[kind]+=1
            if kind=='input':
                if pending is not None:raise ValueError('Input inside output pair')
                input_ahead=max(input_ahead,d['target']-d['actual'])
            elif kind=='output-before':
                if pending is not None:raise ValueError('Missing output-after')
                pending=d
            else:
                if pending is None:raise ValueError('Missing output-before')
                expected=dict(pending)
                if pending['stop']:
                    expected.update(target=max(pending['actual'],pending['base']),stop=0)
                    clamped+=pending['base']>pending['actual']
                if d!=expected:raise ValueError('Output transition violates source clamp')
                pending=None
    if pending is not None or not all(counts.values()):raise ValueError('Incomplete delivery audit')
    return dict(counts=counts,clampedOutputGroups=clamped,maximumInputTargetAheadSeconds=input_ahead)


def assess(root):
    result=board_assess(root,HERE/'output_drain_board_capture.py')
    retained=HERE/'reports/output-drain-board'
    manifest=json.loads((retained/'manifest.json').read_text())
    if any(sha(retained/n)!=h for n,h in manifest['files'].items()):raise ValueError('Changed retained controls')
    original=json.loads((retained/'assessment.json').read_text())
    comparisons={};audits={}
    for mode in ('off','tick','on','retry'):
        a,b=root/mode,retained/mode
        r=json.loads((b/'run.json').read_text())
        if sha(b/'run.json')!=original['receipts'][mode]:raise ValueError('Changed original control')
        comparisons[mode]=compare_raw(a/'waveform.raw',b/'waveform.raw',[result['logs'][mode]['count'],original['logs'][mode]['count']],20e-6,exact=True)
        if not equal(a/'ngspice.log',b/'ngspice.log',FIRMWARE):raise ValueError('Audit changed firmware')
        audits[mode]=scan(a/'ngspice.log')
    return dict(completed=True,qualified=False,boardAssessment=result,exactOriginalComparisons=comparisons,audits=audits,
                scope='Complete bounded controls with exact samples and firmware versus the retained same-mode drain captures. Does not establish full post-reset equivalence, ADC threshold history, convergence or a correction.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=assess(a.root)
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
