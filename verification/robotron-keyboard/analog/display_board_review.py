#!/usr/bin/env python3
"""Review typed display/callback links at paused board boundaries."""
import argparse,json,math
from pathlib import Path
from audit_log import records,complete,equal
from compare_firmware_io import sha as logical_sha
from postreset_startup_review import FIRMWARE
from raw_pair_review import compare_raw
from ttl7406_probe import sha
from private_sync_family_probe import snapshot as callback_snapshot
from display_payload_probe import snapshot as payload_snapshot
from private_sync_family_board_review import verify_symbols,family
HERE=Path(__file__).resolve().parent


def bundle(lines,identities):
    if lines[0]!='VA_BEGIN' or lines[-1]!='VA_END':raise ValueError('Invalid board bundle')
    cursor=1;sections={}
    for prefix in ('VF','VD','VJ'):
        if not lines[cursor].startswith(prefix+'_BEGIN '):raise ValueError('Missing board section')
        end=lines.index(prefix+'_END',cursor);sections[prefix]=lines[cursor:end+1];cursor=end+1
    if cursor!=len(lines)-1:raise ValueError('Unexpected board section')
    callbacks=callback_snapshot(sections['VF']);payload=payload_snapshot(sections['VD']);links={}
    h=sections['VJ'][0].split()
    if len(h)!=3 or h[:2]!=['VJ_BEGIN','1']:raise ValueError('Invalid link header')
    for line in sections['VJ'][1:-1]:
        a=line.split()
        if len(a)!=3 or a[0]!='VJ_LINK':raise ValueError('Invalid link record')
        owner,callback=map(int,a[1:])
        if owner<1 or callback<1 or owner in links or callback in links.values():raise ValueError('Aliased display link')
        links[owner]=callback
    if int(h[2])!=len(links) or set(links)!={o['id'] for o in payload['objects']}:raise ValueError('Unassociated payload')
    by_id={cb['values'][0]:cb for cb in callbacks['callbacks']}
    display={cb['values'][0] for cb in callbacks['callbacks'] if family(cb,identities)=='strobe_cb'}
    if set(links.values())!=display:raise ValueError('Unassociated display callback')
    for obj in payload['objects']:
        cb=by_id[links[obj['id']]];v=cb['values']
        if v[1]!=obj['executing'] or not v[4] or obj['name']!='$strobe':raise ValueError('Changed associated display state')
    return {'callbacks':callbacks,'payload':payload,'links':links}


def inventory(path,identities,*,corrupt=False):
    ordinal=0;boundary=None;stages={};stage=None;lines=[];fault=None
    observed=executing=display=released=0
    for line in records(path,('VB_','VA_','VF_','VD_','VJ_')):
        a=line.split();kind=a[0]
        if fault is not None:raise ValueError('Observer continued after fault')
        if kind=='VB_BRIDGE':
            if boundary is not None or lines or len(a)!=4:raise ValueError('Unfinished boundary')
            index=int(a[1]);target=float(a[3]);phase=('before-step','after-step')[ordinal%2]
            if index!=ordinal or a[2]!=phase or not math.isfinite(target) or target<0:raise ValueError('Invalid boundary')
            boundary={'index':index,'phase':phase,'targetSeconds':target};ordinal+=1;stages={};stage=None
        elif kind=='VB_STAGE':
            if boundary is None or lines or len(a)!=2 or a[1] in stages or a[1] not in ('before','repeat','restored'):raise ValueError('Invalid stage')
            if stage is not None and stage not in stages:raise ValueError('Missing snapshot')
            stage=a[1]
        elif kind=='VA_BEGIN':
            if boundary is None or stage is None or stage in stages or lines:raise ValueError('Orphan bundle')
            lines=[line]
        elif kind=='VA_END' or kind.startswith(('VF_','VD_','VJ_')):
            if not lines:raise ValueError('Orphan observer record')
            lines.append(line)
            if kind=='VA_END':stages[stage]=(lines,bundle(lines,identities));lines=[]
        elif kind in ('VB_STABLE','VB_FAULT'):
            if boundary is None or lines:raise ValueError('Incomplete boundary')
            if kind=='VB_STABLE':
                if line!='VB_STABLE equal=1' or list(stages)!=['before','repeat'] or stages['before'][0]!=stages['repeat'][0]:raise ValueError('Observer changed state')
            else:
                if not corrupt or line!='VB_FAULT payload_unchanged=1 rejected=1 restored=1' or list(stages)!=['before','restored']:raise ValueError('Invalid association fault')
                if stages['before'][0]!=stages['restored'][0] or boundary['targetSeconds']<5e-6:raise ValueError('Association not restored')
                if not stages['before'][1]['links']:raise ValueError('Missing fault target')
                fault=dict(boundary)
            state=stages['before'][1];observed+=len(state['callbacks']['callbacks']);display+=len(state['links'])
            executing+=sum(cb['values'][1] for cb in state['callbacks']['callbacks'])
            released+=int(state['payload']['freed']>0 and not state['links'])
            boundary=None;stage=None
        else:raise ValueError('Unknown board observer record')
    if boundary is not None or lines or not ordinal or (fault is None and ordinal%2):raise ValueError('Incomplete observation')
    if not executing or not display or not released:raise ValueError('Missing display lifetime/continuation coverage')
    return {'boundaries':ordinal,'liveCallbackObservations':observed,'executingCallbackObservations':executing,
            'associatedDisplayObservations':display,'releasedDisplayObservations':released,'fault':fault}


