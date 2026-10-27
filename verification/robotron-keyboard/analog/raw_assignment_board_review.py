#!/usr/bin/env python3
"""Review raw strength assignments with all preceding combined board checks."""
from raw_island_board_review import *
from raw_island_board_review import bundle as prior_bundle
from assignment_raw import parse as assignment_raw_parse,bind as assignment_raw_bind,mutation as assignment_raw_mutation
from wire_raw_probe import triplet
FAULTS={'raw-assignment-byte':0,'raw-assignment-width':2,'raw-assignment-port':3}

def bundle(lines,identities):
    starts=[i for i,l in enumerate(lines) if l.startswith('VAR_BEGIN ')]
    if len(starts)!=1 or lines[-1]!='VA_END':raise ValueError('Missing raw assignment section')
    i=starts[0]
    if not any(l.startswith('VIX_BEGIN ') for l in lines[:i]):raise ValueError('Raw assignment section before raw islands')
    state=prior_bundle(lines[:i]+['VA_END'],identities);raw=assignment_raw_parse(lines[i:-1])
    if raw['tick']!=state['threads']['tick']:raise ValueError('Raw assignment time mismatch')
    state['assignmentRaw']=raw;return state

class RawAssignmentState:
    def __init__(self):
        self.identities={};self.previous=set();self.retired=set();self.observations=0;self.maximum=0;self.pending=0;self.executing=0
    def observe(self,state,graph,signals):
        raw=state['assignmentRaw'];assignment_raw_bind(raw,state['assignments'])
        if raw['tick']!=state['threads']['tick']:raise ValueError('Raw assignment time mismatch')
        if signals.types is None:raise ValueError('Missing assignment target classes')
        nodes={n['key']:n for n in graph.nodes};types={n['key']:n for n in signals.types['nodes']};current=set()
        for e in raw['events']:
            key=int(e['target'],16);node=nodes.get(key);native=types.get(key)
            if not node or not native or not node['fun'] or any(node[k]!=native[k] for k in ('id','fun','filter')):raise ValueError('Raw assignment destination outside admitted graph/classes')
            identity=e['id'];intrinsic=(e['address'],e['target'],e['port'],e['raw'])
            if identity in self.retired or self.identities.setdefault(identity,intrinsic)!=intrinsic:raise ValueError('Raw assignment lifetime reused or payload changed')
            current.add(identity)
            if e['region']=='executing':self.executing+=1
            else:self.pending+=1
        self.retired.update(self.previous-current);self.previous=current
        self.observations+=1;self.maximum=max(self.maximum,sum(len(e['raw']) for e in raw['events']))
    def changed(self,before,after,fault_type):
        if {k:v for k,v in before.items() if k not in ('assignmentRaw','assignments')}!={k:v for k,v in after.items() if k not in ('assignmentRaw','assignments')}:raise ValueError('Raw assignment fault changed preceding state')
        op=FAULTS[fault_type];raw=before['assignmentRaw'];target=next((e for e in raw['events'] if op!=0 or e['raw']),None)
        if target is None:raise ValueError('Missing raw assignment fault target')
        expected=assignment_raw_mutation(raw,target['id'],op)
        if after['assignmentRaw']!=expected:raise ValueError('Wrong raw assignment mutation')
        assignment_raw_bind(raw,before['assignments']);assignment_raw_bind(expected,after['assignments'])
        legacy=copy.deepcopy(before['assignments']);changed=next(e for e in expected['events'] if e['id']==target['id'])
        for e in legacy['events']:
            if e['kind']==8 and e['id']==target['id']:
                e.update(port=changed['port'],size=len(changed['raw']),bits=''.join(triplet(x) for x in changed['raw']) or '-')
        if legacy!=after['assignments']:raise ValueError('Raw assignment fault changed unrelated legacy state')
    def result(self):
        if not self.observations or not self.pending:raise ValueError('Missing raw assignment board observations')
        return dict(rawAssignmentObservations=self.observations,pendingRawAssignments=self.pending,executingRawAssignments=self.executing,uniqueRawAssignmentLifetimes=len(self.identities),maximumRawAssignmentBytes=self.maximum)

