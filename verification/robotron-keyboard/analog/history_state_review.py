#!/usr/bin/env python3
"""Review bounded live XSPICE history coverage and observer non-interference."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
from audit_log import scan, equal
from compare_firmware_io import sha as logical_sha
from raw_pair_review import compare_raw
from trace_io import open_text
from ttl7406_probe import sha

PHASES={'callback-entry','event-after','run-entry','advance-before','advance-after','output-before','output-after'}


def snapshots(path, stats, *, corrupt=False):
    active=None;phases=Counter();rejections=0;detected=0;output=None;advance=None;dimensions=None
    with open_text(path) as stream:
        for line in stream:
            fields=line.split()
            if not fields:continue
            kind=fields[0]
            if kind=='H_BEGIN':
                if active is not None or len(fields)!=3 or fields[1] not in PHASES:raise ValueError('Malformed history entry')
                time=float(fields[2])
                if not math.isfinite(time) or time<=0:raise ValueError('Invalid initialized history time')
                active={'phase':fields[1],'time':time,'arrays':{},'queue':[]};phases[fields[1]]+=1
            elif kind=='H_SCHED':
                if active is None or 'scheduler' in active or len(fields)!=6:raise ValueError('Malformed scheduler state')
                values=tuple(float.fromhex(v) for v in fields[1:4]);index,pending=map(int,fields[4:])
                if not all(map(math.isfinite,values)) or index < -1 or pending not in (0,1):raise ValueError('Invalid scheduler state')
                active['scheduler']=values+(index,pending)
            elif kind=='H_QUEUE':
                if active is None or len(fields)!=6:raise ValueError('Malformed input queue')
                if int(fields[1])!=len(active['queue']) or not math.isfinite(float.fromhex(fields[2])):raise ValueError('Invalid queue entry')
                active['queue'].append((float.fromhex(fields[2]),*map(int,fields[3:])))
            elif kind in ('H_ARRAY','H_PENDING'):
                if active is None:raise ValueError('Orphan history array')
                if kind=='H_ARRAY':
                    tag,previous,count=map(int,fields[1:4]);key=(tag,previous);values=fields[4:]
                    if key not in ((0,0),(0,1),(1,0),(1,1)) or key in active['arrays']:raise ValueError('Invalid history key')
                else:
                    if 'pending' in active:raise ValueError('Duplicate pending buffer')
                    count=int(fields[1]);values=fields[2:]
                if count<0 or len(values)!=count:raise ValueError('Incomplete history array')
                parsed=tuple(tuple(map(int,v.split(':'))) for v in values)
                if any(len(v)!=2 for v in parsed):raise ValueError('Invalid Digital_t value')
                if kind=='H_ARRAY':active['arrays'][key]=parsed
                else:active['pending']=parsed
            elif kind=='H_END':
                if active is None or 'scheduler' not in active or 'pending' not in active or len(active['arrays'])!=4:raise ValueError('Incomplete history snapshot')
                a=active['arrays'];dims=(len(a[0,0]),len(a[1,0]))
                if len(a[0,1])!=dims[0] or len(a[1,1])!=dims[1] or (dimensions is not None and dimensions!=dims):raise ValueError('Changed history dimensions')
                dimensions=dims
                if len(active['queue'])!=active['scheduler'][3]+1:raise ValueError('Incomplete queue')
                if len(active['pending'])!=(dims[1] if active['scheduler'][4] else 0):raise ValueError('Invalid pending validity')
                if advance is not None:
                    if active['phase']!='advance-after' or active['time']!=advance['time']:raise ValueError('Missing advance completion')
                    advance=None
                elif active['phase']=='advance-after':raise ValueError('Orphan advance completion')
                if active['phase']=='advance-before':advance=active
                if output is not None:
                    if active['phase']!='output-after' or active['time']!=output['time'] or active['scheduler'][4]!=0:raise ValueError('Missing output completion')
                    if a[1,0]!=output['pending'] or a[0,0]!=output['arrays'][0,0] or a[0,1]!=output['arrays'][0,1]:raise ValueError('Output publication differs from pending buffer')
                    output=None
                elif active['phase']=='output-after':raise ValueError('Orphan output completion')
                if active['phase']=='output-before':
                    if not active['scheduler'][4]:raise ValueError('Output without pending buffer')
                    output=active
                yield active;active=None
            elif kind=='H_REJECT':
                if active is not None or len(fields)!=3 or fields[2] not in ('equal=0','equal=1'):raise ValueError('Malformed rejection')
                rejection_time=float(fields[1])
                if not math.isfinite(rejection_time) or rejection_time<=0:raise ValueError('Invalid rejection time')
                if fields[2]=='equal=0':
                    if not corrupt:raise ValueError('Rejected trial changed history')
                    detected+=1
                rejections+=1
            elif kind.startswith('H_'):raise ValueError('Unknown history record')
    if active is not None or output is not None or advance is not None:raise ValueError('Truncated history trace')
    if not corrupt and (set(phases)!=PHASES or not rejections):raise ValueError('Missing history path coverage')
    if corrupt and detected!=1:raise ValueError('Missing corruption control')
    stats.update(phases=dict(phases),rejections=rejections,corruptionsDetected=detected,dimensions=dimensions)


def assess(root, baseline):
    runs={m:json.loads((root/m/'run.json').read_text()) for m in ('off','check','corrupt')}
    for mode,r in runs.items():
        if r['exitCode']!=(2 if mode=='corrupt' else 0):raise ValueError('Unexpected exit')
        if r['inputs']!=runs['off']['inputs'] or r['runtime']!=runs['off']['runtime']:raise ValueError('Different producer conditions')
        env=dict(runs['off']['environment'],ROBOTRON_HISTORY_STATE=mode)
        if env!=r['environment']:raise ValueError('Different experimental environment')
        for name,digest in r['inputs'].items():
            if sha(root/mode/name)!=digest:raise ValueError('Changed input')
        for name,item in r['storage'].items():
            if logical_sha(root/mode/name)!=item['sha256']:raise ValueError('Changed capture')
    reference=json.loads((baseline/'run.json').read_text())
    if reference['inputs']!=runs['off']['inputs']:raise ValueError('Different prior baseline inputs')
    for name,digest in reference['inputs'].items():
        if sha(baseline/name)!=digest:raise ValueError('Changed baseline input')
    for name,item in reference['storage'].items():
        if logical_sha(baseline/name)!=item['sha256']:raise ValueError('Changed baseline capture')
    with open_text(root/'off/ngspice.log') as stream:
        if any(line.startswith('H_') for line in stream):raise ValueError('Disabled observer emitted history')
    stats={};negative={}
    for _ in snapshots(root/'check/ngspice.log',stats):pass
    for _ in snapshots(root/'corrupt/ngspice.log',negative,corrupt=True):pass
    with open_text(root/'corrupt/ngspice.log') as stream:
        if not any('Rejected trial changed XSPICE history' in line for line in stream):raise ValueError('Missing negative diagnostic')
    counts=[]
    for path in (root/'off',root/'check',baseline):
        record=scan(path/'ngspice.log')
        if record['diagnostic'] or record['sorry'] or record['count'] is None:raise ValueError('Incomplete positive control')
        counts.append(record['count'])
    prefix=('FIRST_FETCH ','BUS_','SERIAL_')
    if not equal(root/'off/ngspice.log',root/'check/ngspice.log',prefix) or not equal(root/'off/ngspice.log',baseline/'ngspice.log',prefix):raise ValueError('Changed firmware continuation')
    comparisons=[compare_raw(root/'off/waveform.raw',root/'check/waveform.raw',counts[:2],20e-6,exact=True),
                 compare_raw(root/'off/waveform.raw',baseline/'waveform.raw',[counts[0],counts[2]],20e-6,exact=True)]
    return {'history':stats,'negativeControl':negative,'waveformComparisons':comparisons,'qualified':False,
            'baseline':{'path':str(baseline),'receiptSha256':sha(baseline/'run.json')},
            'scope':'Initialized callback/history observation and input-barrier equality in the bounded 20-us observer fixture. Exact disabled/enabled/prior waveform and firmware continuation; corruption changes actual input history and is detected.',
            'notEstablished':['Initialization histories','Complete pending HDL events','Output delay/changed flags and downstream scheduled events','General rollback and full required scenarios','Independent physical-model admission']}


def check(root):
    manifest=json.loads((root/'manifest.json').read_text())
    files={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and p.name!='manifest.json'}
    if files!=manifest['files']:raise ValueError('Changed history evidence')
    for name,digest in manifest['sources'].items():
        if sha(Path(__file__).parent/name)!=digest:raise ValueError('Changed history source')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--baseline',type=Path);p.add_argument('--check-manifest',action='store_true');a=p.parse_args()
    if a.check_manifest:check(a.root)
    else:
        if not a.baseline:p.error('Need --baseline')
        result=assess(a.root,a.baseline);(a.root/'assessment.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
