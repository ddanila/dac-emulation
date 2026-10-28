"""Validate and remove only the explicitly allocated diagnostic memory from a copy."""
import copy,re
from array_probe import validate as validate_arrays


def without_diagnostic(state,handle_offset):
    result=copy.deepcopy(state);memories=result['memoryMetadata'];metadata=result['scopeMetadata'];reference=result['scopeMetadataReferences'];arrays=result['arrays']
    extras=[m for m in memories['rows'] if re.fullmatch(rb'__lifecycle_[12]\x00',bytes.fromhex(m['name']))]
    if len(extras)!=1:raise ValueError('Missing unique diagnostic memory')
    m=extras[0];ident=m['id'];validate_arrays(arrays)
    if m['handle']-m['array']!=handle_offset or ident!=max(o['id'] for o in reference['objects']):raise ValueError('Invalid diagnostic layout/identity')
    objects=[o for o in reference['objects'] if o['id']==ident]
    if objects!=[dict(id=ident,pointer=m['handle'],type=29)]:raise ValueError('Unbound diagnostic object')
    owners=[s for s in metadata['scopes'] if dict(id=ident,type=29) in s['intern']]
    refs={r['id']:r['pointer'] for r in reference['scopes']}
    if len(owners)!=1 or refs.get(owners[0]['id'])!=m['scope']:raise ValueError('Unbound diagnostic scope')
    values=[a for a in arrays['arrays'] if a['key']==m['array']]
    if len(values)!=1:raise ValueError('Missing diagnostic payload')
    a=values[0]
    expected=dict(scope=m['scope'],first=0,last=1,msb=7,lsb=0,size=2,width=8,signed=0,swap=0,head=0,cache=0,words=['1'*8,'3'*8],cacheParent=None,cacheWords=[])
    if any(a[k]!=v for k,v in expected.items()) or any(p['array']==a['id'] for p in arrays['ports']):raise ValueError('Unexpected diagnostic memory payload or references')
    if m['nameBytes']!=len(bytes.fromhex(m['name'])):raise ValueError('Wrong diagnostic name allocation')
    memories['rows'].remove(m);reference['objects'].remove(objects[0]);owners[0]['intern'].remove(dict(id=ident,type=29));arrays['arrays'].remove(a)
    remap={value['id']:i+1 for i,value in enumerate(arrays['arrays'])}
    for value in arrays['arrays']:value['id']=remap[value['id']]
    for port in arrays['ports']:port['array']=remap[port['array']]
    validate_arrays(arrays)
    return result,m


def created(before,after,handle_offset):
    normalized,memory=without_diagnostic(after,handle_offset)
    if normalized!=before:raise ValueError('Allocation changed unrelated complete state')
    return memory
