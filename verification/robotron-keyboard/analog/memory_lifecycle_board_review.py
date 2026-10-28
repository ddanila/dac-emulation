#!/usr/bin/env python3
"""Review all compact payloads at selected startup and later parameter fault boundaries."""
import argparse,json
from pathlib import Path
import memory_lifecycle_core_review as previous
import memory_lifecycle_preflight as preflight
from memory_compact import MemoryDecoder
from memory_metadata import parse as memory_parse
from memory_board_budget import bindings as memory_bindings,native_layout
from parameter_compact import ParameterDecoder
from parameter_payload import parse as parameter_parse
from parameter_board_budget import bindings as parameter_bindings
from scope_metadata_compact import Decoder
from scope_metadata_records import parse as metadata_parse
from scope_metadata_bindings import reference_parse,validate
from port_payload_compact import PortDecoder
from scope_signals_compact import SignalDecoder,parse as all_signal_parse
from scope_signals_board_budget import bindings as all_signal_bindings
from scope_signal_declarations import validate as declaration_bindings
from port_payload import parse as port_parse
from port_payload_board_budget import bindings as port_bindings,compiled_ports


def inventory(path,identities,**kwargs):
    offset=kwargs.pop('memory_offset')
    previous.HANDLE_OFFSET=offset
    old_records,old_bundle,old_graph=previous.records,previous.bundle,previous.GraphState
    graphs=[];compiled=compiled_ports(kwargs['compiled'])
    def make_graph(source):
        graph=old_graph(source);graphs.append(graph);return graph
    decoders={'VSMD':Decoder(),'VSMRD':Decoder(True),'VPPD':PortDecoder(),'VSAD':SignalDecoder(),'VPMD':ParameterDecoder(),'VMMD':MemoryDecoder()}
    stage=None;stages={};pending={};counts=dict(snapshots=0,scopes=0,boundSignals=0)
    def records(path,prefix):
        nonlocal stage,stages,pending
        active=None;block=[]
        for line in old_records(path,prefix+('VSMD_','VSMRD_','VSM_','VSMR_','VPP_','VPPD_','VSA_','VSAD_','VPM_','VPMD_','VMM_','VMMD_')):
            if active:
                block.append(line)
                if line==active+'_END':
                    dense=decoders[active].decode(block);key={'VSMD':'metadata','VSMRD':'reference','VPPD':'ports','VSAD':'allSignals','VPMD':'parameters','VMMD':'memories'}[active]
                    if key in pending:raise ValueError('Duplicate combined metadata section')
                    pending[key]={'metadata':metadata_parse,'reference':reference_parse,'ports':port_parse,'allSignals':all_signal_parse,'parameters':parameter_parse,'memories':memory_parse}[key](dense.splitlines())
                    active=None;block=[]
                continue
            if line.startswith(('VSMD_BEGIN ','VSMRD_BEGIN ','VPPD_BEGIN ','VSAD_BEGIN ','VPMD_BEGIN ','VMMD_BEGIN ')):
                if stage is None:raise ValueError('Metadata outside snapshot stage')
                active=line.split('_BEGIN')[0];block=[line];continue
            if line.startswith(('VSM_','VSMR_','VSMD_','VSMRD_','VPP_','VPPD_','VSA_','VSAD_','VPM_','VPMD_','VMM_','VMMD_')):raise ValueError('Orphan metadata record')
            if line.startswith('VB_BRIDGE '):
                if pending:raise ValueError('Unconsumed metadata')
                stages={};stage=None
            elif line.startswith('VB_STAGE '):
                if pending:raise ValueError('Interrupted combined metadata')
                stage=line.split()[1]
            elif line.startswith(('VB_STABLE ','VB_MEMORY_LIFECYCLE ')):
                restored='repeat' if line.startswith('VB_STABLE ') else 'restored'
                if pending or 'before' not in stages or restored not in stages or stages['before']!=stages[restored]:raise ValueError('Combined metadata changed without restoration')
                stage=None
            yield line
        if active or pending:raise ValueError('Truncated combined metadata')
    def bundle(lines,identities):
        nonlocal pending
        state=old_bundle(lines,identities)
        if set(pending)!={'metadata','reference','ports','allSignals','parameters','memories'}:raise ValueError('Missing complete metadata sections')
        membership=dict(tick=state['threads']['tick'],scopes=[dict(id=s['id'],pointer=s['pointer'],parent=s['parent'],type=s['kind'],members=s['members']) for s in state['scopes']])
        joined=dict(pending,membership=membership,signals=state['typedSignals'])
        found=validate(joined)
        if len(graphs)!=1:raise ValueError('Missing unique native graph reviewer')
        # Undo only the explicitly requested diagnostic field in a copy for
        # declaration checks; the original payload is retained for exact fault comparison.
        import copy
        checked_parameters=copy.deepcopy(pending['parameters'])
        port_state=port_bindings(pending['ports'],pending['metadata'],pending['reference'],graphs[0].image(state['graph']),compiled)
        counts['ports']=port_state['ports'];counts['portBits']=port_state['bits']
        full_signals=dict(joined,signals=pending['allSignals'])
        full_bindings=all_signal_bindings(full_signals,graphs[0].image(state['graph']))
        declaration_bindings(full_signals,kwargs['compiled'])
        if any(r not in pending['allSignals']['rows'] for r in state['typedSignals']['rows']):raise ValueError('Bridge signals differ from complete inventory')
        counts['allSignals']=full_bindings['boundSignals']
        counts['parameters']=parameter_bindings(checked_parameters,pending['metadata'],pending['reference'],kwargs['compiled'])['parameters']
        from memory_lifecycle_state import without_diagnostic
        checked=dict(memoryMetadata=pending['memories'],arrays=state['arrays'],scopeMetadata=pending['metadata'],scopeMetadataReferences=pending['reference'])
        if stage=='created':checked,_=without_diagnostic(checked,offset)
        memory_state=memory_bindings(checked['memoryMetadata'],checked['arrays'],checked['scopeMetadata'],checked['scopeMetadataReferences'],kwargs['compiled'],offset)
        counts['memories']=memory_state['memories'];counts['memoryReadPorts']=memory_state['readPorts']
        state['memoryMetadata']=pending['memories']
        state['parameters']=pending['parameters']
        state['scopeSignals']=pending['allSignals']
        if stage is None or stage in stages:raise ValueError('Duplicate combined metadata stage')
        stages[stage]=pending
        state['portPayload']=pending['ports'];state['scopeMetadata']=pending['metadata'];state['scopeMetadataReferences']=pending['reference'];pending={}
        counts['snapshots']+=1;counts['scopes']=found['scopes'];counts['boundSignals']=found['boundSignals']
        return state
    try:
        previous.records=records;previous.bundle=bundle;previous.GraphState=make_graph
        result=previous.inventory(path,identities,**kwargs)
    finally:
        previous.records,previous.bundle,previous.GraphState=old_records,old_bundle,old_graph
    if not counts['snapshots'] or any(d.sequence!=counts['snapshots'] for d in decoders.values()):raise ValueError('Incomplete combined metadata coverage')
    result['scopeMetadata']=dict(counts,metadataFull=decoders['VSMD'].full,metadataReused=decoders['VSMD'].reused,
        referenceFull=decoders['VSMRD'].full,referenceReused=decoders['VSMRD'].reused,portFull=decoders['VPPD'].full,portReused=decoders['VPPD'].reused,allSignalFull=decoders['VSAD'].full,allSignalReused=decoders['VSAD'].reused,parameterFull=decoders['VPMD'].full,parameterReused=decoders['VPMD'].reused,memoryFull=decoders['VMMD'].full,memoryReused=decoders['VMMD'].reused)
    return result


