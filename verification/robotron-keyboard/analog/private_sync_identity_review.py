#!/usr/bin/env python3
"""Review explicitly identified synchronization callback headers at bounded board bridge boundaries."""
import argparse,json,math
from pathlib import Path
from audit_log import records,complete,equal
from compare_firmware_io import sha as logical_sha
from postreset_startup_review import FIRMWARE
from raw_pair_review import compare_raw
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def snapshot(lines):
    begin=lines[0].split()
    if len(begin)!=5 or begin[:2]!=['VS_BEGIN','1'] or lines[-1]!='VS_END':raise ValueError('Invalid snapshot framing')
    now,mode,count=map(int,begin[2:]);items=[]
    if now<0 or mode not in range(6) or count<0:raise ValueError('Invalid scheduler header')
    for line in lines[1:-1]:
        a=line.split()
        if len(a)!=18 or a[0]!='VS_CALLBACK':raise ValueError('Invalid callback record')
        values=list(map(int,a[1:-1]));real=float.fromhex(a[-1])
        ident,executing,sync,reason,index,active,function,user,obj,value,nxt,back,timeptr,typ,high,low=values
        if ident<1 or (items and ident<=items[-1][0]):raise ValueError('Invalid lifetime ordering')
        if any(x not in (0,1) for x in (executing,sync,active,function,user,obj,value,nxt,back,timeptr)):
            raise ValueError('Invalid callback flags')
        # The separate VPI registers next_advance_cb explicitly before the
        # initial callback can yield. Active callbacks must match that identity;
        # canceled callbacks cannot match a non-null function.
        if function!=active or not all((user,obj,value,nxt,back,timeptr)):
            raise ValueError('Uncovered callback identity/referent shape')
        if reason not in (6,9) or index!=0 or typ!=2 or not 0<=high<2**32 or not 0<=low<2**32 or real!=0:
            raise ValueError('Unexpected board callback payload')
        if executing and not active:raise ValueError('Canceled executing callback')
        items.append(values)
    if len(items)!=count or sum(x[1] for x in items)>1:raise ValueError('Incomplete live callback registry')
    if any(x[1] for x in items) and mode not in (4,5):raise ValueError('Executing callback lacks synchronization mode')
    return {'time':now,'mode':mode,'callbacks':items}


def inventory(path, *, corrupt=False):
    ordinal=0;boundary=None;stages={};stage=None;lines=[];fault=None
    observed=executing=canceled=maximum=0;reasons=set();phases={'before-step':0,'after-step':0}
    for line in records(path,('VS_',)):
        a=line.split();kind=a[0]
        if kind=='VS_BRIDGE':
            if boundary is not None or lines or len(a)!=4:raise ValueError('Unfinished bridge boundary')
            index=int(a[1]);target=float(a[3]);phase=('before-step','after-step')[ordinal%2]
            if index!=ordinal or a[2]!=phase or not math.isfinite(target) or target<0:raise ValueError('Invalid boundary order/time')
            boundary={'index':index,'phase':phase,'targetSeconds':target};ordinal+=1;phases[phase]+=1;stages={};stage=None
        elif kind=='VS_STAGE':
            if boundary is None or lines or len(a)!=2 or a[1] in stages or a[1] not in ('before','repeat','changed','restored'):
                raise ValueError('Invalid snapshot stage')
            if stage is not None and stage not in stages:raise ValueError('Missing prior snapshot')
            stage=a[1]
        elif kind=='VS_BEGIN':
            if boundary is None or stage is None or stage in stages or lines:raise ValueError('Orphan/nested snapshot')
            lines=[line]
        elif kind in ('VS_CALLBACK','VS_END'):
            if not lines:raise ValueError('Orphan callback record')
            lines.append(line)
            if kind=='VS_END':stages[stage]=(lines,snapshot(lines));lines=[]
        elif kind in ('VS_STABLE','VS_FAULT'):
            if boundary is None or lines:raise ValueError('Incomplete observation')
            if kind=='VS_STABLE':
                if line!='VS_STABLE equal=1' or list(stages)!=['before','repeat'] or stages['before'][0]!=stages['repeat'][0]:
                    raise ValueError('Observer changed callback state')
            else:
                if not corrupt or fault is not None or line!='VS_FAULT detected=1 restored=1' or list(stages)!=['before','changed','restored']:
                    raise ValueError('Invalid fault control')
                before=stages['before'][1];after=stages['changed'][1]
                if before==after or before!=stages['restored'][1] or boundary['targetSeconds']<5e-6:
                    raise ValueError('Fault not detected/restored at prescribed boundary')
                if before['time']!=after['time'] or before['mode']!=after['mode'] or len(before['callbacks'])!=len(after['callbacks']):
                    raise ValueError('Fault changed unrelated scheduler state')
                changes=[(a,b) for a,b in zip(before['callbacks'],after['callbacks']) if a!=b]
                if len(changes)!=1:raise ValueError('Wrong mutation count')
                a,b=changes[0]
                if a[1] or not a[5] or a[:2]+a[3:]!=b[:2]+b[3:] or a[2]==b[2]:raise ValueError('Wrong mutation target')
                fault=dict(boundary)
            state=stages['before'][1];items=state['callbacks'];observed+=len(items);maximum=max(maximum,len(items))
            executing+=sum(x[1] for x in items);canceled+=sum(not x[5] for x in items);reasons.update(x[3] for x in items)
            boundary=None;stage=None
        else:raise ValueError('Unknown private callback record')
        if fault is not None and kind!='VS_FAULT':raise ValueError('Unexpected continuation after fault')
    if boundary is not None or lines or not ordinal or (fault is None and ordinal%2):raise ValueError('Incomplete bridge observation')
    if not executing:raise ValueError('No executing callback observations')
    return {'boundaries':ordinal,'phases':phases,'liveCallbackObservations':observed,'maximumLiveCallbacks':maximum,
            'executingCallbackObservations':executing,'canceledCallbackObservations':canceled,'reasons':sorted(reasons),
            'functionIdentityEstablished':True,'fault':fault}


