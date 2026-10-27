#!/usr/bin/env python3
"""Review wire payload deltas with complete preceding board state checks."""
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
from array_board_review import bundle as array_bundle,ArrayState
from net_source_contract import profile as graph_profile
from net_delta_probe import block as graph_block,reconstruct
from net_probe import parse as graph_parse,validate as graph_validate,changed as graph_changed
import collections
from thread_board_reachability import analyze
from board_thread_contract import compiled_contract,validate_snapshot as validate_board_threads
import board_thread_contract
from port_board_review import port_contract
from stop_board_review import startup_identity

from net_board_review import bundle as net_bundle,GraphState
from wire_delta_probe import block as wire_block,reconstruct as wire_reconstruct
from wire_probe import parse as wire_parse,changed as wire_changed
FAULTS={f'wire{k}-{name}':(k,field) for k in (4,8) for name,field in [('init',0),('driven',1),('propagate',4)]}
HERE=Path(__file__).resolve().parent


def bundle(lines,identities):
    starts=[i for i,l in enumerate(lines) if l.startswith('VWD_BEGIN ')]
    if len(starts)!=1 or lines[-1]!='VA_END':raise ValueError('Missing wire delta section')
    i=starts[0];state=net_bundle(lines[:i]+['VA_END'],identities)
    frame,end=wire_block(lines[i:-1])
    if end!=len(lines[i:-1]) or frame['mode']!='D' or frame['tick']!=state['threads']['tick']:raise ValueError('Wrong wire framing/time')
    state['wires']=frame;return state


class WireState:
    def __init__(self):
        self.reference=None;self.observations=0;self.maximum=0;self.kinds=set();self.signature=None;self.cached=None
    def set_reference(self,lines):
        if self.reference is not None:raise ValueError('Wire reference reset')
        frame,end=wire_block(lines)
        if end!=len(lines) or frame['mode']!='R' or frame['tick']!=0:raise ValueError('Invalid initial wires')
        self.reference=frame['rows']
    def image(self,frame):
        if self.reference is None:raise ValueError('Missing wire reference')
        signature=(frame['total'],tuple(frame['rows'].items()))
        if signature!=self.signature:
            self.cached=wire_parse(wire_reconstruct(self.reference,frame));self.signature=signature
        # Tick is explicit even when content is unchanged; no native scan is skipped.
        return dict(self.cached,tick=frame['tick'])
    def observe(self,state,graph):
        snapshot=self.image(state['wires'])
        if snapshot['tick']!=state['threads']['tick']:raise ValueError('Wire boundary mismatch')
        expected=[n for n in graph.nodes if n['filter']]
        if len(expected)!=len(snapshot['filters']):raise ValueError('Missing allocated wire filter')
        for n,w in zip(expected,snapshot['filters']):
            if (n['id'],n['key'],n['filter'])!=(w['id'],w['node'],w['pointer']):raise ValueError('Wire binding differs from allocated graph')
            self.kinds.add(w['kind'])
        self.check_aliases(state,snapshot)
        self.observations+=1;self.maximum=max(self.maximum,len(expected))
    @staticmethod
    def check_aliases(state,snapshot):
        wires={w['pointer']:w for w in snapshot['filters']}
        for port in state['filters']['ports']:
            wire=wires.get(port['pointer'])
            if wire is None or wire['kind']!=8:raise ValueError('Missing island wire alias')
            if any(wire[k]!=v for k,v in port.items() if k not in ('island','port')):raise ValueError('Island/wire payload mismatch')
    def changed(self,before,after,fault_type):
        if {k:v for k,v in before.items() if k not in ('wires','filters')}!={k:v for k,v in after.items() if k not in ('wires','filters')}:raise ValueError('Wire fault changed preceding state')
        first,last=self.image(before['wires']),self.image(after['wires'])
        wire_changed(first,last,*FAULTS[fault_type])
        self.check_aliases(before,first);self.check_aliases(after,last)
        # The island observer may see the same filter mutation, but its ownership cannot change.
        fields=('island','port','pointer')
        if before['filters']['tick']!=after['filters']['tick'] or [tuple(p[k] for k in fields) for p in before['filters']['ports']]!=[tuple(p[k] for k in fields) for p in after['filters']['ports']]:raise ValueError('Wire fault changed island ownership')
    def result(self):
        if not self.observations or self.kinds!={4,8}:raise ValueError('Missing wire family coverage')
        return dict(wireObservations=self.observations,maximumWireFilters=self.maximum,wireKinds=sorted(self.kinds))