def assess(root,producer):
    names=('baseline','rebuilt','off','observe','corrupt');runs={n:json.loads((root/n/'run.json').read_text()) for n in names}
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
    replaced={'ivlng.so','ivlng.vpi','libvvp.so','system.vpi'}
    def shared(r):return {d['path']:d['sha256'] for d in r['externalDependencies'] if Path(d['path']).name not in replaced}
    if shared(base)!=shared(runs['off']):raise ValueError('Changed non-candidate runtime dependencies')
    expected_deck=(root/'baseline/io.cir').read_text()
    for name in ('ivlng.so','libvvp.so','ivlng.vpi'):
        old,new=dep(base,name),dep(runs['off'],name)
        if expected_deck.count(old)!=1 or old==new:raise ValueError('Missing distinct observer runtime')
        expected_deck=expected_deck.replace(old,new)
    for key,filename in (('bridgeBuildSha256','bridge-build.json'),('icarusBuildSha256','icarus-build.json')):
        receipt_path=root/filename
        if sha(receipt_path)!=runs['off'][key]:raise ValueError('Changed build receipt')
        build=json.loads(receipt_path.read_text())
        targets=('ivlng.so','ivlng.vpi') if key.startswith('bridge') else ('vvp/libvvp.so','vpi/system.vpi')
        deps={d['path']:d['sha256'] for d in runs['off']['externalDependencies']}
        for target in targets:
            if deps.get(dep(runs['off'],Path(target).name))!=build['outputs'][target]:raise ValueError('Unmatched built runtime')
        if key.startswith('icarus'):
            rebuilt_deps={d['path']:d['sha256'] for d in runs['rebuilt']['externalDependencies']}
            if rebuilt_deps.get(dep(runs['rebuilt'],'system.vpi'))!=build['outputs']['baseline/system.vpi']:raise ValueError('Unmatched rebuilt module')
    if shared(runs['rebuilt'])!=shared(base):raise ValueError('Changed rebuilt shared dependencies')
    for name in ('ivlng.so','ivlng.vpi','libvvp.so'):
        if dep(runs['rebuilt'],name)!=dep(runs['off'],name):raise ValueError('Changed rebuilt candidate runtime')
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
        expected=dict(base['environment'])
        if mode!='baseline':expected.update(ROBOTRON_PRIVATE_DISPLAY=mode if mode in ('observe','corrupt') else 'off',ROBOTRON_DISPLAY_MODULE=dep(r,'system.vpi'))
        if r['environment']!=expected:raise ValueError('Changed capture environment')
        if mode!='baseline' and (folder/'io.cir').read_text()!=expected_deck:raise ValueError('Changed observer circuit')
        if mode in ('observe','corrupt') and r['externalDependencies']!=runs['off']['externalDependencies']:
            raise ValueError('Changed observer libraries')
        if set(r['inputs'])!=set(base['inputs']):raise ValueError('Changed inputs')
        for name,digest in r['inputs'].items():
            if sha(folder/name)!=digest:raise ValueError('Changed input bytes')
            if name=='s600.hex' and digest!=base['inputs'][name]:raise ValueError('Changed firmware')
        if mode!='baseline':
            old,new=dep(base,'system.vpi'),dep(r,'system.vpi')
            vvp=(root/'baseline/io.vvp').read_text()
            marker=':vpi_module \"'+old+'\";'
            if vvp.count(marker)!=1 or (folder/'io.vvp').read_text()!=vvp.replace(marker,':vpi_module \"'+new+'\";'):
                raise ValueError('Changed HDL beyond system module substitution')
        for name,digest in (('waveform.raw',r['storage']['waveform.raw']['sha256']),('ngspice.log',r['log']['sha256'])):
            if logical_sha(folder/name)!=digest:raise ValueError('Changed retained output')
        if r['exitCode']!=r['log']['exitCode']:raise ValueError('Inconsistent termination')
        if r['expectedExitCode']!=(2 if negative else 0):raise ValueError('Changed termination contract')
        if not negative:
            if not r['completed'] or r.get('error') or r['exitCode']!=0:raise ValueError('Incomplete positive control')
            scans[mode]=complete(folder/'ngspice.log')
            if not scans[mode]['latchesMatch'] or not any(records(folder/'ngspice.log',('FIRST_FETCH ',))):
                raise ValueError('Missing or invalid firmware execution')
        elif not r['completed'] or r.get('error') or r['exitCode']!=2:raise ValueError('Incomplete fault control')
        receipts[mode]=sha(folder/'run.json')
    for mode in ('baseline','rebuilt','off'):
        if next(records(root/mode/'ngspice.log',('VB_','VA_','VF_','VD_','VJ_')),None) is not None:raise ValueError('Disabled observer emitted records')
    observed=inventory(root/'observe/ngspice.log',identities);negative=inventory(root/'corrupt/ngspice.log',identities,corrupt=True)
    if bool(negative['fault'])!=(runs['corrupt']['exitCode']==2):raise ValueError('Fault/termination mismatch')
    if not any(records(root/'corrupt/ngspice.log',('FIRST_FETCH ',))):raise ValueError('Fault fixture never reached firmware')
    comparisons={}
    for label,left,right in (('rebuiltBaseline','baseline','rebuilt'),('disabledObserver','rebuilt','off'),('enabledObserver','off','observe')):
        comparisons[label]=compare_raw(root/left/'waveform.raw',root/right/'waveform.raw',[scans[n]['count'] for n in (left,right)],20e-6,exact=True)
        if not equal(root/left/'ngspice.log',root/right/'ngspice.log',FIRMWARE):raise ValueError('Changed firmware continuation')
    return {'reviewCompleted':True,'qualified':False,'controlsPassed':bool(negative['fault']),
            'comparisons':comparisons,'firmwareRecordsExactlyEqual':True,'observedCallbacks':observed,'negativeControl':negative,'receipts':receipts,'baselineReused':True,'payloadCoverageComplete':False,
            'scope':'Complete 20-us fixture with service reset at 1 us; typed display payloads linked to live callback handles, functions and user data at paused HDL step boundaries. Single-payload NULL fault rejected and restored before scheduler execution.',
            'notEstablished':['Other callback referents and complete private-state coverage','Initial start callback, executing stack/wrapper and other event payloads','General rollback or private-state restoration','Full post-reset/startup/repeat/supply recovery qualification']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','producer','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();result=assess(a.root,a.producer)
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
