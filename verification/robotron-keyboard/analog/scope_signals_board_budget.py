#!/usr/bin/env python3
"""Bind every initialized board vector signal to scope objects and net allocations."""
import argparse,json,math
from pathlib import Path
import port_payload_board_budget as previous
from signal_handles import parse as signal_parse
from scope_metadata_bindings import parse as joined_parse,validate
from net_probe import parse as graph_parse


def bindings(state,graph):
    result=validate(state);rows=state['signals']['rows']
    expected={o['pointer'] for o in state['reference']['objects'] if o['type'] in (25,36,48)}
    if {r['pointer'] for r in rows}!=expected:raise ValueError('Incomplete scope signal coverage')
    if graph['tick']!=state['signals']['tick']:raise ValueError('Signal/net time mismatch')
    nodes={n['id']:n['key'] for n in graph['nodes']}
    for row in rows:
        if nodes.get(row['nodeId'])!=row['node']:raise ValueError('Unknown scope signal net')
    return dict(result,completeRegisteredSignalFamilies=True,netBindings=len(rows))


def review(root):
    prior=previous.review(root)
    text=(root/'scope-signals-before.txt').read_text()
    if text!=(root/'scope-signals-after.txt').read_text():raise ValueError('Scope signal scan changed state')
    lines=text.splitlines()
    if not lines or not lines[0].startswith('VSA_BEGIN '):raise ValueError('Missing all-signal image')
    signal_lines=[l.replace('VSA_','VSH_',1) for l in lines]
    joined=joined_parse([l for name in ('metadata-before.txt','metadata-references-before.txt','handle-scopes.txt') for l in (root/name).read_text().splitlines()]+signal_lines)
    result=bindings(joined,graph_parse((root/'handle-graph.txt').read_text().splitlines()))
    admitted=signal_parse((root/'handles-before.txt').read_text().splitlines())
    if any(r not in joined['signals']['rows'] for r in admitted['rows']):raise ValueError('Bridge admission payload differs')
    lines=(root/'scope-signals-budget.txt').read_text().splitlines()
    if len(lines)!=1:raise ValueError('Missing all-signal budget')
    a=lines[0].split()
    if len(a)!=6 or a[:3]!=['SCOPE_SCAN','scope-signals','64']:raise ValueError('Invalid scope signal budget')
    total,minimum,maximum=map(float,a[3:])
    if not all(math.isfinite(v) for v in (total,minimum,maximum)) or not 0<minimum<=total/64<=maximum:raise ValueError('Invalid scan time')
    calls=prior['initialStateProjection']['normalSnapshotCalls'];size=len(text.encode())
    return dict(qualified=False,controlsPassed=True,priorPortControls=prior,bindings=result,admittedBridgeSignals=len(admitted['rows']),
        additionalScopeSignals=len(joined['signals']['rows'])-len(admitted['rows']),imageBytes=size,
        scanTimings=dict(iterations=64,meanSeconds=total/64,minSeconds=minimum,maxSeconds=maximum),
        initialStateProjection=dict(normalSnapshotCalls=calls,logicalBytes=calls*size,scanSeconds=calls*total/64,excludesGrowthOtherObserversAndReview=True),
        scope='Complete initialized actual keyboard vector signal registry joins every scope object of types reg/net/integer, native scope ownership and allocated net identity. Existing bridge-admitted images are an exact subset. Initial repeat images are unchanged. Compiled declaration metadata, unsupported families, lifetime changes, compact storage and normal transient qualification remain open.')


def run(source,bridge,icarus,out):
    previous.run(source,bridge,icarus,out)
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','bridge','icarus','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.source,a.bridge,a.icarus,a.out)
