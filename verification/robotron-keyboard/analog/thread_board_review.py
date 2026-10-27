#!/usr/bin/env python3
"""Review initialized live threads and scheduler bindings with preceding board layers."""
import argparse,json,math
from pathlib import Path
from audit_log import records,complete,equal
from compare_firmware_io import sha as logical_sha
from postreset_startup_review import FIRMWARE
from raw_pair_review import compare_raw
from ttl7406_probe import sha
from private_sync_family_board_review import verify_symbols
from primitive_board_review import PrimitiveLifetimes
from island_board_review import IslandLifetimes
from island_filter_board_review import bundle as filter_bundle,FilterLifetimes
from thread_compact_probe import parse_snapshot
from thread_probe import changed_snapshot,validate_normal
import copy
from port_board_review import port_contract
from stop_board_review import startup_identity


FAULTS={'schedule':0,'flag':1,'word':2,'pc':3,'wait':4,'queue':8}


def queue_snapshot(lines):
    a=lines[0].split();z=lines[-1].split()
    if len(a)!=3 or a[:2]!=['VTQ_BEGIN','1'] or len(z)!=3 or z[0]!='VTQ_END':raise ValueError('Missing thread queue framing')
    tick=int(a[2]);events=[];identities=set();positions=set()
    for line in lines[1:-1]:
        a=line.split()
        if len(a)!=8 or a[0]!='VTQ_EVENT':raise ValueError('Invalid thread event')
        slot,ordinal,identity,kind,thread=map(int,(a[1],a[3],a[4],a[5],a[6]));key=0 if a[7]=='(nil)' else int(a[7],16)
        if slot< -1 or ordinal<0 or identity<1 or kind not in (1,2) or min(thread,key)<0 or bool(thread)!=bool(key):raise ValueError('Invalid thread event identity')
        if a[2] not in ('init','final','start','active','inactive','nbassign','rwsync','rosync','del_thr'):raise ValueError('Invalid thread queue region')
        if identity in identities or (slot,a[2],ordinal) in positions:raise ValueError('Aliased thread event')
        identities.add(identity);positions.add((slot,a[2],ordinal))
        events.append(dict(slot=slot,region=a[2],ordinal=ordinal,id=identity,kind=kind,thread=thread,key=key))
    if tick<0 or int(z[1])!=len(events) or int(z[2])<0:raise ValueError('Invalid thread queue footer')
    return dict(tick=tick,events=events,unsupportedEvents=int(z[2]))


def bundle(lines,identities):
    starts=[i for i,l in enumerate(lines) if l.startswith('VT_BEGIN ')]
    queues=[i for i,l in enumerate(lines) if l.startswith('VTQ_BEGIN ')]
    if len(starts)!=1 or len(queues)!=1 or lines[-1]!='VA_END' or not starts[0]<queues[0]:raise ValueError('Missing live-thread sections')
    i,j=starts[0],queues[0];state=filter_bundle(lines[:i]+['VA_END'],identities)
    state['threads']=parse_snapshot(lines[i:j]);state['threadQueue']=queue_snapshot(lines[j:-1])
    if state['threads']['tick']!=state['callbacks']['time'] or state['threadQueue']['tick']!=state['callbacks']['time']:raise ValueError('Thread/callback native time mismatch')
    return state


def changed_thread(before,changed,fault_type):
    field=FAULTS[fault_type]
    if field==8:
        if {k:v for k,v in before.items() if k!='threadQueue'}!={k:v for k,v in changed.items() if k!='threadQueue'}:raise ValueError('Queue fault changed unrelated state')
        expected=copy.deepcopy(before['threadQueue']);targets=[e for e in expected['events'] if e['kind']==1 and e['thread']]
        if not targets:raise ValueError('Missing queued thread fault target')
        targets[0].update(thread=0,key=0)
        if expected!=changed['threadQueue']:raise ValueError('Wrong queued thread payload fault')
    else:
        if {k:v for k,v in before.items() if k!='threads'}!={k:v for k,v in changed.items() if k!='threads'}:raise ValueError('Thread fault changed unrelated state')
        changed_snapshot(before['threads'],changed['threads'],field)


