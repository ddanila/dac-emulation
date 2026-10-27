#!/usr/bin/env python3
"""Review complete compact array images with every preceding board layer."""
import argparse,json,math,copy
from pathlib import Path
from fast_audit_log import records,complete,equal
from compare_firmware_io import sha as logical_sha
from postreset_startup_review import FIRMWARE
from raw_pair_review import compare_raw
from ttl7406_probe import sha
from private_sync_family_board_review import verify_symbols
from primitive_board_review import PrimitiveLifetimes
from island_board_review import IslandLifetimes
from island_filter_board_review import FilterLifetimes
from thread_board_review import ThreadLifetimes
from wait_board_review import bundle as wait_bundle,WaitLifetimes
from code_binding_board_review import bundle as code_bundle, CodeBindings
from scope_board_review import bundle as scope_bundle,ScopeMembership
from code_operand_board_review import bundle as operand_bundle,OperandState
from array_probe import parse as array_parse,validate as array_validate,changed as array_changed
from array_compact_probe import expand
from array_source_contract import profile as array_profile
import collections
from thread_board_reachability import analyze
from board_thread_contract import compiled_contract,validate_snapshot as validate_board_threads
import board_thread_contract
from port_board_review import port_contract
from stop_board_review import startup_identity

FAULTS={'word':0,'address':1,'link':2,'cache':3}
HERE=Path(__file__).resolve().parent


def bundle(lines,identities):
    starts=[i for i,l in enumerate(lines) if l.startswith('VAC_BEGIN ')]
    if len(starts)!=1 or lines[-1]!='VA_END':raise ValueError('Missing compact array section')
    i=starts[0];state=operand_bundle(lines[:i]+['VA_END'],identities)
    state['arrays']=array_parse(expand(lines[i:-1]))
    if state['arrays']['tick']!=state['threads']['tick']:raise ValueError('Array observation time mismatch')
    return state


class ArrayState:
    def __init__(self,compiled):
        profile=array_profile(compiled);ports=collections.Counter(p['array'] for p in profile['ports'])
        self.expected=collections.Counter((a['words'],a['width'],a['msb'],a['lsb'],ports[a['label']]) for a in profile['arrays'])
        self.layout=None;self.observations=0;self.initial=False;self.loaded=False;self.cached=False;self.addresses={}
    def observe(self,state):
        snapshot=state['arrays'];array_validate(snapshot)
        if snapshot['tick']!=state['threads']['tick']:raise ValueError('Wrong array boundary time')
        actual=collections.Counter((a['size'],a['width'],a['msb'],a['lsb'],sum(p['array']==a['id'] for p in snapshot['ports'])) for a in snapshot['arrays'])
        if actual!=self.expected:raise ValueError('Native arrays differ from compiled board')
        layout=([ {k:v for k,v in a.items() if k not in ('words','cache','cacheParent','cacheWords')} for a in snapshot['arrays']],
                [{k:v for k,v in p.items() if k!='address'} for p in snapshot['ports']])
        if self.layout is None:self.layout=layout
        if layout!=self.layout:raise ValueError('Changed array/storage/read-port identity')
        scope_keys={s['pointer'] for s in state['scopes']}
        if any(a['scope'] not in scope_keys for a in snapshot['arrays']):raise ValueError('Array owner missing from scope inventory')
        unwritten=all(set(w)=={'3'} for a in snapshot['arrays'] for w in a['words'])
        if self.observations==0:
            if not unwritten or any(a['cache'] for a in snapshot['arrays']):raise ValueError('Expected unwritten startup array state')
            self.initial=True
        self.loaded|=not unwritten;self.cached|=any(a['cache'] for a in snapshot['arrays'])
        for p in snapshot['ports']:self.addresses.setdefault(p['id'],set()).add(p['address'])
        self.observations+=1
    def changed(self,before,after,fault_type):
        if fault_type not in FAULTS:raise ValueError('Unknown array fault')
        if {k:v for k,v in before.items() if k!='arrays'}!={k:v for k,v in after.items() if k!='arrays'}:raise ValueError('Array fault changed unrelated board state')
        array_changed(before['arrays'],after['arrays'],FAULTS[fault_type])
    def result(self,negative):
        changed=sum(len(v)>1 for v in self.addresses.values())
        if not self.initial or not self.observations or (not negative and (not self.loaded or not self.cached or not changed)):raise ValueError('Missing operational array coverage')
        return dict(arrayObservations=self.observations,arrays=len(self.layout[0]),arrayReadPorts=len(self.layout[1]),loadedArrayStateObserved=self.loaded,wordHandleCacheObserved=self.cached,readPortsWithAddressChanges=changed)