def review(root):
    offset=native_layout(root)
    old=preflight.inventory
    try:
        preflight.inventory=lambda *args,**kwargs:inventory(*args,memory_offset=offset,**kwargs);result=preflight.review(root)
    finally:preflight.inventory=old
    from fast_audit_log import complete,equal,records
    from postreset_startup_review import FIRMWARE
    from raw_pair_review import compare_raw
    from stop_board_review import startup_identity
    from compare_firmware_io import sha as logical_sha
    baseline=root/'baseline';receipt=json.loads((baseline/'run.json').read_text())
    for name,digest in [('waveform.raw',receipt['storage']['waveform.raw']['sha256']),('ngspice.log',receipt['log']['sha256'])]:
        if logical_sha(baseline/name)!=digest:raise ValueError('Changed normal reference output')
    original=complete(baseline/'ngspice.log');identity=startup_identity(baseline/'ngspice.log')
    if not original['latchesMatch'] or receipt['endSeconds']!=20e-6:raise ValueError('Incomplete normal reference')
    comparisons={}
    for mode in result['negativeControls']:
        folder=root/mode;run=json.loads((folder/'run.json').read_text());scan=complete(folder/'ngspice.log')
        if scan!=run['summary'] or not scan['latchesMatch'] or not any(records(folder/'ngspice.log',('FIRST_FETCH ',))):raise ValueError('Invalid complete firmware execution')
        if startup_identity(folder/'ngspice.log')!=identity:raise ValueError('Changed initialized models')
        comparisons[mode]=compare_raw(baseline/'waveform.raw',folder/'waveform.raw',[original['count'],scan['count']],20e-6,exact=True)
        if not equal(baseline/'ngspice.log',folder/'ngspice.log',FIRMWARE):raise ValueError('Changed restored-fault firmware continuation')
    result['completeComparisons']=comparisons;result['firmwareRecordsExactlyEqual']=True
    from parameter_continue_activity import activity
    result['postRestorationActivity']={}
    for mode,state in result['negativeControls'].items():
        target=state['lifecycleCycles'][-1]['targetSeconds'];found=activity(root/mode/'ngspice.log',target)
        if found!=activity(baseline/'ngspice.log',target):raise ValueError('Changed post-restoration bus activity')
        result['postRestorationActivity'][mode]=found

    result['scope']='Two selected complete board lifecycle cycles at 5 and 6 us allocate and destroy a test memory, require direct/combined refusal with unchanged logger cache identities/sequences, detach the stale entry and restore all state exactly. Complete 20-us waveform and firmware continuation match the baseline. Test memories have no compiled HDL references; this is not continuous observation or full graph teardown.'

    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.write_text(json.dumps(review(a.root),indent=2)+'\n')