class ThreadLifetimes:
    def __init__(self):
        self.threads={};self.previous=set();self.retired=set();self.events={};self.previous_events=set();self.retired_events=set();self.objects={}
        self.observations=0;self.queued=0;self.empty=0;self.waiting=0;self.words=0;self.extended=0;self.deletions=0;self.unwritten=0

    def observe(self,state):
        snapshot=state['threads'];queue=state['threadQueue'];validate_normal(snapshot)
        if snapshot['running']:raise ValueError('Board boundary inside active thread requires pending execution-chain coverage')
        live={t['id']:t for t in snapshot['threads']};current=set(live)
        if not live or current&self.retired:raise ValueError('Missing/reused thread lifetime')
        self.retired.update(self.previous-current);self.previous=current
        for identity,t in live.items():
            flags=tuple(i for i,c in enumerate(t['flags']) if c!='-');words=tuple(i for i,c in enumerate(t['words']) if c!='-')
            old=self.threads.get(identity)
            if old and (old['scope']!=t['scope'] or not set(old['flags'])<=set(flags) or not set(old['words'])<=set(words)):raise ValueError('Changed thread scope or lost initialized register')
            self.threads[identity]=dict(scope=t['scope'],flags=flags,words=words)
            self.observations+=1;self.waiting+=int(t['state'][6]=='1');self.words+=len(words);self.extended+=sum(i>=8 for i in flags)
            self.unwritten+=512-len(flags)+16-len(words)
        event_ids=set();scheduled=set()
        for event in queue['events']:
            eid=event['id'];identity=event['thread'];event_ids.add(eid)
            if identity not in live or not event['key']:raise ValueError('Unknown queued thread object')
            binding=(event['kind'],identity,event['key'])
            if eid in self.retired_events or (eid in self.events and self.events[eid]!=binding):raise ValueError('Reused/rebound thread event lifetime')
            if identity in self.objects and self.objects[identity]!=event['key']:raise ValueError('Thread object identity changed')
            self.events[eid]=binding;self.objects[identity]=event['key']
            if event['kind']==2:
                if live[identity]['state'][8]!='1':raise ValueError('Deletion without delayed-delete state')
                self.deletions+=1;continue
            current_thread=identity
            while current_thread:
                if current_thread in scheduled:raise ValueError('Thread scheduled more than once')
                scheduled.add(current_thread);t=live[current_thread]
                if t['state'][7]!='1':raise ValueError('Queued thread lacks scheduled flag')
                current_thread=t['wait']
        if scheduled!={i for i,t in live.items() if t['state'][7]=='1'}:raise ValueError('Scheduled flags disagree with queued thread chains')
        self.retired_events.update(self.previous_events-event_ids);self.previous_events=event_ids
        self.queued+=len(scheduled);self.empty+=int(not event_ids)

    def result(self,negative):
        if not self.queued or not self.unwritten or (not negative and (not self.waiting or not self.words or not self.empty)):raise ValueError('Missing initialized/queued/waiting thread coverage')
        return dict(liveThreadObservations=self.observations,uniqueThreads=len(self.threads),uniqueThreadEvents=len(self.events),
                    queuedThreadObservations=self.queued,eventWaitingObservations=self.waiting,initializedWordObservations=self.words,
                    initializedExtendedFlagObservations=self.extended,unwrittenRegisterObservations=self.unwritten,
                    emptyThreadQueueBoundaries=self.empty,delayedDeletionObservations=self.deletions)