def inventory(path,identities,*,fault_type=None,contract=None,compiled=None):
    if fault_type is not None and fault_type not in FAULTS:raise ValueError('Unknown fault type')
    primitives=PrimitiveLifetimes();island_lifetimes=IslandLifetimes();filters=FilterLifetimes();threads=ThreadLifetimes();waits=WaitLifetimes();codes=CodeBindings();scopes=ScopeMembership();operands=OperandState(compiled);arrays=ArrayState(compiled);reference_lines=[]
    ordinal=0;boundary=None;stages={};stage=None;lines=[];fault=None
    display=released=saved=cleared=executing=empty=0;event_links={};callback_links={}
    markers={name:f'VB_ARRAY_FAULT field={field} changed=1 restored=1' for name,field in FAULTS.items()}
    layout=None;port_observations=0;output_layout=None;output_observations=0
    startup_id=None;startup_phase=1;active_start=finished_start=0
    assignment_ids={};previous_ids=set();retired_ids=set();assignment_counts={4:0,8:0};empty_assignments=0;unsupported_max=0
    for line in records(path,('VB_','VA_','VF_','VD_','VJ_','VR_','VE_','VP_','VW_','VS_','VAP_','VPR_','VI_','VIQ_','VIF_','VT_','VTQ_','VWE_','VTC_','VSC_','VCO_','VAC_','VAR_')):
        a=line.split();kind=a[0]
        if fault is not None:raise ValueError('Continuation after fault')
        if reference_lines:
            if not kind.startswith('VCO_'):raise ValueError('Interrupted reference image')
            reference_lines.append(line)
            if kind=='VCO_END':operands.set_reference(reference_lines);reference_lines=[]
            continue
        if kind=='VCO_BEGIN' and boundary is None:
            if ordinal or operands.reference is not None:raise ValueError('Late or duplicate reference image')
            reference_lines=[line];continue
        if kind=='VB_BRIDGE':
            if operands.reference is None:raise ValueError('Missing initial operand reference')
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
        elif kind=='VA_END' or kind.startswith(('VF_','VD_','VJ_','VR_','VE_','VP_','VW_','VS_','VAP_','VPR_','VI_','VIQ_','VIF_','VT_','VTQ_','VWE_','VTC_','VSC_','VCO_','VAC_','VAR_')):
            if not lines:raise ValueError('Orphan observer record')
            lines.append(line)
            if kind=='VA_END':stages[stage]=(lines,bundle(lines,identities));lines=[]
        elif kind in ('VB_STABLE','VB_ARRAY_FAULT'):
            if boundary is None or lines:raise ValueError('Incomplete boundary')
            if kind=='VB_STABLE':
                if line!='VB_STABLE equal=1' or list(stages)!=['before','repeat'] or stages['before'][0]!=stages['repeat'][0]:raise ValueError('Observer changed state')
            else:
                expected=['before','changed','restored']
                if fault_type is None or line!=markers[fault_type] or list(stages)!=expected:raise ValueError('Wrong fault control')
                if stages['before'][0]!=stages['restored'][0]:raise ValueError('Fault not restored')
                if fault_type=='link' and (boundary['index']!=0 or boundary['targetSeconds']!=0):raise ValueError('Array fault missed paused startup')
                if fault_type in ('word','address','cache') and boundary['targetSeconds']<5e-6:raise ValueError('Array fault missed later boundary')
                arrays.changed(stages['before'][1],stages['changed'][1],fault_type)
                fault=dict(boundary)
            state=stages['before'][1]
            codes.observe(state)
            scopes.observe(state)
            operands.observe(state)
            arrays.observe(state)
            waits.observe(state)
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
            if fault is not None and startup_phase!=(2 if fault_type in ('word','address','cache') else 1):raise ValueError('Wrong fault lifecycle phase')
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
    if reference_lines or boundary is not None or lines or not ordinal or (fault is None and ordinal%2):raise ValueError('Incomplete observations')
    if not active_start or (fault_type is None and (not finished_start or not executing or not empty or not saved or not cleared or not display or not released)):raise ValueError('Missing startup or later board state coverage')
    if not assignment_counts[4] or not assignment_counts[8] or (fault_type is None and not empty_assignments):raise ValueError('Missing assignment family or consumption coverage')
    if fault_type and fault is None:raise ValueError('Unexercised fault')
    return {**arrays.result(fault_type is not None),**operands.result(),**scopes.result(fault_type is not None),**codes.result(fault_type is not None),**waits.result(fault_type is not None),**threads.result(fault_type is not None),**filters.result(fault_type is not None),**island_lifetimes.result(fault_type is not None),**primitives.result(fault_type is not None),'assignmentObservations':assignment_counts,'uniqueAssignments':len(assignment_ids),'emptyAssignmentBoundaries':empty_assignments,'maximumUncoveredEvents':unsupported_max,'startupLifetimeId':startup_id,'activeStartupObservations':active_start,'destroyedStartupObservations':finished_start,'boundaries':ordinal,'executingWrapperObservations':executing,'emptyFrameObservations':empty,
            'uniqueExecutingEvents':len(event_links),'associatedDisplayObservations':display,'releasedDisplayObservations':released,
            'savedStopObservations':saved,'clearedStopObservations':cleared,'portObservations':port_observations,'ports':layout,'outputCallbackObservations':output_observations,'outputCallbacks':output_layout,'fault':fault}