def inventory(path,identities,*,fault_type=None,contract=None,compiled=None):
    if fault_type is not None and fault_type not in FAULTS:raise ValueError('Unknown fault type')
    primitives=PrimitiveLifetimes();island_lifetimes=IslandLifetimes();filters=FilterLifetimes();threads=ThreadLifetimes();waits=WaitLifetimes();codes=CodeBindings();scopes=ScopeMembership();operands=OperandState(compiled);arrays=ArrayState(compiled);graph=GraphState(compiled);wires=WireState();reference_lines=[];graph_lines=[];wire_lines=[]
    ordinal=0;boundary=None;stages={};stage=None;lines=[];fault=None
    display=released=saved=cleared=executing=empty=0;event_links={};callback_links={}
    markers={name:f'VB_WIRE_FAULT kind={kind} field={field} changed=1 restored=1' for name,(kind,field) in FAULTS.items()}
    layout=None;port_observations=0;output_layout=None;output_observations=0
    startup_id=None;startup_phase=1;active_start=finished_start=0
    assignment_ids={};previous_ids=set();retired_ids=set();assignment_counts={4:0,8:0};empty_assignments=0;unsupported_max=0
    for line in records(path,('VB_','VA_','VF_','VD_','VJ_','VR_','VE_','VP_','VW_','VS_','VAP_','VPR_','VI_','VIQ_','VIF_','VT_','VTQ_','VWE_','VTC_','VSC_','VCO_','VAC_','VAR_','VND_','VNG_','VWD_')):
        a=line.split();kind=a[0]
        if fault is not None:raise ValueError('Continuation after fault')
        if wire_lines:
            if not kind.startswith('VWD_'):raise ValueError('Interrupted wire reference')
            wire_lines.append(line)
            if kind=='VWD_END':wires.set_reference(wire_lines);wire_lines=[]
            continue
        if kind=='VWD_BEGIN' and boundary is None:
            if ordinal or wires.reference is not None:raise ValueError('Late/duplicate wire reference')
            wire_lines=[line];continue
        if graph_lines:
            if not kind.startswith(('VND_','VNG_')):raise ValueError('Interrupted graph reference')
            graph_lines.append(line)
            if kind=='VND_END':graph.set_reference(graph_lines);graph_lines=[]
            continue
        if kind=='VND_BEGIN' and boundary is None:
            if ordinal or graph.reference is not None:raise ValueError('Late/duplicate graph reference')
            graph_lines=[line];continue
        if reference_lines:
            if not kind.startswith('VCO_'):raise ValueError('Interrupted reference image')
            reference_lines.append(line)
            if kind=='VCO_END':operands.set_reference(reference_lines);reference_lines=[]
            continue
        if kind=='VCO_BEGIN' and boundary is None:
            if ordinal or operands.reference is not None:raise ValueError('Late or duplicate reference image')
            reference_lines=[line];continue
        if kind=='VB_BRIDGE':
            if operands.reference is None or graph.reference is None or wires.reference is None:raise ValueError('Missing initial reference')
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
        elif kind=='VA_END' or kind.startswith(('VF_','VD_','VJ_','VR_','VE_','VP_','VW_','VS_','VAP_','VPR_','VI_','VIQ_','VIF_','VT_','VTQ_','VWE_','VTC_','VSC_','VCO_','VAC_','VAR_','VND_','VNG_','VWD_')):
            if not lines:raise ValueError('Orphan observer record')
            lines.append(line)
            if kind=='VA_END':stages[stage]=(lines,bundle(lines,identities));lines=[]
        elif kind in ('VB_STABLE','VB_WIRE_FAULT'):
            if boundary is None or lines:raise ValueError('Incomplete boundary')
            if kind=='VB_STABLE':
                if line!='VB_STABLE equal=1' or list(stages)!=['before','repeat'] or stages['before'][0]!=stages['repeat'][0]:raise ValueError('Observer changed state')
            else:
                expected=['before','changed','restored']
                if fault_type is None or line!=markers[fault_type] or list(stages)!=expected:raise ValueError('Wrong fault control')
                if stages['before'][0]!=stages['restored'][0]:raise ValueError('Fault not restored')
                if FAULTS[fault_type][1]==0 and (boundary['index']!=0 or boundary['targetSeconds']!=0):raise ValueError('Wire fault missed paused startup')
                if FAULTS[fault_type][1]!=0 and boundary['targetSeconds']<5e-6:raise ValueError('Wire fault missed later boundary')
                wires.changed(stages['before'][1],stages['changed'][1],fault_type)
                fault=dict(boundary)
            state=stages['before'][1]
            codes.observe(state)
            scopes.observe(state)
            operands.observe(state)
            arrays.observe(state)
            graph.observe(state,operands)
            wires.observe(state,graph)
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
            if fault is not None and startup_phase!=(2 if FAULTS[fault_type][1]!=0 else 1):raise ValueError('Wrong fault lifecycle phase')
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
    if wire_lines or graph_lines or reference_lines or boundary is not None or lines or not ordinal or (fault is None and ordinal%2):raise ValueError('Incomplete observations')
    if not active_start or (fault_type is None and (not finished_start or not executing or not empty or not saved or not cleared or not display or not released)):raise ValueError('Missing startup or later board state coverage')
    if not assignment_counts[4] or not assignment_counts[8] or (fault_type is None and not empty_assignments):raise ValueError('Missing assignment family or consumption coverage')
    if fault_type and fault is None:raise ValueError('Unexercised fault')
    return {**wires.result(),**graph.result(fault_type is not None),**arrays.result(fault_type is not None),**operands.result(),**scopes.result(fault_type is not None),**codes.result(fault_type is not None),**waits.result(fault_type is not None),**threads.result(fault_type is not None),**filters.result(fault_type is not None),**island_lifetimes.result(fault_type is not None),**primitives.result(fault_type is not None),'assignmentObservations':assignment_counts,'uniqueAssignments':len(assignment_ids),'emptyAssignmentBoundaries':empty_assignments,'maximumUncoveredEvents':unsupported_max,'startupLifetimeId':startup_id,'activeStartupObservations':active_start,'destroyedStartupObservations':finished_start,'boundaries':ordinal,'executingWrapperObservations':executing,'emptyFrameObservations':empty,
            'uniqueExecutingEvents':len(event_links),'associatedDisplayObservations':display,'releasedDisplayObservations':released,
            'savedStopObservations':saved,'clearedStopObservations':cleared,'portObservations':port_observations,'ports':layout,'outputCallbackObservations':output_observations,'outputCallbacks':output_layout,'fault':fault}


