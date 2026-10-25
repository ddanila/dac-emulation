#!/usr/bin/env python3
"""Review directly observed controller output flags and pending event lists."""
import argparse
import json
import math
from pathlib import Path
from history_state_review import assess as assess_histories
from trace_io import open_text
from ttl7406_probe import sha


def scheduling(path, *, require_activity=True):
    active=None;port=None;snapshots=0;items=0;max_pending=0;published=0;matched=0;requests=set();layout=None
    with open_text(path) as stream:
        for line in stream:
            fields=line.split()
            if not fields:continue
            kind=fields[0]
            if kind=='H_BEGIN':
                if active is not None:raise ValueError('Nested scheduling snapshot')
                active={'phase':fields[1],'time':float(fields[2]),'ports':[],'items':0};port=None
            elif kind=='H_ARRAY' and active is not None and fields[1:3]==['1','0']:
                active['outputs']=[tuple(map(int,v.split(':'))) for v in fields[4:]]
            elif kind=='E_SUM':
                if active is None or 'summary' in active or len(fields)!=6:raise ValueError('Malformed event summary')
                times=[float.fromhex(v) for v in fields[1:3]];counts=list(map(int,fields[3:]))
                if not all(map(math.isfinite,times)) or min(counts)<0:raise ValueError('Invalid queue summary')
                active['summary']=times+counts
            elif kind=='E_PORT':
                if active is None or 'summary' not in active or len(fields)!=10:raise ValueError('Malformed output port')
                if port is not None and port['remaining']:raise ValueError('Missing queued events')
                connection,ordinal,index,changed=map(int,fields[1:5]);delay=float.fromhex(fields[5]);valid,state,strength,count=map(int,fields[6:])
                if connection not in (1,2) or min(ordinal,index,count)<0 or changed not in (0,1) or not math.isfinite(delay) or delay<0:raise ValueError('Invalid output scheduling fields')
                if valid!=int(active['phase']=='output-after' and changed) or (not valid and (state,strength)!=(0,0)):raise ValueError('Read unassigned output value')
                port={'connection':connection,'ordinal':ordinal,'index':index,'remaining':count,'seen':0,'valid':valid,'value':(state,strength)}
                active['ports'].append(port)
                if valid:
                    requests.add((index,active['time']+delay,state,strength));published+=1
            elif kind=='E_ITEM':
                if active is None or port is None or len(fields)!=9:raise ValueError('Orphan pending event')
                index,ordinal=map(int,fields[1:3]);event_time,posted_time=map(float.fromhex,fields[3:5]);removed=int(fields[5]);removed_time=float.fromhex(fields[6]);state,strength=map(int,fields[7:])
                if index!=port['index'] or ordinal!=port['seen'] or port['remaining']<=0:raise ValueError('Incomplete or reordered event list')
                if not all(map(math.isfinite,(event_time,posted_time,removed_time))) or removed not in (0,1) or event_time<posted_time or (not removed and removed_time!=0):raise ValueError('Invalid queued event')
                port['remaining']-=1;port['seen']+=1;active['items']+=1;items+=1
                key=(index,event_time,state,strength)
                if not removed and key in requests:requests.remove(key);matched+=1
            elif kind=='H_END':
                if active is None or 'summary' not in active or 'outputs' not in active or not active['ports']:raise ValueError('Missing scheduling state')
                if port['remaining']:raise ValueError('Truncated event list')
                current=[(p['connection'],p['ordinal'],p['index']) for p in active['ports']]
                expected=[(c,i) for c in (1,2) for i in range(sum(p['connection']==c for p in active['ports']))]
                if [(c,i) for c,i,index in current]!=expected or len({index for c,i,index in current})!=len(current):raise ValueError('Invalid port inventory')
                if layout is not None and layout!=current:raise ValueError('Changed port inventory')
                layout=current
                if len(current)!=len(active['outputs']):raise ValueError('Missing output port')
                for p,value in zip(active['ports'],active['outputs']):
                    if p['valid'] and p['value']!=value:raise ValueError('Published output disagrees with output history')
                max_pending=max(max_pending,active['items']);snapshots+=1;active=None;port=None
            elif kind.startswith('E_') and kind!='E_CORRUPT':raise ValueError('Unknown scheduling record')
    if active is not None:raise ValueError('Truncated scheduling snapshot')
    if require_activity and (not snapshots or not items or not published or not matched):raise ValueError('Missing scheduled event activity')
    return {'snapshots':snapshots,'ports':len(layout or []),'pendingEventObservations':items,
            'maximumObservedPendingEvents':max_pending,'assignedOutputObservations':published,
            'publicationsWitnessedInPendingQueue':matched,
            'unwitnessedPublicationKeys':len(requests),
            'unwitnessedPublications':[{'outputIndex':i,'scheduledTime':t,'state':s,'strength':strength} for i,t,s,strength in sorted(requests)],
            'matchingScope':'Exact port, scheduled time and value matches. Events may be consumed before another observer checkpoint; unmatched requests are not classified as lost.'}


def assess(root,baseline):
    result=assess_histories(root,baseline)
    result['scheduling']=scheduling(root/'check/ngspice.log')
    with open_text(root/'corrupt/ngspice.log') as stream:
        if sum(s=='E_CORRUPT output-delay\n' for s in stream)!=1:raise ValueError('Missing delay corruption control')
    result['scope']='Bounded initialized controller histories, output flags/delays, assigned output values, and complete lists from controller output-queue current pointers. Delay corruption is detected at a rejected input barrier. Disabled/enabled/prior waveform samples and firmware events match exactly.'
    result['notEstablished']=['Startup lifecycle','Other circuit models and past/free output queue history','Private HDL pending-event queue','General rollback, full scenarios, numerical convergence and physical-model admission']
    return result


def check(root):
    manifest=json.loads((root/'manifest.json').read_text())
    files={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and p.name!='manifest.json'}
    if files!=manifest['files']:raise ValueError('Changed scheduling evidence')
    for name,digest in manifest['sources'].items():
        if sha(Path(__file__).parent/name)!=digest:raise ValueError('Changed scheduling source')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--baseline',type=Path);p.add_argument('--check-manifest',action='store_true');a=p.parse_args()
    if a.check_manifest:check(a.root)
    else:
        if not a.baseline:p.error('Need baseline')
        result=assess(a.root,a.baseline);(a.root/'assessment.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
