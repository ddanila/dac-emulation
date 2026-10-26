#!/usr/bin/env python3
"""Review private queue observation at bounded board bridge boundaries."""
import argparse,json,math
from pathlib import Path
from audit_log import records,complete,equal
from compare_firmware_io import sha as logical_sha
from private_queue_probe import snapshot
from postreset_startup_review import FIRMWARE
from raw_pair_review import compare_raw
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def inventory(path, *, corrupt=False):
    ordinal=0;boundary=None;stages={};stage=None;lines=[];types=set();fault=None
    events=0;future=0;maximum=0;phases={'before-step':0,'after-step':0}
    for line in records(path,('VQ_',)):
        a=line.split();kind=a[0]
        if kind=='VQ_BRIDGE':
            if boundary is not None or lines or len(a)!=4:raise ValueError('Unfinished bridge boundary')
            index=int(a[1]);target=float(a[3]);phase=('before-step','after-step')[ordinal%2]
            if index!=ordinal or a[2]!=phase or not math.isfinite(target) or target<0:
                raise ValueError('Invalid bridge boundary order/time')
            boundary={'index':index,'phase':phase,'targetSeconds':target};ordinal+=1;phases[phase]+=1;stages={};stage=None
        elif kind=='VQ_STAGE':
            if boundary is None or lines or len(a)!=2 or a[1] in stages or a[1] not in ('before','repeat','changed','restored'):
                raise ValueError('Invalid snapshot stage')
            if stage is not None and stage not in stages:raise ValueError('Missing prior snapshot')
            stage=a[1]
        elif kind=='VQ_BEGIN':
            if boundary is None or stage is None or stage in stages or lines:raise ValueError('Orphan/nested snapshot')
            lines=[line]
        elif kind in ('VQ_TIME','VQ_EVENT','VQ_COUNT','VQ_END'):
            if not lines:raise ValueError('Orphan queue record')
            lines.append(line)
            if kind=='VQ_END':stages[stage]=(lines,snapshot(lines));lines=[]
        elif kind in ('VQ_STABLE','VQ_FAULT'):
            if boundary is None or lines:raise ValueError('Incomplete observation')
            if kind=='VQ_STABLE':
                if line!='VQ_STABLE equal=1' or list(stages)!=['before','repeat'] or stages['before'][0]!=stages['repeat'][0]:
                    raise ValueError('Observer changed queue topology')
            else:
                if not corrupt or fault is not None or line!='VQ_FAULT detected=1 restored=1' or list(stages)!=['before','changed','restored']:
                    raise ValueError('Invalid fault control')
                if stages['before'][0]==stages['changed'][0] or stages['before'][0]!=stages['restored'][0] or boundary['targetSeconds']<5e-6:
                    raise ValueError('Fault not detected/restored at the prescribed boundary')
                fault=dict(boundary)
            measured=stages['before'][1];events+=measured['events'];maximum=max(maximum,measured['events'])
            future+=sum(t>measured['time'] for t in measured['timeSlots']);types.update(map(tuple,measured['eventTypes']))
            boundary=None;stage=None
        else:raise ValueError('Unknown private queue record')
        if fault is not None and kind!='VQ_FAULT':raise ValueError('Unexpected continuation after intentional fault')
    if boundary is not None or lines or not ordinal or (fault is None and ordinal%2):raise ValueError('Incomplete bridge observation')
    return {'boundaries':ordinal,'phases':phases,'queuedEventObservations':events,'maximumQueuedEvents':maximum,
            'futureTimeSlotObservations':future,'eventTypes':[list(t) for t in sorted(types)],'fault':fault}


