#!/usr/bin/env python3
"""Review parameter faults at selected startup and later complete states."""
from raw_assignment_board_review import *
from callback_list_board_review import bundle as prior_bundle
from signal_handles import parse as typed_parse
from callback_signal_links import parse as link_parse
from callback_signal_board import SignalHandleState
from callback_delta import block as callback_block
from callback_list_board import CallbackListState
FAULTS={'callback-list-user':0,'callback-list-object':1,'callback-list-function':2,'callback-list-link':3}

from parameter_fault_fields import FIELDS as TYPED_FAULTS,toggle

FAULTS.update(TYPED_FAULTS)


def bundle(lines,identities):
    starts=[i for i,line in enumerate(lines) if line.startswith('VSH_BEGIN ')]
    links=[i for i,line in enumerate(lines) if line.startswith('VSL_BEGIN ')]
    if len(starts)!=1 or len(links)!=1 or starts[0]>=links[0] or lines[-1]!='VA_END':raise ValueError('Missing typed signal/link sections')
    i,j=starts[0],links[0];state=prior_bundle(lines[:i]+['VA_END'],identities)
    state['typedSignals']=typed_parse(lines[i:j]);state['callbackSignalLinks']=link_parse(lines[j:-1]);return state

def typed_changed(before,after,field,bindings):
    import copy
    expected=copy.deepcopy(before);toggle(expected['parameters'],field)
    if expected!=after:raise ValueError('Parameter fault changed wrong field or unrelated state')