def assess(root,producer):
    names=('baseline','off','observe','wire4-init-corrupt','wire4-driven-corrupt','wire4-propagate-corrupt','wire8-init-corrupt','wire8-driven-corrupt','wire8-propagate-corrupt')
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
            if r.get('captureTimeoutSeconds')!=3000:raise ValueError('Changed wire capture budget')
            if r.get('compiledThreadProfile')!=profile or r.get('threadContractSourceSha256')!=sha(Path(board_thread_contract.__file__)):raise ValueError('Changed compiled thread contract')
            if r['mode']!=mode or r['producerSha256']!=sha(producer):raise ValueError('Changed producer/mode')
            for key,path in [('baselineReceiptSha256','baseline/run.json'),('baselineAssessmentSha256','baseline-assessment.json'),('bridgeBuildSha256','bridge-build.json'),('icarusBuildSha256','icarus-build.json'),('symbolReceiptSha256','symbols.json')]:
                if r[key]!=sha(root/path):raise ValueError('Changed '+key)
            expected=dict(base['environment'],ROBOTRON_DISPLAY_MODULE=dep(runs['off'],'system.vpi')['path'],ROBOTRON_PRIVATE_DISPLAY=mode)
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
        if next(records(root/mode/'ngspice.log',('VB_','VA_','VF_','VD_','VJ_','VR_','VE_','VP_','VW_','VS_','VAP_','VPR_','VI_','VIQ_','VIF_','VT_','VTQ_','VWE_','VTC_','VSC_','VCO_','VAC_','VAR_','VND_','VNG_','VWD_')),None) is not None:raise ValueError('Disabled observer emitted records')
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
    negatives={mode:inventory(root/mode/'ngspice.log',identities,fault_type=mode.removesuffix('-corrupt'),contract=contract,compiled=(root/'baseline/io.vvp').read_text()) for mode in ('wire4-init-corrupt','wire4-driven-corrupt','wire4-propagate-corrupt','wire8-init-corrupt','wire8-driven-corrupt','wire8-propagate-corrupt')}
    comparisons={}
    for label,left,right in [('disabledBaseline','baseline','off'),('enabledObserver','off','observe')]:
        comparisons[label]=compare_raw(root/left/'waveform.raw',root/right/'waveform.raw',[scans[n]['count'] for n in (left,right)],20e-6,exact=True)
        if not equal(root/left/'ngspice.log',root/right/'ngspice.log',FIRMWARE):raise ValueError('Changed firmware continuation')
    return {'compiledThreadProfile':profile,'reviewCompleted':True,'qualified':False,'controlsPassed':True,'comparisons':comparisons,'firmwareRecordsExactlyEqual':True,
            'observedState':observed,'negativeControls':negatives,'receipts':receipts,
            'scope':'Complete 20-us service fixture, reset at 1 us. Wire payload deltas and allocation bindings observed with all preceding layers. Vec4/vec8 initialization faults restore at startup; driven-value and propagation faults restore after 5 us. Normal controls preserve exact waveform samples and firmware continuation.',
            'notEstablished':['Referenced operand objects, nonempty event-control payloads and scope intern contents and deep context/object/callback/fanout referents','Reachable detached/deferred-deletion paths, freed-storage equivalence or general rollback','Full post-reset/startup/repeat/supply recovery qualification']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('root','producer','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();result=assess(a.root,a.producer)
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
