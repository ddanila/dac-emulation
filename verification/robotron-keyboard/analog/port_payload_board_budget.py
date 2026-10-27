#!/usr/bin/env python3
"""Bind all initialized native port payloads to compiled declarations and owners."""
import argparse,json,math,re
from pathlib import Path
import scope_metadata_board_budget as previous
from port_payload import parse
from scope_metadata_records import parse as metadata_parse
from scope_metadata_bindings import reference_parse
from net_probe import parse as graph_parse


def compiled_ports(text):
    quoted=r'"(?:\\.|[^"\\])*"';scopes={};current=None;ports={}
    for line in text.splitlines():
        line=line.strip()
        if re.match(r'^\S+\s+\.scope\s',line):
            m=re.fullmatch(r'(\S+)\s+\.scope\s+[^,]+,\s*('+quoted+r')\s+('+quoted+r')\s+(.+);',line)
            if not m:raise ValueError('Unrecognized compiled scope')
            parent=re.search(r',\s*([^,\s]+)$',m[4]);parent=parent[1] if parent else None
            if parent is not None and parent not in scopes:raise ValueError('Unknown compiled parent')
            current=m[1]
            if current in scopes:raise ValueError('Duplicate compiled scope')
            scopes[current]=(scopes[parent] if parent else ())+ (json.loads(m[2]),)
        elif line.startswith('.scope '):
            current=line[7:].removesuffix(';')
            if current not in scopes:raise ValueError('Unknown recalled scope')
        elif line.startswith('.port_info '):
            m=re.fullmatch(r'\.port_info (\d+) /(INPUT|OUTPUT|INOUT) (\d+) ('+quoted+r')(?:,\s*(\S+))?;',line)
            if not m or current not in scopes:raise ValueError('Unrecognized compiled port')
            key=(scopes[current],int(m[1]))
            if key in ports:raise ValueError('Duplicate compiled port')
            ports[key]=dict(name=json.loads(m[4]),direction={'INPUT':1,'OUTPUT':2,'INOUT':3}[m[2]],width=int(m[3]),hasNetReference=m[5] is not None)
    if not ports:raise ValueError('Missing compiled ports')
    return ports


def bindings(payload,metadata,reference,graph,compiled):
    if len({s['tick'] for s in (payload,metadata,reference,graph)})!=1:raise ValueError('Port binding time mismatch')
    scopes={s['id']:s for s in metadata['scopes']};objects={o['id']:o for o in reference['objects']};nodes={n['id']:n['key'] for n in graph['nodes']}
    owners={}
    for scope in scopes.values():
        for obj in scope['intern']:
            if obj['id'] in owners:raise ValueError('Duplicate internal ownership')
            owners[obj['id']]=scope['id']
    paths={}
    def path(ident):
        if ident not in paths:
            scope=scopes[ident];name=bytes.fromhex(scope['nameBytes'])
            if not name.endswith(b'\0') or b'\0' in name[:-1]:raise ValueError('Invalid compiled scope name')
            paths[ident]=(path(scope['parent']) if scope['parent'] else ())+ (name[:-1].decode(),)
        return paths[ident]
    seen=set();seen_bits=set();keys=set();nonnull=0
    for port in payload['ports']:
        obj=objects.get(port['id'])
        if obj!=dict(id=port['id'],pointer=port['pointer'],type=44) or owners.get(port['id'])!=port['scope']:raise ValueError('Port identity/owner mismatch')
        if port['scope'] not in scopes:raise ValueError('Unknown port scope')
        name=bytes.fromhex(port['name'])
        if not name.endswith(b'\0') or b'\0' in name[:-1]:raise ValueError('Invalid compiled port name')
        key=(path(port['scope']),port['index'])
        native=dict(name=name[:-1].decode(),direction=port['direction'],width=port['width'],hasNetReference=bool(port['node']))
        if key in keys or compiled.get(key)!=native:raise ValueError('Port payload differs from compiled declaration')
        keys.add(key);seen.add(port['id'])
        if port['node']:
            if nodes.get(port['nodeId'])!=port['node']:raise ValueError('Port net identity mismatch')
            nonnull+=1
        if [b['index'] for b in port['bits']]!=list(range(port['width'])):raise ValueError('Port bit order differs from compiled order')
        for bit in port['bits']:
            if bit['id'] in seen_bits or objects.get(bit['id'])!=dict(id=bit['id'],pointer=bit['pointer'],type=45) or owners.get(bit['id'])!=port['scope']:raise ValueError('Port bit identity/owner mismatch')
            seen_bits.add(bit['id'])
    if keys!=set(compiled) or seen!={o['id'] for o in objects.values() if o['type']==44} or seen_bits!={o['id'] for o in objects.values() if o['type']==45}:raise ValueError('Incomplete port family coverage')
    return dict(ports=len(seen),bits=len(seen_bits),nonNullNetReferences=nonnull,compiledDeclarationsExactlyEqual=True)


def review(root):
    prior=previous.review(root)
    text=(root/'port-payload-before.txt').read_text()
    if text!=(root/'port-payload-after.txt').read_text():raise ValueError('Port scan changed initialized payload')
    payload=parse(text.splitlines())
    result=bindings(payload,metadata_parse((root/'metadata-before.txt').read_text().splitlines()),reference_parse((root/'metadata-references-before.txt').read_text().splitlines()),graph_parse((root/'handle-graph.txt').read_text().splitlines()),compiled_ports((root/'io.vvp').read_text()))
    lines=(root/'port-payload-budget.txt').read_text().splitlines()
    if len(lines)!=1:raise ValueError('Incomplete port budget')
    a=lines[0].split()
    if len(a)!=6 or a[:3]!=['SCOPE_SCAN','ports','64']:raise ValueError('Invalid port budget')
    total,minimum,maximum=map(float,a[3:])
    if not all(math.isfinite(x) for x in (total,minimum,maximum)) or not 0<minimum<=total/64<=maximum:raise ValueError('Invalid port timing')
    calls=prior['initialStateProjection']['normalSnapshotCalls'];size=len(text.encode())
    return dict(qualified=False,controlsPassed=True,priorMetadataControls=prior,portBindings=result,imageBytes=size,
        scanTimings=dict(iterations=64,meanSeconds=total/64,minSeconds=minimum,maxSeconds=maximum),
        initialStateProjection=dict(normalSnapshotCalls=calls,logicalBytes=calls*size,scanSeconds=calls*total/64,excludesGrowthOtherObserversAndReview=True),
        scope='All initialized actual keyboard native ports and bits bind exactly to scope intern identities and compiled declaration names/directions/widths/indices/order. Nonnull references would bind to native graph IDs; this board may use null references. Complete images remain unchanged through full scans before coroutine advance. No changing-state, field/subclass/lifecycle or operational board qualification.')


def run(source,bridge,icarus,out):
    previous.run(source,bridge,icarus,out)
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','bridge','icarus','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.source,a.bridge,a.icarus,a.out)
