#!/usr/bin/env python3
"""Review saved stop-handle controls against the preceding display baseline."""
import argparse,json,math
from pathlib import Path
from audit_log import records,complete,equal
from compare_firmware_io import sha as logical_sha
from postreset_startup_review import FIRMWARE
from raw_pair_review import compare_raw
from ttl7406_probe import sha
from private_sync_family_board_review import verify_symbols
from display_stop_review import bundle


def inventory(path,identities,*,corrupt=False):
    ordinal=0;boundary=None;stages={};stage=None;lines=[];fault=None
    observed=executing=display=released=saved=cleared=0
    for line in records(path,('VB_','VA_','VF_','VD_','VJ_','VR_')):
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
        elif kind=='VA_END' or kind.startswith(('VF_','VD_','VJ_','VR_')):
            if not lines:raise ValueError('Orphan observer record')
            lines.append(line)
            if kind=='VA_END':stages[stage]=(lines,bundle(lines,identities));lines=[]
        elif kind in ('VB_STABLE','VB_STOP_FAULT'):
            if boundary is None or lines:raise ValueError('Incomplete boundary')
            if kind=='VB_STABLE':
                if line!='VB_STABLE equal=1' or list(stages)!=['before','repeat'] or stages['before'][0]!=stages['repeat'][0]:raise ValueError('Observer changed state')
            else:
                if not corrupt or line!='VB_STOP_FAULT rejected=1 restored=1' or list(stages)!=['before','restored']:raise ValueError('Invalid association fault')
                if stages['before'][0]!=stages['restored'][0] or boundary['targetSeconds']<5e-6:raise ValueError('Association not restored')
                if not stages['before'][1]['stop']['present']:raise ValueError('Missing fault target')
                fault=dict(boundary)
            state=stages['before'][1];observed+=len(state['callbacks']['callbacks']);display+=len(state['links'])
            executing+=sum(cb['values'][1] for cb in state['callbacks']['callbacks'])
            released+=int(state['payload']['freed']>0 and not state['links'])
            saved+=int(state['stop']['present']);cleared+=int(not state['stop']['present'])
            boundary=None;stage=None
        else:raise ValueError('Unknown board observer record')
    if boundary is not None or lines or not ordinal or (fault is None and ordinal%2):raise ValueError('Incomplete observation')
    if not executing or (not corrupt and (not display or not released)) or not saved or not cleared:raise ValueError('Missing display lifetime/continuation coverage')
    return {'boundaries':ordinal,'liveCallbackObservations':observed,'executingCallbackObservations':executing,
            'associatedDisplayObservations':display,'releasedDisplayObservations':released,'savedStopObservations':saved,'clearedStopObservations':cleared,'fault':fault}


def startup_identity(path):
    lines=[line for line in records(path,('HISTORY_INIT ','Instance: ')) if line.startswith('HISTORY_INIT ') or 'DAC_ANCHORED enabled' in line]
    if not any(l.startswith('HISTORY_INIT ') for l in lines) or not any('DAC_ANCHORED enabled' in l for l in lines):
        raise ValueError('Missing selected XSPICE startup diagnostics')
    return lines


