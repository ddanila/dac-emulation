#!/usr/bin/env python3
"""Verify accumulated output flags and initial LED events in bounded live controls."""
import argparse
import json
from pathlib import Path
import re
from audit_log import equal
from filter_truncation_log import diagnostic
from compare_firmware_io import sha as logical_sha
from event_state_review import scheduling
from history_state_review import snapshots
from raw_pair_review import compare_raw
from staged_output_capture import VARIANTS
from test_staged_output import probe
from trace_io import open_text
from ttl7406_probe import sha



STATE_RECORDS=('H_BEGIN ','H_SCHED ','H_QUEUE ','H_ARRAY ','H_PENDING ','H_END\n','H_REJECT ','E_SUM ','E_PORT ','E_ITEM ')
def runtime_summary(path):
    # Both telemetry streams receive their own structural review below. Avoid
    # applying unrelated solver-message regexes to millions of typed records.
    counts=[];failure=None;sorry=False
    with open_text(path) as stream:
        for line in stream:
            if line.startswith(STATE_RECORDS):continue
            if line.startswith('E_CORRUPT '):raise ValueError('Unexpected corruption in positive control')
            failure=failure or diagnostic(line);sorry=sorry or 'SORRY:' in line
            counts.extend(map(int,re.findall(r'No\. of Data Rows\s*:\s*(\d+)',line)))
            if len(counts)>1:raise ValueError('Multiple completion counts')
    return {'count':counts[0] if counts else None,'diagnostic':failure,'sorry':sorry}


def led_indices(log,deck):
    match=re.findall(r'^Ahdl \[.*?\] \[(.*?)\] hdl$',deck,re.M)
    if len(match)!=1:raise ValueError('Ambiguous controller connection')
    names=match[0].split();result={}
    with open_text(log) as stream:
        for line in stream:
            if line.startswith('E_PORT '):
                a=line.split()
                if a[1]=='1' and names[int(a[2])] in ('led0','led1'):result[names[int(a[2])]]=int(a[3])
            if line=='H_END\n':break
    if set(result)!= {'led0','led1'}:raise ValueError('Missing LED port identities')
    return result


def watch(log,expected):
    found=set();indices={key[0] for key in expected}
    with open_text(log) as stream:
        for line in stream:
            if not line.startswith('E_ITEM '):continue
            a=line.split()
            if int(a[1]) not in indices:continue
            key=(int(a[1]),float.fromhex(a[3]),int(a[7]),int(a[8]))
            if a[5]=='0' and key in expected:found.add(key)
    return found



def startup_stages(log,indices):
    callback=0;active=None;stages=[]
    with open_text(log) as stream:
        for line in stream:
            a=line.split()
            if not a:continue
            if a[:2]==['H_BEGIN','callback-entry']:callback+=1
            if a[:2]==['H_BEGIN','output-after']:active={'callback':callback,'time':float(a[2]),'leds':{}}
            elif active is not None and a[:3]==['H_ARRAY','1','0']:active['values']=[tuple(map(int,v.split(':'))) for v in a[4:]]
            elif active is not None and a[0]=='E_PORT' and int(a[3]) in indices.values():
                active['leds'][int(a[3])]={'changed':int(a[4]),'historyValue':active['values'][int(a[2])]}
            elif active is not None and a[0]=='H_END':
                del active['values'];stages.append(active);active=None
                if len(stages)==2:break
    if len(stages)!=2 or stages[0]['callback']!=stages[1]['callback'] or stages[0]['time']!=stages[1]['time'] or any(set(p['leds'])!=set(indices.values()) for p in stages):raise ValueError('Missing repeated startup staging within one callback')
    return stages


