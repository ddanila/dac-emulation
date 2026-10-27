#!/usr/bin/env python3
"""Join all initialized board memory names, native identities and compiled arrays."""
import argparse,collections,json,math,re
from pathlib import Path
import parameter_board_budget as previous
from memory_metadata import parse,review as native_review
from retained_evidence import check
from array_probe import parse as array_parse,validate as array_validate
from array_source_contract import profile
from scope_metadata_records import parse as metadata_parse
from scope_metadata_bindings import reference_parse


def compiled_memories(text):
    arrays=profile(text);paths={};quoted=r'"(?:\\.|[^"\\])*"'
    for raw in text.splitlines():
        line=raw.strip()
        if not re.match(r'^\S+\s+\.scope\s',line):continue
        m=re.fullmatch(r'(\S+)\s+\.scope\s+[^,]+,\s*('+quoted+r')\s+('+quoted+r')\s+(.+);',line)
        if not m:raise ValueError('Unsupported memory scope declaration')
        parent=re.search(r',\s*([^,\s]+)$',m[4]);parent=parent[1] if parent else None
        if m[1] in paths or (parent is not None and parent not in paths):raise ValueError('Invalid compiled memory scope')
        paths[m[1]]=(paths[parent] if parent else ())+ (json.loads(m[2]),)
    declarations={};ports=collections.Counter(p['array'] for p in arrays['ports'])
    for a in arrays['arrays']:
        key=(paths[a['scope']],a['name'])
        if key in declarations:raise ValueError('Duplicate compiled memory name')
        first,last=a['compilerFirst'],a['compilerLast']
        declarations[key]=dict(first=min(first,last),last=max(first,last),swap=int(first>last),msb=a['msb'],lsb=a['lsb'],size=a['words'],width=a['width'],signed=0,readPorts=ports[a['label']])
    return declarations


def bindings(memories,arrays,metadata,reference,compiled,handle_offset):
    if len({s['tick'] for s in (memories,arrays,metadata,reference)})!=1:raise ValueError('Memory snapshot time mismatch')
    if type(handle_offset) is not int or handle_offset<0:raise ValueError('Missing native layout witness')
    array_validate(arrays);declarations=compiled_memories(compiled)
    scopes={s['id']:s for s in metadata['scopes']};scope_ids={s['pointer']:s['id'] for s in reference['scopes']};objects={o['id']:o for o in reference['objects']};owners={};paths={}
    for s in scopes.values():
        for obj in s['intern']:owners.setdefault(obj['id'],[]).append(s['id'])
    def name(value):
        raw=bytes.fromhex(value)
        if not raw.endswith(b'\0') or b'\0' in raw[:-1]:raise ValueError('Invalid bounded memory/scope name')
        return raw[:-1].decode()
    def path(ident):
        if ident not in paths:
            s=scopes[ident];paths[ident]=(path(s['parent']) if s['parent'] else ())+ (name(s['nameBytes']),)
        return paths[ident]
    native={a['key']:a for a in arrays['arrays']};seen=set();keys=set();payloads=set();result=[]
    for m in memories['rows']:
        if m['handle']-m['array']!=handle_offset:raise ValueError('Memory handle/concrete layout differs from native witness')
        obj=objects.get(m['id']);owner=scope_ids.get(m['scope']);a=native.get(m['array'])
        if obj!=dict(id=m['id'],pointer=m['handle'],type=29) or owner is None or owners.get(m['id'])!=[owner]:raise ValueError('Memory handle identity/owner mismatch')
        if a is None or a['scope']!=m['scope'] or m['array'] in payloads:raise ValueError('Memory concrete array identity/owner mismatch')
        key=(path(owner),name(m['name']));expected=declarations.get(key)
        fields=('first','last','swap','msb','lsb','size','width','signed');actual={k:a[k] for k in fields};actual['readPorts']=sum(p['array']==a['id'] for p in arrays['ports'])
        if key in keys or actual!=expected:raise ValueError('Memory payload differs from compiled declaration')
        seen.add(m['id']);payloads.add(m['array']);keys.add(key);result.append(dict(path=list(key[0]),name=key[1],objectId=m['id'],arrayId=a['id'],words=a['size'],width=a['width'],readPorts=actual['readPorts']))
    if keys!=set(declarations) or seen!={o['id'] for o in objects.values() if o['type']==29} or payloads!=set(native):raise ValueError('Incomplete memory population')
    return dict(memories=len(seen),logicalBits=sum(a['size']*a['width'] for a in arrays['arrays']),readPorts=len(arrays['ports']),compiledNamesOwnersRangesAndPortCountsExactlyEqual=True,rows=result)


def native_layout(root):
    witness=root/'native-layout';check(witness);native_review(witness)
    built=json.loads((root/'icarus-build.json').read_text());native=json.loads((witness/'build.json').read_text())
    for name in ('vvp/libvvp.so','vvp/vpi_priv.h'):
        if built['outputs'][name]!=native['outputs'][name]:raise ValueError('Native layout uses different runtime/header')
    lines=(witness/'enabled.stdout').read_text().splitlines();offsets=set()
    for line in lines:
        if line.startswith('IDENTITY '):
            a=line.split();offsets.add(int(a[2],16)-int(a[3],16))
    if len(offsets)!=1:raise ValueError('Inconsistent native array layout')
    return offsets.pop()


def review(root):
    prior=previous.review(root)
    for stem in ('memories','memory-arrays'):
        if (root/(stem+'-before.txt')).read_bytes()!=(root/(stem+'-after.txt')).read_bytes():raise ValueError('Memory scan changed initialized state')
    text=(root/'memories-before.txt').read_text();result=bindings(parse(text.splitlines()),array_parse((root/'memory-arrays-before.txt').read_text().splitlines()),metadata_parse((root/'metadata-before.txt').read_text().splitlines()),reference_parse((root/'metadata-references-before.txt').read_text().splitlines()),(root/'io.vvp').read_text(),native_layout(root))
    lines=(root/'memories-budget.txt').read_text().splitlines()
    if len(lines)!=1:raise ValueError('Missing memory budget')
    a=lines[0].split()
    if len(a)!=6 or a[:3]!=['SCOPE_SCAN','memories','64']:raise ValueError('Invalid memory budget')
    total,minimum,maximum=map(float,a[3:])
    if not all(math.isfinite(v) for v in (total,minimum,maximum)) or not 0<minimum<=total/64<=maximum:raise ValueError('Invalid memory timing')
    calls=prior['initialStateProjection']['normalSnapshotCalls'];size=len(text.encode())
    return dict(qualified=False,controlsPassed=True,priorParameterControls=prior,bindings=result,nativeHandleOffsetBytes=native_layout(root),imageBytes=size,scanTimings=dict(iterations=64,meanSeconds=total/64,minSeconds=minimum,maxSeconds=maximum),initialStateProjection=dict(normalSnapshotCalls=calls,logicalBytes=calls*size,scanSeconds=calls*total/64,excludesGrowthOtherObserversAndReview=True),scope='All initialized board memory names and scope object handles join concrete array payloads and independent compiled scope/name/range/size/width/read-port counts. Complete memory names and array values/cache images remain unchanged through scans at tick zero. Native storage traversal safety, lifecycle/subclass and operational transient qualification remain open.')


def run(source,bridge,icarus,out):
    import shutil
    previous.run(source,bridge,icarus,out)
    shutil.copytree(Path(__file__).resolve().parent/'reports/memory-metadata',out/'native-layout')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','bridge','icarus','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.source,a.bridge,a.icarus,a.out)
