#!/usr/bin/env python3
"""Review initialized bridge-port state and canonical handle/context bindings."""
import argparse,copy,json,math,re
from pathlib import Path
from audit_log import records,complete,equal
from compare_firmware_io import sha as logical_sha
from postreset_startup_review import FIRMWARE
from raw_pair_review import compare_raw
from ttl7406_probe import sha
from private_sync_family_board_review import verify_symbols
from wrapper_board_review import bundle as wrapper_bundle
from port_identity_review import snapshot as port_snapshot
from stop_board_review import startup_identity


def port_contract(vvp):
    lines=vvp.splitlines()
    roots=[(i,re.fullmatch(r'\S+ \.scope module, "([^"\\]+)" "[^"\\]+" \d+ \d+;',line.strip())) for i,line in enumerate(lines)]
    roots=[(i,m.group(1)) for i,m in roots if m]
    if len(roots)!=1:raise ValueError('Need one unambiguous compiled root module')
    start,root=roots[0];declared=[]
    for line in lines[start+1:]:
        if '.scope ' in line:break
        if '.port_info ' not in line:continue
        m=re.fullmatch(r'\s*\.port_info (\d+) /(INPUT|OUTPUT|INOUT) (\d+) "([^"\\]+)";',line)
        if not m or int(m[1])!=len(declared):raise ValueError('Invalid compiled port declaration')
        declared.append({'direction':{'INPUT':1,'OUTPUT':2,'INOUT':3}[m[2]],'bits':int(m[3]),'name':root+'.'+m[4]})
    if not declared:raise ValueError('Missing compiled ports')
    result=[]
    for direction in (1,2,3):
        position=0
        for p in declared:
            if p['direction']==direction:
                result.append(dict(p,index=len(result),position=position));position+=p['bits']
    return result


def bundle(lines,identities):
    starts=[i for i,l in enumerate(lines) if l.startswith('VP_BEGIN ')]
    if len(starts)!=1 or lines[-2:]!=['VP_END','VA_END']:raise ValueError('Missing/misplaced port section')
    i=starts[0];state=wrapper_bundle(lines[:i]+['VA_END'],identities)
    state['portState']=port_snapshot(lines[i:-1]);return state


def inventory(path,identities,*,fault_type=None,contract=None):
    if fault_type not in (None,'handle','context','value'):raise ValueError('Unknown fault type')
    ordinal=0;boundary=None;stages={};stage=None;lines=[];fault=None
    display=released=saved=cleared=executing=empty=0;event_links={};callback_links={}
    markers={kind:f'VB_PORT_FAULT kind=port-{kind}-corrupt detected=1 restored=1' for kind in ('handle','context','value')}
    layout=None;port_observations=0
    for line in records(path,('VB_','VA_','VF_','VD_','VJ_','VR_','VE_','VP_')):
        a=line.split();kind=a[0]
        if fault is not None:raise ValueError('Continuation after fault')
        if kind=='VB_BRIDGE':
            if boundary is not None or lines or len(a)!=4:raise ValueError('Unfinished boundary')
            index=int(a[1]);target=float(a[3]);phase=('before-step','after-step')[ordinal%2]
            if index!=ordinal or a[2]!=phase or not math.isfinite(target) or target<0:raise ValueError('Invalid boundary')
            boundary={'index':index,'phase':phase,'targetSeconds':target};ordinal+=1;stages={};stage=None
        elif kind=='VB_STAGE':
            if boundary is None or lines or len(a)!=2 or a[1] in stages or a[1] not in ('before','repeat','changed','restored'):raise ValueError('Invalid stage')
            if stage is not None and stage not in stages:raise ValueError('Missing snapshot')
            stage=a[1]
        elif kind=='VA_BEGIN':
            if boundary is None or stage is None or stage in stages or lines:raise ValueError('Orphan bundle')
            lines=[line]
        elif kind=='VA_END' or kind.startswith(('VF_','VD_','VJ_','VR_','VE_','VP_')):
            if not lines:raise ValueError('Orphan observer record')
            lines.append(line)
            if kind=='VA_END':stages[stage]=(lines,bundle(lines,identities));lines=[]
        elif kind in ('VB_STABLE','VB_PORT_FAULT'):
            if boundary is None or lines:raise ValueError('Incomplete boundary')
            if kind=='VB_STABLE':
                if line!='VB_STABLE equal=1' or list(stages)!=['before','repeat'] or stages['before'][0]!=stages['repeat'][0]:raise ValueError('Observer changed state')
            else:
                expected=['before','changed','restored'] if fault_type=='value' else ['before','restored']
                if fault_type is None or line!=markers[fault_type] or list(stages)!=expected:raise ValueError('Wrong fault control')
                if stages['before'][0]!=stages['restored'][0] or boundary['targetSeconds']<5e-6:raise ValueError('Fault not restored')
                before=stages['before'][1]
                if fault_type=='value':
                    wanted=copy.deepcopy(before);wanted['portState']['ports'][0]['previous'][0]^=1
                    if stages['changed'][1]!=wanted:raise ValueError('Wrong port value mutation')
                fault=dict(boundary)
            state=stages['before'][1]
            metadata=[{k:p[k] for k in ('index','direction','bits','position','name')} for p in state['portState']['ports']]
            if layout is None:layout=metadata
            if metadata!=layout or (contract is not None and metadata!=contract):raise ValueError('Port identity differs from compiled interface')
            port_observations+=len(metadata)
            for frame in state['frames']:
                if frame['deleteObject']:raise ValueError('Wrong normal wrapper ownership')
                event,callback=frame['id'],frame['callbackId']
                if event_links.get(event,callback)!=callback or callback_links.get(callback,event)!=event:raise ValueError('Reused executing identity')
                event_links[event]=callback;callback_links[callback]=event
            executing+=len(state['frames']);empty+=int(not state['frames'])
            display+=len(state['links']);released+=int(state['payload']['freed']>0 and not state['links'])
            saved+=int(state['stop']['present']);cleared+=int(not state['stop']['present'])
            boundary=None;stage=None
        else:raise ValueError('Unknown observer record')
    if boundary is not None or lines or not ordinal or (fault is None and ordinal%2):raise ValueError('Incomplete observations')
    if not executing or not empty or not saved or not cleared or (fault_type is None and (not display or not released)):raise ValueError('Missing state coverage')
    if fault_type and fault is None:raise ValueError('Unexercised fault')
    return {'boundaries':ordinal,'executingWrapperObservations':executing,'emptyFrameObservations':empty,
            'uniqueExecutingEvents':len(event_links),'associatedDisplayObservations':display,'releasedDisplayObservations':released,
            'savedStopObservations':saved,'clearedStopObservations':cleared,'portObservations':port_observations,'ports':layout,'fault':fault}


