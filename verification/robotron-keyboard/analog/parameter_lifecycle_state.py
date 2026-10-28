"""Validate the diagnostic parameter and isolate its complete-state addition."""
import copy,re,struct


def without_diagnostic(state,kind):
    result=copy.deepcopy(state);parameters=result['parameters'];metadata=result['scopeMetadata'];reference=result['scopeMetadataReferences']
    if kind not in ('binary','real','string'):raise ValueError('Unknown diagnostic family')
    number=('binary','real','string').index(kind)
    extras=[p for p in parameters['rows'] if re.fullmatch(rb'__parameter_lifecycle_[012]_[12]\x00',bytes.fromhex(p['name']))]
    if len(extras)!=1:raise ValueError('Missing unique diagnostic parameter')
    p=extras[0];ident=p['id'];v=p['value']
    if p['kind']!=kind or not re.fullmatch(f'__parameter_lifecycle_{number}_[12]'.encode()+b'\x00',bytes.fromhex(p['name'])) or any(p[k] for k in ('local','file','line')) or ident!=max(o['id'] for o in reference['objects']):raise ValueError('Wrong diagnostic family/metadata')
    objects=[o for o in reference['objects'] if o['id']==ident]
    if objects!=[dict(id=ident,pointer=p['pointer'],type=41)]:raise ValueError('Unbound diagnostic object')
    owners=[s for s in metadata['scopes'] if dict(id=ident,type=41) in s['intern']];refs={r['id']:r['pointer'] for r in reference['scopes']}
    if len(owners)!=1 or refs.get(owners[0]['id'])!=p['scope']:raise ValueError('Unbound diagnostic scope')
    if kind=='binary':
        if v['width']!=80 or v['signed'] or v['sized'] or v['aPointer']==v['bPointer']:raise ValueError('Wrong diagnostic binary shape')
        mask=(1<<v['wordBits'])-1
        if v['words']!=[[mask,mask^1]]+[[mask,mask]]*(v['wordCount']-1):raise ValueError('Wrong diagnostic binary payload')
    elif kind=='real':
        if v!=dict(bytes=8,value=struct.pack('=d',2.5).hex()):raise ValueError('Wrong diagnostic real payload')
    elif v['bytes']!=4 or v['value']!='47005200' or not v['pointer']:raise ValueError('Wrong diagnostic string payload')
    if p['nameBytes']!=len(bytes.fromhex(p['name'])):raise ValueError('Wrong diagnostic name allocation')
    parameters['rows'].remove(p);reference['objects'].remove(objects[0]);owners[0]['intern'].remove(dict(id=ident,type=41))
    return result,p


def created(before,after,kind):
    normalized,parameter=without_diagnostic(after,kind)
    if normalized!=before:raise ValueError('Allocation changed unrelated complete state')
    return parameter