def assess(root,producer):
    names=('baseline','off','observe','corrupt');runs={n:json.loads((root/n/'run.json').read_text()) for n in names}
    base=runs['baseline'];prior=json.loads((root/'baseline-assessment.json').read_text())
    if not prior.get('controlsPassed') or prior['receipts']['off']!=sha(root/'baseline/run.json'):
        raise ValueError('Unreviewed display baseline')
    if base['mode']!='off' or base['endSeconds']!=20e-6:raise ValueError('Changed baseline scope')
    identities=verify_symbols(root,runs);build=json.loads((root/'bridge-build.json').read_text())
    def dep(run,name):
        matches=[d for d in run['externalDependencies'] if Path(d['path']).name==name]
        if len(matches)!=1:raise ValueError('Ambiguous dependency')
        return matches[0]
    def shared(run):return {d['path']:d['sha256'] for d in run['externalDependencies'] if Path(d['path']).name not in ('ivlng.so','ivlng.vpi')}
    if shared(base)!=shared(runs['off']):raise ValueError('Changed non-bridge runtime')
    deck=(root/'baseline/io.cir').read_text()
    for name in ('ivlng.so','ivlng.vpi'):
        old,new=dep(base,name),dep(runs['off'],name)
        if old['path']==new['path'] or deck.count(old['path'])!=1 or new['sha256']!=build['outputs'][name]:
            raise ValueError('Unpinned bridge substitution')
        deck=deck.replace(old['path'],new['path'])
    startup=startup_identity(root/'baseline/ngspice.log')
    scans={};receipts={}
    for mode,r in runs.items():
        folder=root/mode;negative=mode=='corrupt'
        if not r['completed'] or r.get('error') or r['exitCode']!=(2 if negative else 0) or r['log']['exitCode']!=r['exitCode'] or r['expectedExitCode']!=r['exitCode']:
            raise ValueError('Incomplete or wrong termination')
        if r['runtime']!=base['runtime'] or r['endSeconds']!=base['endSeconds']:raise ValueError('Changed runtime/window')
        if mode!='baseline':
            if r['mode']!=mode or r['producerSha256']!=sha(producer):raise ValueError('Changed producer/mode')
            for key,path in [('baselineReceiptSha256','baseline/run.json'),('baselineAssessmentSha256','baseline-assessment.json'),('bridgeBuildSha256','bridge-build.json'),('symbolReceiptSha256','symbols.json')]:
                if r[key]!=sha(root/path):raise ValueError('Changed '+key)
            if r.get('runtimeEnvironment')!={'SPICE_SCRIPTS':str(Path(base['runtime']['spinit']['path']).parent)}:raise ValueError('Missing explicit XSPICE initialization selection')
            expected=dict(base['environment'],ROBOTRON_PRIVATE_DISPLAY='stop-corrupt' if negative else mode)
            if r['environment']!=expected or r['externalDependencies']!=runs['off']['externalDependencies']:
                raise ValueError('Changed matched control environment/dependencies')
            if (folder/'io.cir').read_text()!=deck:raise ValueError('Changed circuit beyond bridge substitution')
        if set(r['inputs'])!=set(base['inputs']):raise ValueError('Changed input set')
        for name,h in r['inputs'].items():
            if sha(folder/name)!=h or (name!='io.cir' and h!=base['inputs'][name]):raise ValueError('Changed input/firmware')
        for name,h in [('waveform.raw',r['storage']['waveform.raw']['sha256']),('ngspice.log',r['log']['sha256'])]:
            if logical_sha(folder/name)!=h:raise ValueError('Changed retained output')
        if startup_identity(folder/'ngspice.log')!=startup:raise ValueError('Changed XSPICE startup diagnostics')
        if not negative:
            scans[mode]=complete(folder/'ngspice.log')
            if not scans[mode]['latchesMatch']:raise ValueError('Invalid firmware continuation')
        if not any(records(folder/'ngspice.log',('FIRST_FETCH ',))):raise ValueError('Missing firmware execution')
        receipts[mode]=sha(folder/'run.json')
    for mode in ('baseline','off'):
        if next(records(root/mode/'ngspice.log',('VB_','VA_','VF_','VD_','VJ_','VR_')),None) is not None:raise ValueError('Disabled observer emitted records')
    observed=inventory(root/'observe/ngspice.log',identities)
    negative=inventory(root/'corrupt/ngspice.log',identities,corrupt=True)
    if not negative['fault']:raise ValueError('Unexercised stop fault')
    comparisons={}
    for label,left,right in [('disabledBaseline','baseline','off'),('enabledObserver','off','observe')]:
        comparisons[label]=compare_raw(root/left/'waveform.raw',root/right/'waveform.raw',[scans[n]['count'] for n in (left,right)],20e-6,exact=True)
        if not equal(root/left/'ngspice.log',root/right/'ngspice.log',FIRMWARE):raise ValueError('Changed firmware continuation')
    return {'reviewCompleted':True,'qualified':False,'controlsPassed':True,'comparisons':comparisons,
            'firmwareRecordsExactlyEqual':True,'observedRelationships':observed,'negativeControl':negative,'receipts':receipts,
            'scope':'Complete 20-us service fixture, reset at 1 us. Saved stop handles linked to active executing delayed callbacks; cleared handles observed during startup/output stops. Invalid opaque handle rejected and restored before scheduler continuation.',
            'notEstablished':['Port referent identities, executing wrappers and initialization-only event families','Freed-storage equivalence or general rollback','Full post-reset/startup/repeat/supply recovery qualification']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('root','producer','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();result=assess(a.root,a.producer)
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
