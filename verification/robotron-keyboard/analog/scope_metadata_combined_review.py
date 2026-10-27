#!/usr/bin/env python3
"""Decode metadata log records while preserving every preceding board review."""
import argparse,json
from pathlib import Path
import typed_signal_fault_review as previous
import typed_signal_fault_preflight as preflight
from scope_metadata_compact import Decoder
from scope_metadata_records import parse as metadata_parse
from scope_metadata_bindings import reference_parse,validate


def inventory(path,identities,**kwargs):
    old_records,old_bundle=previous.records,previous.bundle
    decoders={'VSMD':Decoder(),'VSMRD':Decoder(True)}
    stage=None;stages={};pending={};counts=dict(snapshots=0,scopes=0,boundSignals=0)
    def records(path,prefix):
        nonlocal stage,stages,pending
        active=None;block=[]
        for line in old_records(path,prefix+('VSMD_','VSMRD_','VSM_','VSMR_')):
            if active:
                block.append(line)
                if line==active+'_END':
                    dense=decoders[active].decode(block);key='metadata' if active=='VSMD' else 'reference'
                    if key in pending:raise ValueError('Duplicate combined metadata section')
                    pending[key]=(metadata_parse if key=='metadata' else reference_parse)(dense.splitlines())
                    active=None;block=[]
                continue
            if line.startswith(('VSMD_BEGIN ','VSMRD_BEGIN ')):
                if stage is None:raise ValueError('Metadata outside snapshot stage')
                active=line.split('_BEGIN')[0];block=[line];continue
            if line.startswith(('VSM_','VSMR_','VSMD_','VSMRD_')):raise ValueError('Orphan metadata record')
            if line.startswith('VB_BRIDGE '):
                if pending:raise ValueError('Unconsumed metadata')
                stages={};stage=None
            elif line.startswith('VB_STAGE '):
                if pending:raise ValueError('Interrupted combined metadata')
                stage=line.split()[1]
            elif line.startswith(('VB_STABLE ','VB_CALLBACK_LIST_FAULT ','VB_TYPED_SIGNAL_FAULT ')):
                restored='repeat' if line.startswith('VB_STABLE ') else 'restored'
                if pending or 'before' not in stages or restored not in stages or stages['before']!=stages[restored]:raise ValueError('Combined metadata changed without restoration')
                stage=None
            yield line
        if active or pending:raise ValueError('Truncated combined metadata')
    def bundle(lines,identities):
        nonlocal pending
        state=old_bundle(lines,identities)
        if set(pending)!={'metadata','reference'}:raise ValueError('Missing complete metadata sections')
        membership=dict(tick=state['threads']['tick'],scopes=[dict(id=s['id'],pointer=s['pointer'],parent=s['parent'],type=s['kind'],members=s['members']) for s in state['scopes']])
        joined=dict(pending,membership=membership,signals=state['typedSignals'])
        found=validate(joined)
        if stage is None or stage in stages:raise ValueError('Duplicate combined metadata stage')
        stages[stage]=pending
        state['scopeMetadata']=pending['metadata'];state['scopeMetadataReferences']=pending['reference'];pending={}
        counts['snapshots']+=1;counts['scopes']=found['scopes'];counts['boundSignals']=found['boundSignals']
        return state
    try:
        previous.records=records;previous.bundle=bundle
        result=previous.inventory(path,identities,**kwargs)
    finally:
        previous.records,previous.bundle=old_records,old_bundle
    if not counts['snapshots'] or any(d.sequence!=counts['snapshots'] for d in decoders.values()):raise ValueError('Incomplete combined metadata coverage')
    result['scopeMetadata']=dict(counts,metadataFull=decoders['VSMD'].full,metadataReused=decoders['VSMD'].reused,
        referenceFull=decoders['VSMRD'].full,referenceReused=decoders['VSMRD'].reused)
    return result


def review(root):
    old=preflight.inventory
    try:
        preflight.inventory=inventory;result=preflight.review(root)
    finally:preflight.inventory=old
    result['scope']='Startup-only combined replay adds reconstructed dense scope metadata and scope/signal ownership joins to every prior layer. Existing callback and typed-signal faults restore exact dense snapshots before termination; compact encoding occurs only after native snapshot comparisons. No scope-specific board fault, normal transient, firmware continuation or operational qualification.'
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.write_text(json.dumps(review(a.root),indent=2)+'\n')
