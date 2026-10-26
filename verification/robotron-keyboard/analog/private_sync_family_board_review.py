#!/usr/bin/env python3
"""Review family-aware callback observation and reused original-runtime baseline at bounded board bridge boundaries."""
import argparse,json,math
from pathlib import Path
from audit_log import records,complete,equal
from compare_firmware_io import sha as logical_sha
from postreset_startup_review import FIRMWARE
from raw_pair_review import compare_raw
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


from private_sync_family_probe import snapshot


def function_symbols(text):
    result={}
    for line in text.splitlines():
        fields=line.split()
        if len(fields)!=3 or fields[1] not in ('t','T'):continue
        name=fields[2][1:] if fields[2].startswith('_') else fields[2]
        if name not in ('next_advance_cb','strobe_cb','monitor_cb_2'):continue
        if name in result:raise ValueError('Ambiguous callback symbol')
        result[name]=int(fields[0],16)
    return result


def verify_symbols(root,runs):
    identities=json.loads((root/'symbols.json').read_text())
    if set(identities)!={'ivlng.vpi','system.vpi'}:raise ValueError('Missing module identities')
    dependencies={d['path']:d['sha256'] for d in runs['off']['externalDependencies']}
    for name,e in identities.items():
        if Path(e['path']).name!=name or dependencies.get(e['path'])!=e['sha256']:raise ValueError('Unpinned callback module')
        if function_symbols((root/(name+'.nm')).read_text())!=e['symbols']:raise ValueError('Changed function symbol evidence')
        required='next_advance_cb' if name=='ivlng.vpi' else 'strobe_cb'
        if required not in e['symbols']:raise ValueError('Missing callback function symbol')
    return identities


def family(item,identities):
    code=item['code'];values=item['values']
    module=Path(code['module']).name
    if module not in identities or code['module']!=identities[module]['path']:raise ValueError('Unidentified loaded module')
    expected='next_advance_cb' if module=='ivlng.vpi' else 'strobe_cb'
    if code['offset']!=identities[module]['symbols'][expected]:raise ValueError('Unidentified loaded callback')
    bridge=expected=='next_advance_cb'
    if values[6]!=int(bridge) or values[3] not in ((6,9) if bridge else (7,)):
        raise ValueError('Callback family/header mismatch')
    if values[2]!=int(not bridge):raise ValueError('Unexpected normal synchronization mode')
    return expected


def inventory(path,identities, *, corrupt=False):
    ordinal=0;boundary=None;stages={};stage=None;lines=[];fault=None
    observed=executing=canceled=maximum=0;families={'next_advance_cb':0,'strobe_cb':0};phases={'before-step':0,'after-step':0}
    for line in records(path,('VF_',)):
        a=line.split();kind=a[0]
        if kind=='VF_BRIDGE':
            if boundary is not None or lines or len(a)!=4:raise ValueError('Unfinished bridge boundary')
            index=int(a[1]);target=float(a[3]);phase=('before-step','after-step')[ordinal%2]
            if index!=ordinal or a[2]!=phase or not math.isfinite(target) or target<0:raise ValueError('Invalid boundary order/time')
            boundary={'index':index,'phase':phase,'targetSeconds':target};ordinal+=1;phases[phase]+=1;stages={};stage=None
        elif kind=='VF_STAGE':
            if boundary is None or lines or len(a)!=2 or a[1] in stages or a[1] not in ('before','repeat','changed','restored'):
                raise ValueError('Invalid snapshot stage')
            if stage is not None and stage not in stages:raise ValueError('Missing prior snapshot')
            stage=a[1]
        elif kind=='VF_BEGIN':
            if boundary is None or stage is None or stage in stages or lines:raise ValueError('Orphan/nested snapshot')
            lines=[line]
        elif kind in ('VF_CB','VF_CODE','VF_END'):
            if not lines:raise ValueError('Orphan callback record')
            lines.append(line)
            if kind=='VF_END':stages[stage]=(lines,snapshot(lines));lines=[]
        elif kind in ('VF_STABLE','VF_FAULT'):
            if boundary is None or lines:raise ValueError('Incomplete observation')
            if kind=='VF_STABLE':
                if line!='VF_STABLE equal=1' or list(stages)!=['before','repeat'] or stages['before'][0]!=stages['repeat'][0]:
                    raise ValueError('Observer changed callback state')
            else:
                if not corrupt or fault is not None or line!='VF_FAULT detected=1 restored=1' or list(stages)!=['before','changed','restored']:
                    raise ValueError('Invalid fault control')
                before=stages['before'][1];after=stages['changed'][1]
                if before==after or before!=stages['restored'][1] or boundary['targetSeconds']<5e-6:raise ValueError('Fault not detected/restored')
                if before['time']!=after['time'] or before['mode']!=after['mode'] or len(before['callbacks'])!=len(after['callbacks']):raise ValueError('Unrelated scheduler mutation')
                changes=[(a,b) for a,b in zip(before['callbacks'],after['callbacks']) if a!=b]
                if len(changes)!=1:raise ValueError('Wrong mutation count')
                a,b=changes[0];av=a['values'];bv=b['values']
                if av[1] or not av[4] or av[:2]+av[3:]!=bv[:2]+bv[3:] or av[2]==bv[2] or a['code']!=b['code']:raise ValueError('Wrong mutation target')
                fault=dict(boundary)
            state=stages['before'][1];items=state['callbacks'];observed+=len(items);maximum=max(maximum,len(items))
            for item in items:
                families[family(item,identities)]+=1;v=item['values'];executing+=v[1];canceled+=int(not v[4])
            boundary=None;stage=None
        else:raise ValueError('Unknown family observer record')
        if fault is not None and kind!='VF_FAULT':raise ValueError('Unexpected continuation after fault')
    if boundary is not None or lines or not ordinal or (fault is None and ordinal%2):raise ValueError('Incomplete bridge observation')
    if not executing or not all(families.values()):raise ValueError('Missing executing/display callback coverage')
    return {'boundaries':ordinal,'phases':phases,'liveCallbackObservations':observed,'maximumLiveCallbacks':maximum,
            'executingCallbackObservations':executing,'canceledCallbackObservations':canceled,'functionObservations':families,
            'functionIdentityEstablished':True,'displayReferentsObserved':False,'payloadCoverageComplete':False,'fault':fault}