def assess(root,producer):
    names=('baseline','off','observe','corrupt');runs={n:json.loads((root/n/'run.json').read_text()) for n in names}
    base=runs['baseline'];fixture=HERE/'reports/instance-queue-state/off'
    control=json.loads((HERE/'reports/postreset-startup-fixes/combined/run.json').read_text())
    if base['combinedControlReceiptSha256']!=sha(HERE/'reports/postreset-startup-fixes/combined/run.json'):
        raise ValueError('Changed combined-fix source receipt')
    if base['fixtureReceiptSha256']!=sha(fixture/'run.json') or (root/'baseline/io.cir').read_text()!=(fixture/'io.cir').read_text():
        raise ValueError('Changed bounded board fixture')
    if base['runtime']!=control['runtime'] or base['environment']!=dict(control['environment'],ROBOTRON_PRIVATE_SYNC='off'):
        raise ValueError('Changed combined-fix baseline')
    def dep(r,name):
        matches=[p for p in r['externalDependencies'] if Path(p['path']).name==name]
        if len(matches)!=1:raise ValueError('Ambiguous bridge dependency')
        return matches[0]['path']
    expected_deck=(root/'baseline/io.cir').read_text()
    for name in ('ivlng.so','libvvp.so','ivlng.vpi'):
        old,new=dep(base,name),dep(runs['off'],name)
        if expected_deck.count(old)!=1 or old==new:raise ValueError('Missing distinct observer runtime')
        expected_deck=expected_deck.replace(old,new)
    scans={};receipts={}
    for mode,r in runs.items():
        folder=root/mode;negative=mode=='corrupt'
        if r['mode']!=mode or r['endSeconds']!=20e-6 or r['producerSha256']!=sha(producer):raise ValueError('Changed capture scope/provenance')
        for key in ('runtime','fixtureReceiptSha256','combinedControlReceiptSha256','bridgeBuildSha256','icarusBuildSha256'):
            if r[key]!=base[key]:raise ValueError('Changed '+key)
        expected=dict(base['environment'],ROBOTRON_PRIVATE_SYNC='off' if mode=='baseline' else mode)
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
        if next(records(root/mode/'ngspice.log',('VS_',)),None) is not None:raise ValueError('Disabled observer emitted records')
    observed=inventory(root/'observe/ngspice.log');negative=inventory(root/'corrupt/ngspice.log',corrupt=True)
    if bool(negative['fault'])!=(runs['corrupt']['exitCode']==2):raise ValueError('Fault/termination mismatch')
    if not any(records(root/'corrupt/ngspice.log',('FIRST_FETCH ',))):raise ValueError('Fault fixture never reached firmware')
    comparisons={}
    for label,left,right in (('disabledBaseline','baseline','off'),('enabledObserver','off','observe')):
        comparisons[label]=compare_raw(root/left/'waveform.raw',root/right/'waveform.raw',[scans[n]['count'] for n in (left,right)],20e-6,exact=True)
        if not equal(root/left/'ngspice.log',root/right/'ngspice.log',FIRMWARE):raise ValueError('Changed firmware continuation')
    return {'reviewCompleted':True,'qualified':False,'controlsPassed':bool(negative['fault']),
            'comparisons':comparisons,'firmwareRecordsExactlyEqual':True,'observedCallbacks':observed,'negativeControl':negative,'receipts':receipts,
            'scope':'Complete 20-us fixture with service reset at 1 us; live synchronization callback headers at actual HDL step boundaries; function identity is checked against the explicit VPI handoff.',
            'notEstablished':['Callback referenced-data contents','Initial start callback, executing stack/wrapper and other event payloads','General rollback or private-state restoration','Full post-reset/startup/repeat/supply recovery qualification']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','producer','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();result=assess(a.root,a.producer)
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
