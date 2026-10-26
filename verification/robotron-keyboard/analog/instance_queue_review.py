#!/usr/bin/env python3
"""Review instance event lists, worklists and rollback-anchor observation."""
import argparse
import json
import math
from pathlib import Path
import re
from audit_log import records
from circuit_output_review import inventory as output_inventory
from delayed_corruption_review import assess as base_assess, fault
from event_state_review import check
from filter_truncation_log import diagnostic
from staged_output_review import STATE_RECORDS

INSTANCE_RECORDS = ('I_SUM ', 'I_INDEX ', 'I_INST ', 'I_SLOT ', 'I_EVENT ')


def inventory(path):
    active=False; layout=None; snapshots=0; events=0; pending=0; external_pending=0
    last_anchors=[]; max_pending_work=0; max_to_call=0
    def finish_instance():
        if current is None: return
        if not terminal or want_event or len(anchors[0])!=1 or len(anchors[1])!=1:
            raise ValueError('Missing instance terminal or unique rollback anchors')
        positions.append({'index':current[0], 'current':anchors[0][0],
                          'lastStep':anchors[1][0], 'events':ordinal})
    for line in records(path, ('H_BEGIN ', 'H_END', 'I_')):
        a=line.split(); kind=a[0]
        if kind=='H_BEGIN':
            if active: raise ValueError('Nested instance snapshot')
            active=True; size=None; instances=[]; positions=[]; current=None
            lists=[[],[],[]]; counts=None; terminal=False; want_event=False
        elif kind=='I_SUM':
            if not active or size is not None or len(a)!=7: raise ValueError('Invalid instance summary')
            size=int(a[1]); times=list(map(float.fromhex,a[2:4]));counts=list(map(int,a[4:7]))
            if size<=0 or not all(map(math.isfinite,times)) or any(n<0 or n>size for n in counts):
                raise ValueError('Invalid instance queue sizes/clocks')
            max_pending_work=max(max_pending_work,counts[1]);max_to_call=max(max_to_call,counts[2])
        elif kind=='I_INDEX':
            if not active or size is None or current is not None or len(a)!=4: raise ValueError('Orphan instance worklist')
            tag,number,index=map(int,a[1:])
            if tag not in range(3) or number!=len(lists[tag]) or not 0<=index<size or index in lists[tag]:
                raise ValueError('Invalid instance worklist')
            lists[tag].append(index)
        elif kind=='I_INST':
            if not active or size is None or len(a)!=7: raise ValueError('Orphan instance identity')
            finish_instance()
            index,own=map(int,a[1:3]);flags=list(map(int,a[4:7]))
            if index!=len(instances) or index>=size or own not in (0,1) or any(v not in (0,1) for v in flags):
                raise ValueError('Invalid instance identity/flags')
            current=(index,own,a[3]);instances.append(current)
            ordinal=0;anchors=[[],[]];terminal=False;want_event=False;previous_time=None
        elif kind=='I_SLOT':
            if not active or current is None or terminal or want_event or len(a)!=6: raise ValueError('Invalid instance slot')
            index,number,now,last,has_event=map(int,a[1:])
            if index!=current[0] or number!=ordinal or any(v not in (0,1) for v in (now,last,has_event)):
                raise ValueError('Invalid instance slot identity')
            if now: anchors[0].append(ordinal)
            if last: anchors[1].append(ordinal)
            want_event=bool(has_event);terminal=not want_event
        elif kind=='I_EVENT':
            if not active or current is None or not want_event or len(a)!=5: raise ValueError('Orphan instance event')
            index,number=map(int,a[1:3]);when,posted=map(float.fromhex,a[3:5])
            if index!=current[0] or number!=ordinal or not all(map(math.isfinite,(when,posted))) or when<posted or (previous_time is not None and when<previous_time):
                raise ValueError('Invalid instance event order/time')
            previous_time=when;events+=1
            if anchors[0]: pending+=1;external_pending+=int(not current[1])
            ordinal+=1;want_event=False
        elif kind=='H_END':
            if not active or size is None: raise ValueError('Incomplete instance snapshot')
            finish_instance()
            if len(instances)!=size or [len(x) for x in lists]!=counts: raise ValueError('Incomplete instance lists')
            if layout is not None and instances!=layout: raise ValueError('Changed instance identities')
            layout=instances;last_anchors=positions;snapshots+=1;active=False
        else: raise ValueError('Unknown instance record')
    if active or not snapshots or not any(x[1] for x in layout) or not any(not x[1] for x in layout):
        raise ValueError('Missing instance coverage')
    return {'snapshots':snapshots,'instances':len(layout),'eventObservations':events,
            'pendingEventObservations':pending,'externalPendingEventObservations':external_pending,
            'maximumPendingWorklist':max_pending_work,'maximumToCallWorklist':max_to_call,
            'inventory':[{'index':i,'controllerOwned':bool(own),'instance':name} for i,own,name in layout],
            'lastAnchors':last_anchors}