def assess(root,producer):
    names=('baseline','off','observe','corrupt');runs={n:json.loads((root/n/'run.json').read_text()) for n in names}
    identities=verify_symbols(root,runs)
    origin=json.loads((root/'baseline-origin.json').read_text())
    if origin['receiptSha256']!=sha(root/'baseline/run.json') or origin['producerSha256']!=sha(root/'baseline-producer.py'):
        raise ValueError('Changed reused baseline provenance')
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
    replaced={'ivlng.so','ivlng.vpi','libvvp.so'}
    def shared(r):return {d['path']:d['sha256'] for d in r['externalDependencies'] if Path(d['path']).name not in replaced}
    if shared(base)!=shared(runs['off']):raise ValueError('Changed non-candidate runtime dependencies')
    expected_deck=(root/'baseline/io.cir').read_text()
    for name in ('ivlng.so','libvvp.so','ivlng.vpi'):
        old,new=dep(base,name),dep(runs['off'],name)
        if expected_deck.count(old)!=1 or old==new:raise ValueError('Missing distinct observer runtime')
        expected_deck=expected_deck.replace(old,new)
    scans={};receipts={}
    for mode,r in runs.items():
        folder=root/mode;negative=mode=='corrupt'
        if r['mode']!=mode or r['endSeconds']!=20e-6 or r['producerSha256']!=sha(root/'baseline-producer.py' if mode=='baseline' else producer):raise ValueError('Changed capture scope/provenance')
        for key in ('runtime','fixtureReceiptSha256','combinedControlReceiptSha256'):
            if r[key]!=base[key]:raise ValueError('Changed '+key)
        if mode!='baseline':
            for key in ('bridgeBuildSha256','icarusBuildSha256'):
                if r[key]!=runs['off'][key]:raise ValueError('Changed candidate build')
            if r['symbolReceiptSha256']!=sha(root/'symbols.json'):raise ValueError('Changed callback module evidence')
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
        if next(records(root/mode/'ngspice.log',('VF_',)),None) is not None:raise ValueError('Disabled observer emitted records')
    observed=inventory(root/'observe/ngspice.log',identities);negative=inventory(root/'corrupt/ngspice.log',identities,corrupt=True)
    if bool(negative['fault'])!=(runs['corrupt']['exitCode']==2):raise ValueError('Fault/termination mismatch')
    if not any(records(root/'corrupt/ngspice.log',('FIRST_FETCH ',))):raise ValueError('Fault fixture never reached firmware')
    comparisons={}
    for label,left,right in (('disabledBaseline','baseline','off'),('enabledObserver','off','observe')):
        comparisons[label]=compare_raw(root/left/'waveform.raw',root/right/'waveform.raw',[scans[n]['count'] for n in (left,right)],20e-6,exact=True)
        if not equal(root/left/'ngspice.log',root/right/'ngspice.log',FIRMWARE):raise ValueError('Changed firmware continuation')
    return {'reviewCompleted':True,'qualified':False,'controlsPassed':bool(negative['fault']),
            'comparisons':comparisons,'firmwareRecordsExactlyEqual':True,'observedCallbacks':observed,'negativeControl':negative,'receipts':receipts,'baselineReused':True,'payloadCoverageComplete':False,
            'scope':'Complete 20-us fixture with service reset at 1 us; Family-aware synchronization callback observation at actual HDL step boundaries; stop and display functions are identified against pinned module symbols. Display data remains unobserved.',
            'notEstablished':['Display and bridge callback referenced-data contents','Initial start callback, executing stack/wrapper and other event payloads','General rollback or private-state restoration','Full post-reset/startup/repeat/supply recovery qualification']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','producer','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();result=assess(a.root,a.producer)
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