def assess(root,baseline,original):
    base=json.loads((baseline/'run.json').read_text());runs={m:json.loads((root/m/'run.json').read_text()) for m in VARIANTS};scans={}
    for mode,r in list(runs.items())+[('baseline',base)]:
        folder=baseline if mode=='baseline' else root/mode
        if r['exitCode']!=0 or r['inputs']!=base['inputs']:raise ValueError('Incomplete or mismatched control')
        for name,digest in r['inputs'].items():
            if sha(folder/name)!=digest:raise ValueError('Changed input')
        for name,item in r['storage'].items():
            if logical_sha(folder/name)!=item['sha256']:raise ValueError('Changed captured stream')
        if mode!='baseline' and (r['runtime']!=runs['off']['runtime'] or r['environment']!=dict(base['environment'],**VARIANTS[mode])):raise ValueError('Mismatched runtime conditions')
        scans[mode]=runtime_summary(folder/'ngspice.log')
        if scans[mode]['count'] is None or scans[mode]['diagnostic'] or scans[mode]['sorry']:raise ValueError('Invalid complete control')
    comparisons={}
    for label,left,right in [('disabledObserver','off','observe'),('fixedObserver','fixed','fixed-observe'),('disabledBaseline','off','baseline')]:
        folders=[baseline if m=='baseline' else root/m for m in (left,right)]
        comparisons[label]=compare_raw(*(p/'waveform.raw' for p in folders),[scans[left]['count'],scans[right]['count']],20e-6,exact=True)
    for mode in VARIANTS:
        if not equal(root/'off/ngspice.log',root/mode/'ngspice.log',('FIRST_FETCH ','BUS_','SERIAL_')):raise ValueError('Changed firmware continuation')
    if not equal(root/'off/ngspice.log',baseline/'ngspice.log',('FIRST_FETCH ','BUS_','SERIAL_')):raise ValueError('Changed baseline firmware')
    difference=compare_raw(root/'off/waveform.raw',root/'fixed/waveform.raw',[scans['off']['count'],scans['fixed']['count']],20e-6)
    histories={}
    for mode in ('observe','fixed-observe'):
        stats={}
        for _ in snapshots(root/mode/'ngspice.log',stats):pass
        histories[mode]=stats
    prior=json.loads(original.read_text())
    indices=led_indices(root/'observe/ngspice.log',(root/'observe/io.cir').read_text())
    if led_indices(root/'fixed-observe/ngspice.log',(root/'fixed-observe/io.cir').read_text())!=indices:raise ValueError('Changed LED mapping')
    expected={(p['outputIndex'],p['scheduledTime'],p['state'],p['strength']) for p in prior['scheduling']['unwitnessedPublications'] if p['outputIndex'] in indices.values()}
    if len(expected)!=2 or any(key[2:]!=(2,0) for key in expected):raise ValueError('Missing original unknown LED requests')
    stages={m:startup_stages(root/m/'ngspice.log',indices) for m in ('observe','fixed-observe')}
    for mode,phases in stages.items():
        for index in indices.values():
            if any(p['leds'][index]['historyValue']!=(2,0) for p in phases) or phases[0]['leds'][index]['changed']!=1 or phases[1]['leds'][index]['changed']!=int(mode=='fixed-observe'):raise ValueError('Startup flag transition does not match the failure/fix')
    old=watch(root/'observe/ngspice.log',expected);fixed=watch(root/'fixed-observe/ngspice.log',expected)
    if old or fixed!=expected:raise ValueError('Did not reproduce and repair missing initial LED events')
    original_scheduling=scheduling(root/'observe/ngspice.log')
    result=scheduling(root/'fixed-observe/ngspice.log')
    unit=probe()
    if unit!='0 1':raise ValueError('Staging/reset probe failed')
    return {'waveformComparisons':comparisons,'candidateWaveformDifference':difference,
            'sampleCounts':{m:s['count'] for m,s in scans.items()},'historyControls':histories,
            'originalScheduling':original_scheduling,'fixedScheduling':result,
            'startupStaging':stages,
            'initialLedEvents':{'indices':indices,'originalObserved':len(old),'fixedObserved':len(fixed),
                                'events':[{'outputIndex':i,'scheduledTime':t,'state':s,'strength':v} for i,t,s,v in sorted(expected)]},
            'partialOutputProbe':unit,'originalAssessmentSha256':sha(original),'qualified':False,
            'scope':'Opt-in accumulation of output flags within one callback, reset at the next callback. Repairs the two initial unknown LED events in the bounded fixture; Observer on/off waveforms remain exact within each variant and firmware events remain exact across variants. The corrected LED DAC inputs change the sampling grid and electrical waveforms; their complete differences are retained, not treated as convergence qualification.',
            'notEstablished':['All startup and firmware scenarios','Private HDL or other-model event queues','Full-repeat, numerical convergence and physical-model admission']}


def check(root):
    manifest=json.loads((root/'manifest.json').read_text())
    files={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and p.name!='manifest.json'}
    if files!=manifest['files']:raise ValueError('Changed staging evidence')
    for name,digest in manifest['sources'].items():
        if sha(Path(__file__).parent/name)!=digest:raise ValueError('Changed staging source')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--baseline',type=Path);p.add_argument('--original',type=Path);p.add_argument('--check-manifest',action='store_true');a=p.parse_args()
    if a.check_manifest:check(a.root)
    else:
        if not a.baseline or not a.original:p.error('Need baseline and original observer assessment')
        result=assess(a.root,a.baseline,a.original);(a.root/'assessment.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