def inventory(path,identities,*,fault_type=None,contract=None,compiled=None):
    if fault_type is not None and fault_type not in FAULTS:raise ValueError('Unknown fault type')
    primitives=PrimitiveLifetimes();island_lifetimes=IslandLifetimes();filters=FilterLifetimes();threads=ThreadLifetimes();waits=WaitLifetimes();codes=CodeBindings();scopes=ScopeMembership();operands=OperandState(compiled);arrays=ArrayState(compiled);graph=GraphState(compiled);wires=WireState();signals=SignalState(compiled);muxes=MuxState(compiled);gates=GateState(compiled);arithmetic=ArithmeticState(compiled);reduction=ReductionState(compiled);raw=RawWireState();concat=ConcatState(compiled);resolver=ResolverState(compiled);israw=RawIslandState(compiled);assignraw=RawAssignmentState();israw_lines=[];resolver_lines=[];concat_lines=[];raw_lines=[];reduction_lines=[];arithmetic_lines=[];gate_lines=[];mux_lines=[];reference_lines=[];graph_lines=[];wire_lines=[];signal_lines=[];type_lines=[]
    ordinal=0;boundary=None;stages={};stage=None;lines=[];fault=None
    display=released=saved=cleared=executing=empty=0;event_links={};callback_links={}
    markers={name:f'VB_RAW_ASSIGNMENT_FAULT operation={op} changed=1 restored=1' for name,op in FAULTS.items()}
    layout=None;port_observations=0;output_layout=None;output_observations=0
    startup_id=None;startup_phase=1;active_start=finished_start=0
    assignment_ids={};previous_ids=set();retired_ids=set();assignment_counts={4:0,8:0};empty_assignments=0;unsupported_max=0
    for line in records(path,('VB_','VA_','VF_','VD_','VJ_','VR_','VE_','VP_','VW_','VS_','VAP_','VPR_','VI_','VIQ_','VIF_','VT_','VTQ_','VWE_','VTC_','VSC_','VCO_','VAC_','VAR_','VND_','VNG_','VWD_','VSD_','VNT_','VXD_','VXM_','VGD_','VAD_','VRE_','VWC_','VCD_','VRX_','VIX_')):
        a=line.split();kind=a[0]
        if fault is not None:raise ValueError('Continuation after fault')
        if israw_lines:
            if not kind.startswith('VIX_'):raise ValueError('Interrupted raw island reference')
            israw_lines.append(line)
            if kind=='VIX_END':israw.set_reference(israw_lines,graph,signals);israw_lines=[]
            continue
        if kind=='VIX_BEGIN' and boundary is None:
            if ordinal or israw.reference is not None:raise ValueError('Late/duplicate raw island reference')
            israw_lines=[line];continue
        if resolver_lines:
            if not kind.startswith('VRX_'):raise ValueError('Interrupted resolver reference')
            resolver_lines.append(line)
            if kind=='VRX_END':resolver.set_reference(resolver_lines,graph,signals);resolver_lines=[]
            continue
        if kind=='VRX_BEGIN' and boundary is None:
            if ordinal or resolver.reference is not None:raise ValueError('Late/duplicate resolver reference')
            resolver_lines=[line];continue
        if concat_lines:
            if not kind.startswith(('VCD_','VXM_EVENT')):raise ValueError('Interrupted concat reference')
            concat_lines.append(line)
            if kind=='VCD_END':concat.set_reference(concat_lines,graph,signals);concat_lines=[]
            continue
        if kind=='VCD_BEGIN' and boundary is None:
            if ordinal or concat.reference is not None:raise ValueError('Late/duplicate concat reference')
            concat_lines=[line];continue
        if raw_lines:
            if not kind.startswith('VWC_'):raise ValueError('Interrupted raw-wire reference')
            raw_lines.append(line)
            if kind=='VWC_END':raw.set_reference(raw_lines,graph,signals,wires);raw_lines=[]
            continue
        if kind=='VWC_BEGIN' and boundary is None:
            if ordinal or raw.reference is not None:raise ValueError('Late/duplicate raw-wire reference')
            raw_lines=[line];continue
        if reduction_lines:
            if not kind.startswith('VRE_'):raise ValueError('Interrupted reduction reference')
            reduction_lines.append(line)
            if kind=='VRE_END':reduction.set_reference(reduction_lines,graph,signals);reduction_lines=[]
            continue
        if kind=='VRE_BEGIN' and boundary is None:
            if ordinal or reduction.reference is not None:raise ValueError('Late/duplicate reduction reference')
            reduction_lines=[line];continue
        if arithmetic_lines:
            if not kind.startswith('VAD_'):raise ValueError('Interrupted arithmetic reference')
            arithmetic_lines.append(line)
            if kind=='VAD_END':arithmetic.set_reference(arithmetic_lines,graph,signals);arithmetic_lines=[]
            continue
        if kind=='VAD_BEGIN' and boundary is None:
            if ordinal or arithmetic.reference is not None:raise ValueError('Late/duplicate arithmetic reference')
            arithmetic_lines=[line];continue
        if gate_lines:
            if not kind.startswith(('VGD_','VXM_EVENT')):raise ValueError('Interrupted gate reference')
            gate_lines.append(line)
            if kind=='VGD_END':gates.set_reference(gate_lines,graph,signals);gate_lines=[]
            continue
        if kind=='VGD_BEGIN' and boundary is None:
            if ordinal or gates.reference is not None:raise ValueError('Late/duplicate gate reference')
            gate_lines=[line];continue
        if mux_lines:
            if not kind.startswith(('VXD_','VXM_EVENT')):raise ValueError('Interrupted mux reference')
            mux_lines.append(line)
            if kind=='VXD_END':muxes.set_reference(mux_lines,graph,signals);mux_lines=[]
            continue
        if kind=='VXD_BEGIN' and boundary is None:
            if ordinal or muxes.reference is not None:raise ValueError('Late/duplicate mux reference')
            mux_lines=[line];continue
        if type_lines:
            if not kind.startswith('VNT_'):raise ValueError('Interrupted class reference')
            type_lines.append(line)
            if kind=='VNT_END':signals.set_types(type_lines,graph);type_lines=[]
            continue
        if kind=='VNT_BEGIN' and boundary is None:
            if ordinal or signals.types is not None:raise ValueError('Late/duplicate class reference')
            type_lines=[line];continue
        if signal_lines:
            if not kind.startswith('VSD_'):raise ValueError('Interrupted signal reference')
            signal_lines.append(line)
            if kind=='VSD_END':signals.set_reference(signal_lines);signal_lines=[]
            continue
        if kind=='VSD_BEGIN' and boundary is None:
            if ordinal or signals.reference is not None:raise ValueError('Late/duplicate signal reference')
            signal_lines=[line];continue
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
            if operands.reference is None or graph.reference is None or wires.reference is None or signals.reference is None or signals.types is None or muxes.reference is None or gates.reference is None or arithmetic.reference is None or reduction.reference is None or raw.reference is None or concat.reference is None or resolver.reference is None or israw.reference is None:raise ValueError('Missing initial reference')
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
        elif kind=='VA_END' or kind.startswith(('VF_','VD_','VJ_','VR_','VE_','VP_','VW_','VS_','VAP_','VPR_','VI_','VIQ_','VIF_','VT_','VTQ_','VWE_','VTC_','VSC_','VCO_','VAC_','VAR_','VND_','VNG_','VWD_','VSD_','VNT_','VXD_','VXM_','VGD_','VAD_','VRE_','VWC_','VCD_','VRX_','VIX_')):
            if not lines:raise ValueError('Orphan observer record')
            lines.append(line)
            if kind=='VA_END':stages[stage]=(lines,bundle(lines,identities));lines=[]
        elif kind in ('VB_STABLE','VB_RAW_ASSIGNMENT_FAULT'):
            if boundary is None or lines:raise ValueError('Incomplete boundary')
            if kind=='VB_STABLE':
                if line!='VB_STABLE equal=1' or list(stages)!=['before','repeat'] or stages['before'][0]!=stages['repeat'][0]:raise ValueError('Observer changed state')
            else:
                expected=['before','changed','restored']
                if fault_type is None or line!=markers[fault_type] or list(stages)!=expected:raise ValueError('Wrong fault control')
                if stages['before'][0]!=stages['restored'][0]:raise ValueError('Fault not restored')
                if boundary['index']!=0 or boundary['targetSeconds']!=0:raise ValueError('Raw assignment fault missed paused startup')
                assignraw.changed(stages['before'][1],stages['changed'][1],fault_type)
                fault=dict(boundary)
            state=stages['before'][1]
            codes.observe(state)
            scopes.observe(state)
            operands.observe(state)
            arrays.observe(state)
            graph.observe(state,operands)
            wires.observe(state,graph)
            signals.observe(state,graph)
            muxes.observe(state,graph)
            gates.observe(state,graph)
            arithmetic.observe(state,graph)
            reduction.observe(state,graph)
            raw.observe(state,graph,wires)
            concat.observe(state,graph)
            resolver.observe(state,graph)
            israw.observe(state,graph)
            assignraw.observe(state,graph,signals)
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
            if fault is not None and startup_phase!=1:raise ValueError('Wrong fault lifecycle phase')
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
    if israw_lines or resolver_lines or concat_lines or raw_lines or reduction_lines or arithmetic_lines or gate_lines or mux_lines or signal_lines or type_lines or wire_lines or graph_lines or reference_lines or boundary is not None or lines or not ordinal or (fault is None and ordinal%2):raise ValueError('Incomplete observations')
    if not active_start or (fault_type is None and (not finished_start or not executing or not empty or not saved or not cleared or not display or not released)):raise ValueError('Missing startup or later board state coverage')
    if not assignment_counts[4] or not assignment_counts[8] or (fault_type is None and not empty_assignments):raise ValueError('Missing assignment family or consumption coverage')
    if fault_type and fault is None:raise ValueError('Unexercised fault')
    return {**assignraw.result(),**israw.result(),**resolver.result(),**concat.result(),**raw.result(),**reduction.result(),**arithmetic.result(),**gates.result(),**muxes.result(),**signals.result(),**wires.result(),**graph.result(fault_type is not None),**arrays.result(fault_type is not None),**operands.result(),**scopes.result(fault_type is not None),**codes.result(fault_type is not None),**waits.result(fault_type is not None),**threads.result(fault_type is not None),**filters.result(fault_type is not None),**island_lifetimes.result(fault_type is not None),**primitives.result(fault_type is not None),'assignmentObservations':assignment_counts,'uniqueAssignments':len(assignment_ids),'emptyAssignmentBoundaries':empty_assignments,'maximumUncoveredEvents':unsupported_max,'startupLifetimeId':startup_id,'activeStartupObservations':active_start,'destroyedStartupObservations':finished_start,'boundaries':ordinal,'executingWrapperObservations':executing,'emptyFrameObservations':empty,
            'uniqueExecutingEvents':len(event_links),'associatedDisplayObservations':display,'releasedDisplayObservations':released,
            'savedStopObservations':saved,'clearedStopObservations':cleared,'portObservations':port_observations,'ports':layout,'outputCallbackObservations':output_observations,'outputCallbacks':output_layout,'fault':fault}