def inventory(path,identities,*,fault_type=None,contract=None):
    if fault_type is not None and fault_type not in FAULTS:raise ValueError('Unknown fault type')
    primitives=PrimitiveLifetimes();island_lifetimes=IslandLifetimes();filters=FilterLifetimes();threads=ThreadLifetimes()
    ordinal=0;boundary=None;stages={};stage=None;lines=[];fault=None
    display=released=saved=cleared=executing=empty=0;event_links={};callback_links={}
    markers={name:f'VB_THREAD_FAULT field={field} changed=1 restored=1' for name,field in FAULTS.items()}
    layout=None;port_observations=0;output_layout=None;output_observations=0
    startup_id=None;startup_phase=1;active_start=finished_start=0
    assignment_ids={};previous_ids=set();retired_ids=set();assignment_counts={4:0,8:0};empty_assignments=0;unsupported_max=0
    for line in records(path,('VB_','VA_','VF_','VD_','VJ_','VR_','VE_','VP_','VW_','VS_','VAP_','VPR_','VI_','VIQ_','VIF_','VT_','VTQ_')):
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
        elif kind=='VA_END' or kind.startswith(('VF_','VD_','VJ_','VR_','VE_','VP_','VW_','VS_','VAP_','VPR_','VI_','VIQ_','VIF_','VT_','VTQ_')):
            if not lines:raise ValueError('Orphan observer record')
            lines.append(line)
            if kind=='VA_END':stages[stage]=(lines,bundle(lines,identities));lines=[]
        elif kind in ('VB_STABLE','VB_THREAD_FAULT'):
            if boundary is None or lines:raise ValueError('Incomplete boundary')
            if kind=='VB_STABLE':
                if line!='VB_STABLE equal=1' or list(stages)!=['before','repeat'] or stages['before'][0]!=stages['repeat'][0]:raise ValueError('Observer changed state')
            else:
                expected=['before','changed','restored']
                if fault_type is None or line!=markers[fault_type] or list(stages)!=expected:raise ValueError('Wrong fault control')
                if stages['before'][0]!=stages['restored'][0]:raise ValueError('Fault not restored')
                if fault_type=='word':
                    if boundary['targetSeconds']<5e-6:raise ValueError('Word fault before initialized late boundary')
                elif boundary['index']!=0 or boundary['targetSeconds']!=0:raise ValueError('Early fault missed paused startup')
                changed_thread(stages['before'][1],stages['changed'][1],fault_type)
                fault=dict(boundary)
            state=stages['before'][1]
            threads.observe(state)
            filters.observe(state)
            island_lifetimes.observe(state)
            primitives.observe(state['primitives'])
            assignments=state['assignments'];current_ids=set()
            for event in assignments['events']:
                identity=event['id'];current_ids.add(identity)
                intrinsic={k:v for k,v in event.items() if k not in ('slot','region','ordinal')}
                if identity in retired_ids or (identity in assignment_ids and assignment_ids[identity]!=intrinsic):
                    raise ValueError('Assignment lifetime reused or queued contents changed')
                assignment_ids[identity]=intrinsic;assignment_counts[event['kind']]+=1
            retired_ids.update(previous_ids-current_ids);previous_ids=current_ids
            empty_assignments+=int(not current_ids);unsupported_max=max(unsupported_max,assignments['unsupportedEvents'])
            start=state['startup']
            if startup_id is None:startup_id=start['registeredId']
            if start['registeredId']!=startup_id or start['phase']<startup_phase:
                raise ValueError('Startup identity changed or returned to an earlier phase')
            startup_phase=start['phase']
            active_start+=int(startup_phase==1);finished_start+=int(startup_phase==2)
            if fault is not None and startup_phase!=(2 if fault_type=='word' else 1):raise ValueError('Wrong fault lifecycle phase')
            if output_layout is None:output_layout=state['outputCallbacks']
            if state['outputCallbacks']!=output_layout:raise ValueError('Changed output callback lifetime/port relationship')
            output_observations+=len(output_layout)
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
    if not active_start or (fault_type is None and (not finished_start or not executing or not empty or not saved or not cleared or not display or not released)):raise ValueError('Missing startup or later board state coverage')
    if not assignment_counts[4] or not assignment_counts[8] or (fault_type is None and not empty_assignments):raise ValueError('Missing assignment family or consumption coverage')
    if fault_type and fault is None:raise ValueError('Unexercised fault')
    return {**threads.result(fault_type is not None),**filters.result(fault_type is not None),**island_lifetimes.result(fault_type is not None),**primitives.result(fault_type is not None),'assignmentObservations':assignment_counts,'uniqueAssignments':len(assignment_ids),'emptyAssignmentBoundaries':empty_assignments,'maximumUncoveredEvents':unsupported_max,'startupLifetimeId':startup_id,'activeStartupObservations':active_start,'destroyedStartupObservations':finished_start,'boundaries':ordinal,'executingWrapperObservations':executing,'emptyFrameObservations':empty,
            'uniqueExecutingEvents':len(event_links),'associatedDisplayObservations':display,'releasedDisplayObservations':released,
            'savedStopObservations':saved,'clearedStopObservations':cleared,'portObservations':port_observations,'ports':layout,'outputCallbackObservations':output_observations,'outputCallbacks':output_layout,'fault':fault}