def assess(root,producer):
    names=('baseline','off','observe','word-corrupt','address-corrupt','link-corrupt','cache-corrupt')
    runs={n:json.loads((root/n/'run.json').read_text()) for n in names}
    profile=compiled_contract((root/'baseline/io.vvp').read_text())
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
            if r.get('captureTimeoutSeconds')!=1800:raise ValueError('Changed array capture budget')
            if r.get('compiledThreadProfile')!=profile or r.get('threadContractSourceSha256')!=sha(Path(board_thread_contract.__file__)):raise ValueError('Changed compiled thread contract')
            if r['mode']!=mode or r['producerSha256']!=sha(producer):raise ValueError('Changed producer/mode')
            for key,path in [('baselineReceiptSha256','baseline/run.json'),('baselineAssessmentSha256','baseline-assessment.json'),('bridgeBuildSha256','bridge-build.json'),('icarusBuildSha256','icarus-build.json'),('symbolReceiptSha256','symbols.json')]:
                if r[key]!=sha(root/path):raise ValueError('Changed '+key)
            expected=dict(base['environment'],ROBOTRON_DISPLAY_MODULE=dep(runs['off'],'system.vpi')['path'],ROBOTRON_PRIVATE_DISPLAY='array-'+mode if negative else mode)
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
        if next(records(root/mode/'ngspice.log',('VB_','VA_','VF_','VD_','VJ_','VR_','VE_','VP_','VW_','VS_','VAP_','VPR_','VI_','VIQ_','VIF_','VT_','VTQ_','VWE_','VTC_','VSC_','VCO_','VAC_','VAR_')),None) is not None:raise ValueError('Disabled observer emitted records')
    contract=port_contract((root/'baseline/io.vvp').read_text())
    observed=inventory(root/'observe/ngspice.log',identities,contract=contract,compiled=(root/'baseline/io.vvp').read_text())
    if observed['scopeCount']!=len(analyze((root/'baseline/io.vvp').read_text())['scopes']):raise ValueError('Scope inventory differs from compiled board')
    expected={}
    for line in (root/'baseline/io.vvp').read_text().splitlines():
        if ' .event' not in line:continue
        kind=3 if ' .event/or ' in line else 2 if ' .event anyedge,' in line else 1
        expected[kind]=expected.get(kind,0)+1
    actual={}
    # The native counts are checked in each boundary through a fixed event-kind layout.
    for kind,count in observed['waitEventKinds'].items():actual[int(kind)]=count
    if actual!=expected:raise ValueError('Wait-event inventory differs from compiled board')
    negatives={mode:inventory(root/mode/'ngspice.log',identities,fault_type=mode.removesuffix('-corrupt'),contract=contract,compiled=(root/'baseline/io.vvp').read_text()) for mode in ('word-corrupt','address-corrupt','link-corrupt','cache-corrupt')}
    comparisons={}
    for label,left,right in [('disabledBaseline','baseline','off'),('enabledObserver','off','observe')]:
        comparisons[label]=compare_raw(root/left/'waveform.raw',root/right/'waveform.raw',[scans[n]['count'] for n in (left,right)],20e-6,exact=True)
        if not equal(root/left/'ngspice.log',root/right/'ngspice.log',FIRMWARE):raise ValueError('Changed firmware continuation')
    return {'compiledThreadProfile':profile,'reviewCompleted':True,'qualified':False,'controlsPassed':True,'comparisons':comparisons,'firmwareRecordsExactlyEqual':True,
            'observedState':observed,'negativeControls':negatives,'receipts':receipts,
            'scope':'Complete 20-us service fixture, reset at 1 us. Complete compact array images observed with all preceding board layers. Word/address/cache faults restore after 5 us; link faults restore at startup. Normal controls preserve exact waveform samples and firmware continuation.',
            'notEstablished':['Referenced operand objects, nonempty event-control payloads and scope intern contents and deep context/object/callback/fanout referents','Reachable detached/deferred-deletion paths, freed-storage equivalence or general rollback','Full post-reset/startup/repeat/supply recovery qualification']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('root','producer','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();result=assess(a.root,a.producer)
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
