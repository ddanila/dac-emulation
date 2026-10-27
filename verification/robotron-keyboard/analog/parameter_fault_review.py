#!/usr/bin/env python3
"""Review compact parameter payloads alongside every preceding combined state layer."""
import argparse,json
from pathlib import Path
import parameter_fault_core_review as previous
import parameter_fault_preflight as preflight
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
    old_records,old_bundle,old_graph=previous.records,previous.bundle,previous.GraphState
    graphs=[];compiled=compiled_ports(kwargs['compiled'])
    def make_graph(source):
        graph=old_graph(source);graphs.append(graph);return graph
    decoders={'VSMD':Decoder(),'VSMRD':Decoder(True),'VPPD':PortDecoder(),'VSAD':SignalDecoder(),'VPMD':ParameterDecoder()}
    stage=None;stages={};pending={};counts=dict(snapshots=0,scopes=0,boundSignals=0)
    def records(path,prefix):
        nonlocal stage,stages,pending
        active=None;block=[]
        for line in old_records(path,prefix+('VSMD_','VSMRD_','VSM_','VSMR_','VPP_','VPPD_','VSA_','VSAD_','VPM_','VPMD_')):
            if active:
                block.append(line)
                if line==active+'_END':
                    dense=decoders[active].decode(block);key={'VSMD':'metadata','VSMRD':'reference','VPPD':'ports','VSAD':'allSignals','VPMD':'parameters'}[active]
                    if key in pending:raise ValueError('Duplicate combined metadata section')
                    pending[key]={'metadata':metadata_parse,'reference':reference_parse,'ports':port_parse,'allSignals':all_signal_parse,'parameters':parameter_parse}[key](dense.splitlines())
                    active=None;block=[]
                continue
            if line.startswith(('VSMD_BEGIN ','VSMRD_BEGIN ','VPPD_BEGIN ','VSAD_BEGIN ','VPMD_BEGIN ')):
                if stage is None:raise ValueError('Metadata outside snapshot stage')
                active=line.split('_BEGIN')[0];block=[line];continue
            if line.startswith(('VSM_','VSMR_','VSMD_','VSMRD_','VPP_','VPPD_','VSA_','VSAD_','VPM_','VPMD_')):raise ValueError('Orphan metadata record')
            if line.startswith('VB_BRIDGE '):
                if pending:raise ValueError('Unconsumed metadata')
                stages={};stage=None
            elif line.startswith('VB_STAGE '):
                if pending:raise ValueError('Interrupted combined metadata')
                stage=line.split()[1]
            elif line.startswith(('VB_STABLE ','VB_CALLBACK_LIST_FAULT ','VB_PARAMETER_FAULT ')):
                restored='repeat' if line.startswith('VB_STABLE ') else 'restored'
                if pending or 'before' not in stages or restored not in stages or stages['before']!=stages[restored]:raise ValueError('Combined metadata changed without restoration')
                stage=None
            yield line
        if active or pending:raise ValueError('Truncated combined metadata')
    def bundle(lines,identities):
        nonlocal pending
        state=old_bundle(lines,identities)
        if set(pending)!={'metadata','reference','ports','allSignals','parameters'}:raise ValueError('Missing complete metadata sections')
        membership=dict(tick=state['threads']['tick'],scopes=[dict(id=s['id'],pointer=s['pointer'],parent=s['parent'],type=s['kind'],members=s['members']) for s in state['scopes']])
        joined=dict(pending,membership=membership,signals=state['typedSignals'])
        found=validate(joined)
        if len(graphs)!=1:raise ValueError('Missing unique native graph reviewer')
        # Undo only the explicitly requested diagnostic field in a copy for
        # declaration checks; the original payload is retained for exact fault comparison.
        import copy
        checked_parameters=copy.deepcopy(pending['parameters'])
        if stage=='changed':previous.toggle(checked_parameters,previous.TYPED_FAULTS.get(kwargs.get('fault_type')))
        port_state=port_bindings(pending['ports'],pending['metadata'],pending['reference'],graphs[0].image(state['graph']),compiled)
        counts['ports']=port_state['ports'];counts['portBits']=port_state['bits']
        full_signals=dict(joined,signals=pending['allSignals'])
        full_bindings=all_signal_bindings(full_signals,graphs[0].image(state['graph']))
        declaration_bindings(full_signals,kwargs['compiled'])
        if any(r not in pending['allSignals']['rows'] for r in state['typedSignals']['rows']):raise ValueError('Bridge signals differ from complete inventory')
        counts['allSignals']=full_bindings['boundSignals']
        counts['parameters']=parameter_bindings(checked_parameters,pending['metadata'],pending['reference'],kwargs['compiled'])['parameters']
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
        referenceFull=decoders['VSMRD'].full,referenceReused=decoders['VSMRD'].reused,portFull=decoders['VPPD'].full,portReused=decoders['VPPD'].reused,allSignalFull=decoders['VSAD'].full,allSignalReused=decoders['VSAD'].reused,parameterFull=decoders['VPMD'].full,parameterReused=decoders['VPMD'].reused)
    return result


def review(root):
    old=preflight.inventory
    try:
        preflight.inventory=inventory;result=preflight.review(root)
    finally:preflight.inventory=old
    result['scope']='Startup-only ten native parameter faults and four callback regressions, with every preceding state layer and all 56 parameter ownership/compiled bindings checked. Seven exact isolated field changes and three zero-output refusals restore complete dense state before controlled termination. Normal transient comparison, firmware continuation, later-boundary and lifecycle qualification remain open.'
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.write_text(json.dumps(review(a.root),indent=2)+'\n')