def assess(root,producer):
    names=('baseline','off','observe','handle-corrupt','context-corrupt','value-corrupt');runs={n:json.loads((root/n/'run.json').read_text()) for n in names}
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
        folder=root/mode;negative=mode not in ('baseline','off','observe')
        if not r['completed'] or r.get('error') or r['exitCode']!=(2 if negative else 0) or r['log']['exitCode']!=r['exitCode'] or r['expectedExitCode']!=r['exitCode']:
            raise ValueError('Incomplete or wrong termination')
        if r['runtime']!=base['runtime'] or r['endSeconds']!=base['endSeconds']:raise ValueError('Changed runtime/window')
        if mode!='baseline':
            if r['mode']!=mode or r['producerSha256']!=sha(producer):raise ValueError('Changed producer/mode')
            for key,path in [('baselineReceiptSha256','baseline/run.json'),('baselineAssessmentSha256','baseline-assessment.json'),('bridgeBuildSha256','bridge-build.json'),('symbolReceiptSha256','symbols.json')]:
                if r[key]!=sha(root/path):raise ValueError('Changed '+key)
            if r.get('runtimeEnvironment')!={'SPICE_SCRIPTS':str(Path(base['runtime']['spinit']['path']).parent)}:raise ValueError('Missing explicit XSPICE initialization selection')
            expected=dict(base['environment'],ROBOTRON_PRIVATE_DISPLAY='port-'+mode if negative else mode)
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
        if next(records(root/mode/'ngspice.log',('VB_','VA_','VF_','VD_','VJ_','VR_','VE_','VP_')),None) is not None:raise ValueError('Disabled observer emitted records')
    contract=port_contract((root/'baseline/io.vvp').read_text())
    observed=inventory(root/'observe/ngspice.log',identities,contract=contract)
    negatives={mode:inventory(root/mode/'ngspice.log',identities,fault_type=mode.split('-')[0],contract=contract) for mode in ('handle-corrupt','context-corrupt','value-corrupt')}
    comparisons={}
    for label,left,right in [('disabledBaseline','baseline','off'),('enabledObserver','off','observe')]:
        comparisons[label]=compare_raw(root/left/'waveform.raw',root/right/'waveform.raw',[scans[n]['count'] for n in (left,right)],20e-6,exact=True)
        if not equal(root/left/'ngspice.log',root/right/'ngspice.log',FIRMWARE):raise ValueError('Changed firmware continuation')
    return {'reviewCompleted':True,'qualified':False,'controlsPassed':True,'comparisons':comparisons,
            'firmwareRecordsExactlyEqual':True,'observedState':observed,'negativeControls':negatives,'receipts':receipts,
            'scope':'Complete 20-us service fixture, reset at 1 us. Canonical port identities bound before first yield, initialized state observed at board boundaries and matched to the compiled interface. Input-only new words are excluded. Handle, context and previous-value faults restored before scheduling.',
            'notEstablished':['Output-callback registration roots, initialization-only event families and scheduler continuation','Freed-storage equivalence or general rollback','Full post-reset/startup/repeat/supply recovery qualification']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('root','producer','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();result=assess(a.root,a.producer)
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