def assess(root,producer):
    names=('baseline','off','observe','schedule-corrupt','flag-corrupt','word-corrupt','pc-corrupt','wait-corrupt','queue-corrupt')
    runs={n:json.loads((root/n/'run.json').read_text()) for n in names}
    base=runs['baseline'];prior=json.loads((root/'baseline-assessment.json').read_text())
    if not prior.get('controlsPassed') or prior['receipts']['off']!=sha(root/'baseline/run.json'):raise ValueError('Unreviewed baseline')
    if base['mode']!='off' or base['endSeconds']!=20e-6:raise ValueError('Changed baseline scope')
    identities=verify_symbols(root,runs)
    def dep(run,name):
        matches=[d for d in run['externalDependencies'] if Path(d['path']).name==name]
        if len(matches)!=1:raise ValueError('Ambiguous dependency')
        return matches[0]
    replaced={'ivlng.so','ivlng.vpi','libvvp.so','system.vpi'}
    def shared(run):return {d['path']:d['sha256'] for d in run['externalDependencies'] if Path(d['path']).name not in replaced}
    if shared(base)!=shared(runs['off']):raise ValueError('Changed non-candidate runtime')
    for filename,outputs in [('bridge-build.json',('ivlng.so','ivlng.vpi')),('icarus-build.json',('vvp/libvvp.so','vpi/system.vpi'))]:
        build=json.loads((root/filename).read_text())
        for name in outputs:
            if dep(runs['off'],Path(name).name)['sha256']!=build['outputs'][name]:raise ValueError('Unmatched built runtime')
    deck=(root/'baseline/io.cir').read_text()
    for name in ('ivlng.so','ivlng.vpi','libvvp.so'):
        old,new=dep(base,name),dep(runs['off'],name)
        if old['path']==new['path'] or deck.count(old['path'])!=1:raise ValueError('Missing distinct candidate runtime')
        deck=deck.replace(old['path'],new['path'])
    original=(root/'baseline/io.vvp').read_text();marker=':vpi_module "'+dep(base,'system.vpi')['path']+'";'
    if original.count(marker)!=1:raise ValueError('Changed system module placement')
    vvp=original.replace(marker,':vpi_module "'+dep(runs['off'],'system.vpi')['path']+'";')
    startup=startup_identity(root/'baseline/ngspice.log');scans={};receipts={}
    for mode,r in runs.items():
        folder=root/mode;negative=mode not in ('baseline','off','observe')
        if not r['completed'] or r.get('error') or r['exitCode']!=(2 if negative else 0) or r['log']['exitCode']!=r['exitCode'] or r['expectedExitCode']!=r['exitCode']:raise ValueError('Incomplete or wrong termination')
        if r['runtime']!=base['runtime'] or r['endSeconds']!=base['endSeconds']:raise ValueError('Changed runtime/window')
        if mode!='baseline':
            if r['mode']!=mode or r['producerSha256']!=sha(producer):raise ValueError('Changed producer/mode')
            for key,path in [('baselineReceiptSha256','baseline/run.json'),('baselineAssessmentSha256','baseline-assessment.json'),('bridgeBuildSha256','bridge-build.json'),('icarusBuildSha256','icarus-build.json'),('symbolReceiptSha256','symbols.json')]:
                if r[key]!=sha(root/path):raise ValueError('Changed '+key)
            expected=dict(base['environment'],ROBOTRON_DISPLAY_MODULE=dep(runs['off'],'system.vpi')['path'],ROBOTRON_PRIVATE_DISPLAY='thread-'+mode if negative else mode)
            if r['environment']!=expected or r['externalDependencies']!=runs['off']['externalDependencies']:raise ValueError('Changed matched control')
            if r.get('runtimeEnvironment')!={'SPICE_SCRIPTS':str(Path(base['runtime']['spinit']['path']).parent)}:raise ValueError('Missing XSPICE selection')
            if (folder/'io.cir').read_text()!=deck or (folder/'io.vvp').read_text()!=vvp:raise ValueError('Changed circuit or HDL beyond runtime substitutions')
        if set(r['inputs'])!=set(base['inputs']):raise ValueError('Changed inputs')
        for name,h in r['inputs'].items():
            if sha(folder/name)!=h or (name=='s600.hex' and h!=base['inputs'][name]):raise ValueError('Changed input/firmware')
        for name,h in [('waveform.raw',r['storage']['waveform.raw']['sha256']),('ngspice.log',r['log']['sha256'])]:
            if logical_sha(folder/name)!=h:raise ValueError('Changed output')
        if not negative:
            if startup_identity(folder/'ngspice.log')!=startup:raise ValueError('Changed initialized models')
        else:
            early=[line for line in records(folder/'ngspice.log',('HISTORY_INIT ','Instance: ')) if line.startswith('HISTORY_INIT ') or 'DAC_ANCHORED enabled' in line]
            if early!=startup[:len(early)]:raise ValueError('Changed early initialization diagnostics')
        if not negative:
            scans[mode]=complete(folder/'ngspice.log')
            if not scans[mode]['latchesMatch']:raise ValueError('Invalid firmware continuation')
        if not negative and not any(records(folder/'ngspice.log',('FIRST_FETCH ',))):raise ValueError('Missing firmware execution')
        receipts[mode]=sha(folder/'run.json')
    for mode in ('baseline','off'):
        if next(records(root/mode/'ngspice.log',('VB_','VA_','VF_','VD_','VJ_','VR_','VE_','VP_','VW_','VS_','VAP_','VPR_','VI_','VIQ_','VIF_','VT_','VTQ_')),None) is not None:raise ValueError('Disabled observer emitted records')
    contract=port_contract((root/'baseline/io.vvp').read_text())
    observed=inventory(root/'observe/ngspice.log',identities,contract=contract)
    negatives={mode:inventory(root/mode/'ngspice.log',identities,fault_type=mode.removesuffix('-corrupt'),contract=contract) for mode in ('schedule-corrupt','flag-corrupt','word-corrupt','pc-corrupt','wait-corrupt','queue-corrupt')}
    comparisons={}
    for label,left,right in [('disabledBaseline','baseline','off'),('enabledObserver','off','observe')]:
        comparisons[label]=compare_raw(root/left/'waveform.raw',root/right/'waveform.raw',[scans[n]['count'] for n in (left,right)],20e-6,exact=True)
        if not equal(root/left/'ngspice.log',root/right/'ngspice.log',FIRMWARE):raise ValueError('Changed firmware continuation')
    return {'reviewCompleted':True,'qualified':False,'controlsPassed':True,'comparisons':comparisons,'firmwareRecordsExactlyEqual':True,
            'observedState':observed,'negativeControls':negatives,'receipts':receipts,
            'scope':'Complete 20-us service fixture, reset at 1 us. Initialized live-thread state and queued event chains observed with all preceding board layers. Lifecycle, flag, word, PC, wait and queue faults restore before scheduling; word fault follows initialization. Normal controls preserve exact waveform samples and firmware continuation.',
            'notEstablished':['Wait-event/code/scope/context/object and callback/fanout referent contents','Reachable detached/deferred-deletion paths, freed-storage equivalence or general rollback','Full post-reset/startup/repeat/supply recovery qualification']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('root','producer','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();result=assess(a.root,a.producer)
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