def inventory(path,identities,*,fault_type=None,contract=None,compiled=None):
    if fault_type is not None and fault_type not in FAULTS:raise ValueError('Unknown fault type')
    primitives=PrimitiveLifetimes();island_lifetimes=IslandLifetimes();filters=FilterLifetimes();threads=ThreadLifetimes();waits=WaitLifetimes();codes=CodeBindings();scopes=ScopeMembership();operands=OperandState(compiled);arrays=ArrayState(compiled);graph=GraphState(compiled);wires=WireState();signals=SignalState(compiled);muxes=MuxState(compiled);gates=GateState(compiled);arithmetic=ArithmeticState(compiled);reduction=ReductionState(compiled);raw=RawWireState();concat=ConcatState(compiled);resolver=ResolverState(compiled);israw=RawIslandState(compiled);assignraw=RawAssignmentState();callbacks=CallbackListState();typed=SignalHandleState(compiled);handle_lines=[];callback_lines=[];binding_lines=[];israw_lines=[];resolver_lines=[];concat_lines=[];raw_lines=[];reduction_lines=[];arithmetic_lines=[];gate_lines=[];mux_lines=[];reference_lines=[];graph_lines=[];wire_lines=[];signal_lines=[];type_lines=[]
    ordinal=0;boundary=None;stages={};stage=None;lines=[];fault=None
    display=released=saved=cleared=executing=empty=0;event_links={};callback_links={}
    markers={name:f'VB_CALLBACK_LIST_FAULT field={op} direct_rejected=1 rejected=1 restored=1' for name,op in FAULTS.items()}
    markers.update({name:f'VB_PARAMETER_FAULT field={field} direct=1 changed={int(field<7)} rejected={int(field>=7)} restored=1' for name,field in TYPED_FAULTS.items()})
    layout=None;port_observations=0;output_layout=None;output_observations=0
    startup_id=None;startup_phase=1;active_start=finished_start=0
    assignment_ids={};previous_ids=set();retired_ids=set();assignment_counts={4:0,8:0};empty_assignments=0;unsupported_max=0
    for line in records(path,('VB_','VA_','VF_','VD_','VJ_','VR_','VE_','VP_','VW_','VS_','VAP_','VPR_','VI_','VIQ_','VIF_','VT_','VTQ_','VWE_','VTC_','VSC_','VCO_','VAC_','VAR_','VND_','VNG_','VWD_','VSD_','VNT_','VXD_','VXM_','VGD_','VAD_','VRE_','VWC_','VCD_','VRX_','VIX_','VLD_','VLB_','VHB_','VSH_','VSL_')):
        a=line.split();kind=a[0]
        if fault is not None:raise ValueError('Continuation after fault')
        if handle_lines:
            if not kind.startswith('VHB_'):raise ValueError('Interrupted typed handle binding')
            handle_lines.append(line)
            if kind=='VHB_END':typed.set_bindings(handle_lines);handle_lines=[]
            continue
        if kind=='VHB_BEGIN' and boundary is None:
            if ordinal or typed.bindings is not None:raise ValueError('Late/duplicate typed handle binding')
            handle_lines=[line];continue
        if binding_lines:
            if not kind.startswith('VLB_'):raise ValueError('Interrupted callback binding header')
            binding_lines.append(line)
            if kind=='VLB_END':callbacks.set_bindings(binding_lines);binding_lines=[]
            continue
        if kind=='VLB_BEGIN' and boundary is None:
            if ordinal or callbacks.bindings is not None:raise ValueError('Late/duplicate callback bindings')
            binding_lines=[line];continue
        if callback_lines:
            if not kind.startswith('VLD_'):raise ValueError('Interrupted callback reference')
            callback_lines.append(line)
            if kind=='VLD_END':callbacks.set_reference(callback_lines);callback_lines=[]
            continue
        if kind=='VLD_BEGIN' and boundary is None:
            if ordinal or callbacks.reference is not None:raise ValueError('Late/duplicate callback reference')
            callback_lines=[line];continue
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
            index=int(a[1]);target=float(a[3]);phase='before-step'
            if a[2]!=phase or not math.isfinite(target) or (ordinal==0 and (index!=0 or target!=0)) or (ordinal==1 and (index<=0 or index%2 or target<5e-6)) or ordinal>1:raise ValueError('Invalid selected boundary')
            boundary={'index':index,'phase':phase,'targetSeconds':target};ordinal+=1;stages={};stage=None
        elif kind=='VB_STAGE':
            if boundary is None or lines or len(a)!=2 or a[1] in stages or a[1] not in ('before','repeat','changed','restored'):raise ValueError('Invalid stage')
            if stage is not None and stage not in stages:raise ValueError('Missing snapshot')
            stage=a[1]
        elif kind=='VA_BEGIN':
            if boundary is None or stage is None or stage in stages or lines:raise ValueError('Orphan bundle')
            lines=[line]
        elif kind=='VA_END' or kind.startswith(('VF_','VD_','VJ_','VR_','VE_','VP_','VW_','VS_','VAP_','VPR_','VI_','VIQ_','VIF_','VT_','VTQ_','VWE_','VTC_','VSC_','VCO_','VAC_','VAR_','VND_','VNG_','VWD_','VSD_','VNT_','VXD_','VXM_','VGD_','VAD_','VRE_','VWC_','VCD_','VRX_','VIX_','VLD_','VLB_','VHB_','VSH_','VSL_')):
            if not lines:raise ValueError('Orphan observer record')
            lines.append(line)
            if kind=='VA_END':stages[stage]=(lines,bundle(lines,identities));lines=[]
        elif kind in ('VB_STABLE','VB_CALLBACK_LIST_FAULT','VB_PARAMETER_FAULT'):
            if boundary is None or lines:raise ValueError('Incomplete boundary')
            if kind=='VB_STABLE':
                if line!='VB_STABLE equal=1' or list(stages)!=['before','repeat'] or stages['before'][0]!=stages['repeat'][0]:raise ValueError('Observer changed state')
            else:
                changed_fault=fault_type in TYPED_FAULTS and TYPED_FAULTS[fault_type]<7
                expected=['before','changed','restored'] if changed_fault else ['before','restored']
                if fault_type is None or line!=markers[fault_type] or list(stages)!=expected:raise ValueError('Wrong fault control')
                if changed_fault:typed_changed(stages['before'][1],stages['changed'][1],TYPED_FAULTS[fault_type],typed.bindings)
                if stages['before'][0]!=stages['restored'][0]:raise ValueError('Fault not restored')
                if ordinal!=2 or boundary['targetSeconds']<5e-6:raise ValueError('Parameter fault missed later boundary')
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
            callbacks.observe(state)
            typed.observe(state,graph,callbacks)
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
            if fault is not None and startup_phase!=2:raise ValueError('Wrong fault lifecycle phase')
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
    if handle_lines or callback_lines or binding_lines or israw_lines or resolver_lines or concat_lines or raw_lines or reduction_lines or arithmetic_lines or gate_lines or mux_lines or signal_lines or type_lines or wire_lines or graph_lines or reference_lines or boundary is not None or lines or not ordinal or (fault is None and ordinal%2):raise ValueError('Incomplete observations')
    if ordinal!=2 or not finished_start:raise ValueError('Missing selected later boundary')
    if not active_start or (fault_type is None and (not finished_start or not executing or not empty or not saved or not cleared or not display or not released)):raise ValueError('Missing startup or later board state coverage')
    if not assignment_counts[4] or not assignment_counts[8] or (fault_type is None and not empty_assignments):raise ValueError('Missing assignment family or consumption coverage')
    if fault_type and fault is None:raise ValueError('Unexercised fault')
    return {**typed.result(),**callbacks.result(),**assignraw.result(),**israw.result(),**resolver.result(),**concat.result(),**raw.result(),**reduction.result(),**arithmetic.result(),**gates.result(),**muxes.result(),**signals.result(),**wires.result(),**graph.result(fault_type is not None),**arrays.result(fault_type is not None),**operands.result(),**scopes.result(fault_type is not None),**codes.result(fault_type is not None),**waits.result(fault_type is not None),**threads.result(fault_type is not None),**filters.result(fault_type is not None),**island_lifetimes.result(fault_type is not None),**primitives.result(fault_type is not None),'assignmentObservations':assignment_counts,'uniqueAssignments':len(assignment_ids),'emptyAssignmentBoundaries':empty_assignments,'maximumUncoveredEvents':unsupported_max,'startupLifetimeId':startup_id,'activeStartupObservations':active_start,'destroyedStartupObservations':finished_start,'boundaries':ordinal,'executingWrapperObservations':executing,'emptyFrameObservations':empty,
            'uniqueExecutingEvents':len(event_links),'associatedDisplayObservations':display,'releasedDisplayObservations':released,
            'savedStopObservations':saved,'clearedStopObservations':cleared,'portObservations':port_observations,'ports':layout,'outputCallbackObservations':output_observations,'outputCallbacks':output_layout,'fault':fault}