def assess(root,producer):
    names=('baseline','off','observe','raw-assignment-byte-corrupt','raw-assignment-width-corrupt','raw-assignment-port-corrupt')
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
            if r.get('captureTimeoutSeconds')!=3300:raise ValueError('Changed raw island capture budget')
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
        if next(records(root/mode/'ngspice.log',('VB_','VA_','VF_','VD_','VJ_','VR_','VE_','VP_','VW_','VS_','VAP_','VPR_','VI_','VIQ_','VIF_','VT_','VTQ_','VWE_','VTC_','VSC_','VCO_','VAC_','VAR_','VND_','VNG_','VWD_','VSD_','VNT_','VXD_','VXM_','VGD_','VAD_','VRE_','VWC_','VCD_','VRX_','VIX_')),None) is not None:raise ValueError('Disabled observer emitted records')
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
    negatives={mode:inventory(root/mode/'ngspice.log',identities,fault_type=mode.removesuffix('-corrupt'),contract=contract,compiled=(root/'baseline/io.vvp').read_text()) for mode in ('raw-assignment-byte-corrupt','raw-assignment-width-corrupt','raw-assignment-port-corrupt')}
    comparisons={}
    for label,left,right in [('disabledBaseline','baseline','off'),('enabledObserver','off','observe')]:
        comparisons[label]=compare_raw(root/left/'waveform.raw',root/right/'waveform.raw',[scans[n]['count'] for n in (left,right)],20e-6,exact=True)
        if not equal(root/left/'ngspice.log',root/right/'ngspice.log',FIRMWARE):raise ValueError('Changed firmware continuation')
    return {'compiledThreadProfile':profile,'reviewCompleted':True,'qualified':False,'controlsPassed':True,'comparisons':comparisons,'firmwareRecordsExactlyEqual':True,
            'observedState':observed,'negativeControls':negatives,'receipts':receipts,
            'scope':'Complete 20-us service fixture with reset at 1 us. Complete raw strength assignments bind pending payloads to legacy identities and every destination to admitted graph/classes; executing payloads remain explicit. Byte/width/port faults restore at paused startup. All preceding raw-island and other layers remain checked. Normal waveforms and firmware must match exactly. Native collision and subclass controls remain independent evidence.',
            'notEstablished':['Referenced operand objects, nonempty event-control payloads and scope intern contents and deep context/object/callback/fanout referents','Reachable detached/deferred-deletion paths, freed-storage equivalence or general rollback','Full post-reset/startup/repeat/supply recovery qualification']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('root','producer','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();result=assess(a.root,a.producer)
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
