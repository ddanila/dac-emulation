#!/usr/bin/env python3
"""Match initialized board parameter payloads to native owners and compiled values."""
import argparse,json,math,re
from pathlib import Path
import scope_signals_board_budget as previous
from scope_signal_declarations import state as signal_state,validate as signal_declarations
from scope_metadata_records import parse as metadata_parse
from scope_metadata_bindings import reference_parse
from parameter_payload import parse


def compiled_parameters(text):
    quoted=r'"(?:\\.|[^"\\])*"';scopes={};current=None;parameters={}
    for raw in text.splitlines():
        line=raw.strip()
        if re.match(r'^\S+\s+\.scope\s',line):
            m=re.fullmatch(r'(\S+)\s+\.scope\s+[^,]+,\s*('+quoted+r')\s+('+quoted+r')\s+(.+);',line)
            if not m:raise ValueError('Unsupported parameter scope')
            parent=re.search(r',\s*([^,\s]+)$',m[4]);parent=parent[1] if parent else None
            if parent is not None and parent not in scopes:raise ValueError('Unknown compiled parent')
            current=m[1]
            if current in scopes:raise ValueError('Duplicate parameter scope')
            scopes[current]=(scopes[parent] if parent else ())+ (json.loads(m[2]),)
        elif line.startswith('.scope '):
            current=line[7:].removesuffix(';')
            if current not in scopes:raise ValueError('Unknown recalled parameter scope')
        elif re.match(r'^\S+\s+\.param',line):
            m=re.fullmatch(r'\S+\s+\.param/l\s+('+quoted+r')\s+([01])\s+(\d+)\s+(\d+),\s*(\+)?C4<([01xz]+)>;',line)
            if not m or current not in scopes:raise ValueError('Unsupported compiled parameter; this board profile requires binary values')
            name,local,file,line_number,signed,bits=m.groups();key=(scopes[current],json.loads(name))
            if key in parameters:raise ValueError('Duplicate compiled parameter')
            parameters[key]=dict(local=int(local),file=int(file),line=int(line_number),signed=int(bool(signed)),sized=0,bits=[{'0':0,'1':1,'z':2,'x':3}[v] for v in reversed(bits)])
    if not parameters:raise ValueError('Missing compiled parameters')
    return parameters


def bindings(payload,metadata,reference,compiled):
    if len({p['tick'] for p in (payload,metadata,reference)})!=1:raise ValueError('Parameter binding time mismatch')
    declarations=compiled_parameters(compiled);scopes={s['id']:s for s in metadata['scopes']};scope_ptrs={s['pointer']:s['id'] for s in reference['scopes']};objects={o['id']:o for o in reference['objects']};owners={};paths={}
    for scope in scopes.values():
        for obj in scope['intern']:owners.setdefault(obj['id'],[]).append(scope['id'])
    def name(value):
        raw=bytes.fromhex(value)
        if not raw.endswith(b'\0') or b'\0' in raw[:-1]:raise ValueError('Invalid parameter/scope name')
        return raw[:-1].decode()
    def path(ident):
        if ident not in paths:
            s=scopes[ident];paths[ident]=(path(s['parent']) if s['parent'] else ())+ (name(s['nameBytes']),)
        return paths[ident]
    seen=set();keys=set();bits_count=0;raw_words=0
    for row in payload['rows']:
        obj=objects.get(row['id']);scope=scope_ptrs.get(row['scope'])
        if obj!=dict(id=row['id'],pointer=row['pointer'],type=41) or scope is None or owners.get(row['id'])!=[scope]:raise ValueError('Parameter identity/owner mismatch')
        key=(path(scope),name(row['name']));declaration=declarations.get(key)
        if row['kind']!='binary' or declaration is None or key in keys:raise ValueError('Unexpected/duplicate parameter family or name')
        value=row['value'];width=value['width'];wordbits=value['wordBits']
        bits=[((value['words'][i//wordbits][1]>>(i%wordbits))&1)*2+((value['words'][i//wordbits][0]>>(i%wordbits))&1) for i in range(width)]
        actual=dict(local=row['local'],file=row['file'],line=row['line'],signed=value['signed'],sized=value['sized'],bits=bits)
        if actual!=declaration:raise ValueError('Parameter payload differs from compiled declaration')
        seen.add(row['id']);keys.add(key);bits_count+=width;raw_words+=len(value['words'])
    if keys!=set(declarations) or seen!={o['id'] for o in objects.values() if o['type']==41}:raise ValueError('Incomplete parameter population')
    return dict(parameters=len(seen),binaryBits=bits_count,rawWordPairs=raw_words,compiledNamesFlagsSourceMetadataAndValuesExactlyEqual=True)


def review(root):
    prior=previous.review(root);compiled=(root/'io.vvp').read_text();signal_declarations(signal_state(root),compiled)
    text=(root/'parameters-before.txt').read_text()
    if text!=(root/'parameters-after.txt').read_text():raise ValueError('Parameter scan changed state')
    result=bindings(parse(text.splitlines()),metadata_parse((root/'metadata-before.txt').read_text().splitlines()),reference_parse((root/'metadata-references-before.txt').read_text().splitlines()),compiled)
    lines=(root/'parameters-budget.txt').read_text().splitlines()
    if len(lines)!=1:raise ValueError('Missing parameter scan budget')
    a=lines[0].split()
    if len(a)!=6 or a[:3]!=['SCOPE_SCAN','parameters','64']:raise ValueError('Invalid parameter scan budget')
    total,minimum,maximum=map(float,a[3:])
    if not all(math.isfinite(v) for v in (total,minimum,maximum)) or not 0<minimum<=total/64<=maximum:raise ValueError('Invalid parameter scan timing')
    calls=prior['initialStateProjection']['normalSnapshotCalls'];size=len(text.encode())
    return dict(qualified=False,controlsPassed=True,priorSignalControls=prior,bindings=result,imageBytes=size,scanTimings=dict(iterations=64,meanSeconds=total/64,minSeconds=minimum,maxSeconds=maximum),
        initialStateProjection=dict(normalSnapshotCalls=calls,logicalBytes=calls*size,scanSeconds=calls*total/64,excludesGrowthOtherObserversAndReview=True),
        scope='All initialized actual keyboard parameters join native scope object identities and independent compiled names, local/source metadata, signed/sized flags and logical binary values. Raw storage words remain retained, including unused high bits not specified by declarations. This board contains binary parameters only; native string/real coverage remains separate. Initial scan images are unchanged. No compact/changed-state cost, pointer/lifecycle or normal transient qualification.')


def run(source,bridge,icarus,out):
    previous.run(source,bridge,icarus,out);(out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','bridge','icarus','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.source,a.bridge,a.icarus,a.out)