def assess(root,producer):
    names=('baseline','off','observe','corrupt');runs={n:json.loads((root/n/'run.json').read_text()) for n in names}
    base=runs['baseline'];fixture=HERE/'reports/instance-queue-state/off'
    control=json.loads((HERE/'reports/postreset-startup-fixes/combined/run.json').read_text())
    if base['combinedControlReceiptSha256']!=sha(HERE/'reports/postreset-startup-fixes/combined/run.json'):
        raise ValueError('Changed combined-fix source receipt')
    if base['fixtureReceiptSha256']!=sha(fixture/'run.json') or (root/'baseline/io.cir').read_text()!=(fixture/'io.cir').read_text():
        raise ValueError('Changed bounded board fixture')
    if base['runtime']!=control['runtime'] or base['environment']!=dict(control['environment'],ROBOTRON_PRIVATE_QUEUE='off'):
        raise ValueError('Changed combined-fix baseline')
    def dep(r,name):
        matches=[p for p in r['externalDependencies'] if Path(p['path']).name==name]
        if len(matches)!=1:raise ValueError('Ambiguous bridge dependency')
        return matches[0]['path']
    expected_deck=(root/'baseline/io.cir').read_text()
    for name in ('ivlng.so','libvvp.so'):
        old,new=dep(base,name),dep(runs['off'],name)
        if expected_deck.count(old)!=1 or old==new:raise ValueError('Missing distinct observer runtime')
        expected_deck=expected_deck.replace(old,new)
    scans={};receipts={}
    for mode,r in runs.items():
        folder=root/mode;negative=mode=='corrupt'
        if r['mode']!=mode or r['endSeconds']!=20e-6 or r['producerSha256']!=sha(producer):raise ValueError('Changed capture scope/provenance')
        for key in ('runtime','fixtureReceiptSha256','combinedControlReceiptSha256','bridgeBuildSha256','icarusBuildSha256'):
            if r[key]!=base[key]:raise ValueError('Changed '+key)
        expected=dict(base['environment'],ROBOTRON_PRIVATE_QUEUE='off' if mode=='baseline' else mode)
        if r['environment']!=expected:raise ValueError('Changed capture environment')
        if mode!='baseline' and (folder/'io.cir').read_text()!=expected_deck:raise ValueError('Changed observer circuit')
        if mode in ('observe','corrupt') and r['externalDependencies']!=runs['off']['externalDependencies']:
            raise ValueError('Changed observer libraries')
        if set(r['inputs'])!=set(base['inputs']):raise ValueError('Changed inputs')
        for name,digest in r['inputs'].items():
            if sha(folder/name)!=digest:raise ValueError('Changed input bytes')
            if name!='io.cir' and digest!=base['inputs'][name]:raise ValueError('Changed firmware')
        for name,digest in (('waveform.raw',r['storage']['waveform.raw']['sha256']),('ngspice.log',r['log']['sha256'])):
            if logical_sha(folder/name)!=digest:raise ValueError('Changed retained output')
        if r['exitCode']!=r['log']['exitCode']:raise ValueError('Inconsistent termination')
        if r['expectedExitCode']!=(2 if negative else 0):raise ValueError('Changed termination contract')
        if not negative:
            if not r['completed'] or r.get('error') or r['exitCode']!=0:raise ValueError('Incomplete positive control')
            scans[mode]=complete(folder/'ngspice.log')
            if not scans[mode]['latchesMatch'] or not any(records(folder/'ngspice.log',('FIRST_FETCH ',))):
                raise ValueError('Missing or invalid firmware execution')
        elif r['exitCode'] not in (0,2):raise ValueError('Unexpected fault termination')
        receipts[mode]=sha(folder/'run.json')
    for mode in ('baseline','off'):
        if next(records(root/mode/'ngspice.log',('VQ_',)),None) is not None:raise ValueError('Disabled observer emitted records')
    observed=inventory(root/'observe/ngspice.log');negative=inventory(root/'corrupt/ngspice.log',corrupt=True)
    if bool(negative['fault'])!=(runs['corrupt']['exitCode']==2):raise ValueError('Fault/termination mismatch')
    if not any(records(root/'corrupt/ngspice.log',('FIRST_FETCH ',))):raise ValueError('Fault fixture never reached firmware')
    comparisons={}
    for label,left,right in (('disabledBaseline','baseline','off'),('enabledObserver','off','observe')):
        comparisons[label]=compare_raw(root/left/'waveform.raw',root/right/'waveform.raw',[scans[n]['count'] for n in (left,right)],20e-6,exact=True)
        if not equal(root/left/'ngspice.log',root/right/'ngspice.log',FIRMWARE):raise ValueError('Changed firmware continuation')
    return {'reviewCompleted':True,'qualified':False,'controlsPassed':bool(negative['fault']),
            'comparisons':comparisons,'firmwareRecordsExactlyEqual':True,'observedQueues':observed,'negativeControl':negative,'receipts':receipts,
            'scope':'Complete 20-us fixture with service reset at 1 us; private queue topology at actual HDL step boundaries.',
            'notEstablished':['Event payloads and executing callback/thread state','General rollback or private-state restoration','Full post-reset/startup/repeat/supply recovery qualification']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','producer','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();result=assess(a.root,a.producer)
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
