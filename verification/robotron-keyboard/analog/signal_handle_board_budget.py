#!/usr/bin/env python3
"""Bind initialized board port handles to compiled metadata and native allocations."""
import argparse,json,math,re
from pathlib import Path
import callback_board_budget as previous
from signal_handles import parse
from net_probe import parse as graph_parse,validate as graph_validate,pointer
from port_identity_review import snapshot as port_snapshot
HERE=Path(__file__).resolve().parent


def compiled_handles(text,names):
    scopes=list(re.finditer(r'^\S+ \.scope module,',text,re.M))
    if not scopes:raise ValueError('Missing compiled module')
    module=re.match(r'^\S+ \.scope module, "([^"]+)"',text[scopes[0].start():]).group(1)
    if any(not name.startswith(module+'.') or name.count('.')!=1 for name in names):raise ValueError('Ports do not belong to compiled top module')
    start=scopes[0].start();end=re.search(r'^\S+ \.scope ',text[scopes[0].end():],re.M)
    top=text[start:scopes[0].end()+end.start() if end else len(text)]
    rows={}
    for m in re.finditer(r'^\S+ \.(net|var)(/s)? "([^"]+)", (-?\d+) (-?\d+),',top,re.M):
        kind,signed,name,left,right=m.groups();name=module+'.'+name
        if name in names:
            if name in rows:raise ValueError('Duplicate compiled handle')
            rows[name]=dict(kind='10signal_'+('net' if kind=='net' else 'reg'),signed=int(bool(signed)),msb=int(left),lsb=int(right))
    if set(rows)!=set(names):raise ValueError('Missing or unsupported compiled port handles')
    return rows


def scope_ids(lines):
    if lines[0]!='VSC_BEGIN 1 0':raise ValueError('Scope time mismatch')
    ids={};i=1
    while i<len(lines) and lines[i].startswith('VSC_SCOPE '):
        a=lines[i].split();i+=1
        if len(a)!=6:raise ValueError('Invalid scope record')
        identity,key,parent,kind,count=int(a[1]),pointer(a[2]),int(a[3]),int(a[4]),int(a[5])
        if identity!=len(ids)+1 or key<=0 or not 0<=parent<identity or count<0:raise ValueError('Invalid scope hierarchy')
        members=[]
        for _ in range(count):
            a=lines[i].split();i+=1
            if len(a)!=2 or a[0]!='VSC_MEMBER' or int(a[1])<=0:raise ValueError('Invalid scope membership')
            members.append(int(a[1]))
        if members!=sorted(set(members)):raise ValueError('Aliased scope members')
        ids[identity]=key
    if not ids or len(set(ids.values()))!=len(ids) or lines[i:]!=[f'VSC_END {len(ids)}']:raise ValueError('Incomplete scope inventory')
    return ids


def review(root):
    callback=previous.review(root);receipt=json.loads((root/'run.json').read_text())
    before=(root/'handles-before.txt').read_text()
    if before!=(root/'handles-after.txt').read_text():raise ValueError('Handle scan changed state')
    state=parse(before.splitlines());unadmitted=parse((root/'handles-unadmitted.txt').read_text().splitlines())
    if state['tick'] or unadmitted!={'tick':0,'rows':[]}:raise ValueError('Missing empty handoff or time advanced')
    ports=port_snapshot((root/'ports.txt').read_text().splitlines())['ports']
    contract=compiled_handles((root/'io.vvp').read_text(),[p['name'] for p in ports])
    graph=graph_parse((root/'handle-graph.txt').read_text().splitlines());graph_validate(graph)
    if graph['tick']:raise ValueError('Graph time mismatch')
    nodes={n['id']:n for n in graph['nodes']};scopes=scope_ids((root/'handle-scopes.txt').read_text().splitlines())
    rows={r['id']:r for r in state['rows']};bindings={}
    lines=(root/'handle-bindings.txt').read_text().splitlines()
    if len(lines)!=len(ports) or len(rows)!=len(ports):raise ValueError('Incomplete port handle handoff')
    for port,line in zip(ports,lines):
        a=line.split()
        if len(a)!=5 or a[0]!='SH_BIND' or int(a[1])!=port['index']:raise ValueError('Wrong port handle order')
        identity=int(a[2]);address,handle=map(pointer,a[3:]);row=rows.get(identity)
        if not row or not address or handle!=row['pointer']:raise ValueError('Wrong native signal identity')
        if bytes.fromhex(row['name'])!=port['name'].rsplit('.',1)[-1].encode()+b'\0':raise ValueError('Signal name differs from bridge port')
        if any(row[k]!=v for k,v in contract[port['name']].items()) or abs(row['msb']-row['lsb'])+1!=port['bits']:raise ValueError('Signal metadata differs from compiled port')
        if row['bits'] or row['count']:raise ValueError('Unexpected initial bit cache')
        if row['nodeId'] not in nodes or nodes[row['nodeId']]['key']!=row['node'] or not nodes[row['nodeId']]['filter']:raise ValueError('Unbound signal graph node')
        if scopes.get(row['scopeId'])!=row['scope']:raise ValueError('Unbound native signal scope')
        bindings[port['index']]=(identity,address,handle)
    if len({v[0] for v in bindings.values()})!=len(ports) or len({v[1] for v in bindings.values()})!=len(ports):raise ValueError('Aliased port handle handoff')
    for line in (root/'bindings.txt').read_text().splitlines():
        a=line.split();index=int(a[1]);_,address,handle=bindings[index]
        if (pointer(a[3]),pointer(a[5]))!=(address,handle):raise ValueError('Callback object differs from typed signal handle')
    budget=(root/'handle-budget.txt').read_text().splitlines()
    if len(budget)!=2 or budget[1]!='SH_DONE':raise ValueError('Incomplete handle budget')
    a=budget[0].split()
    if len(a)!=5 or a[:2]!=['SH_BUDGET','64']:raise ValueError('Invalid handle budget')
    total,minimum,maximum=map(float,a[2:])
    if not all(math.isfinite(x) for x in (total,minimum,maximum)) or not 0<minimum<=total/64<=maximum:raise ValueError('Invalid handle scan measurement')
    calls=2*receipt['reviewedBoundaries'];size=len(before.encode())
    return dict(qualified=False,controlsPassed=True,priorCallbackBindings=callback,initializedPortHandles=len(bindings),imageBytes=size,
                scanTimings=dict(iterations=64,meanSeconds=total/64,minSeconds=minimum,maxSeconds=maximum),
                initialStateProjection=dict(normalSnapshotCalls=calls,logicalBytes=calls*size,scanSeconds=calls*total/64,excludesStateGrowthCompressionAndOtherObservers=True),
                scope='Actual initialized bridge ports match compiled signal class, signedness, range and width. Callback object handles bind to the same typed signals; their node and scope IDs match independent native inventories. Full scans preserve exact initial images and do not allocate bit handles. Diagnostic ends before coroutine advancement; callback-owner adjusted-pointer linkage, lifecycle, changed-state cost and operational integration remain unqualified.')


def run(source,bridge,icarus,out):
    previous.run(source,bridge,icarus,out)
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','bridge','icarus','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.source,a.bridge,a.icarus,a.out)