def external_fault(path, after):
    markers=list(records(path,('C_CORRUPT ',)))
    if len(markers)!=1: raise ValueError('Missing unique instance fault')
    match=re.fullmatch(r'C_CORRUPT instance-current index=(\d+) instance=(\S+) from=(\d+) to=0',markers[0])
    if not match: raise ValueError('Malformed instance fault')
    index,name,position=match.groups();index=int(index);position=int(position)
    data=inventory(path)
    selected=[p for p in data['inventory'] if p['index']==index]
    if len(selected)!=1 or selected[0]['controllerOwned'] or selected[0]['instance']!=name:
        raise ValueError('Fault did not target an observed external instance')
    anchor=data['lastAnchors'][index]
    if not position or position!=anchor['current'] or not anchor['events']:
        raise ValueError('Fault did not rewind an observed consumed event')
    return dict(fault(path,after,mutation_line=markers[0]),mutatedInstance=selected[0],
                previousCurrentOrdinal=position,mutation='Rewind current slot to retained event-list head')


def runtime_summary(path):
    prefixes=STATE_RECORDS+('C_SUM ','C_PORT ','C_EVENT ')+INSTANCE_RECORDS
    count=None;failure=None;sorry=False
    for line in records(path):
        if line.startswith(prefixes): continue
        if line.startswith(('C_CORRUPT ','E_CORRUPT ','I_CORRUPT ')): raise ValueError('Unexpected positive-control fault')
        failure=failure or diagnostic(line);sorry=sorry or 'SORRY:' in line
        matches=re.findall(r'No\. of Data Rows\s*:\s*(\d+)',line)
        if matches:
            if count is not None or len(matches)!=1: raise ValueError('Multiple completion counts')
            count=int(matches[0])
    return {'count':count,'diagnostic':failure,'sorry':sorry}


def assess(root, baseline):
    result=base_assess(root,baseline,fault_review=external_fault,summary_review=runtime_summary)
    result['circuitOutputs']=output_inventory(root/'check/ngspice.log')
    result['instanceQueues']=inventory(root/'check/ngspice.log')
    if not result['instanceQueues']['externalPendingEventObservations']:
        raise ValueError('No actual external pending instance events observed')
    result['scope']='Complete 20-us observer controls for instance lists, rollback anchors and worklists as well as digital output queues. Negative controls rewind an external current slot; they do not mutate a pending callback time.'
    result['notEstablished']=['Long-window instance-state qualification','Private HDL events and freed instance storage',
                              'Full startup/repeat/supply recovery','Numerical convergence','Device admission']
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--baseline',type=Path)
    p.add_argument('--out',type=Path);p.add_argument('--check-manifest',action='store_true')
    a=p.parse_args()
    if a.check_manifest: check(a.root)
    else:
        if not a.baseline or not a.out:p.error('Need baseline and output')
        result=assess(a.root,a.baseline)
        with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
