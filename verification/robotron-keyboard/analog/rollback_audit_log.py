"""Strictly summarize solver/irreversible-client ordering without inferring HDL state."""
from collections import Counter
import math
import re

HEX=r'-?0x[0-9a-f]+(?:\.[0-9a-f]*)?p[+-]?\d+'
ACCEPT=re.compile(r'ROLLBACK_AUDIT accept time=('+HEX+r')')
REJECT=re.compile(r'ROLLBACK_AUDIT reject kind=(newton|lte|breakpoint) time=('+HEX+r') delta=('+HEX+r')(?: (target|target_delta)=('+HEX+r'))?')
CLIENT=re.compile(r'ROLLBACK_AUDIT client phase=(before|after) time=('+HEX+r') name=(\S+) priority=(\d+) index=(\d+) count=(\d+) breakpoint=('+HEX+r')')


def analyze(lines):
    accepted_count=0;first_accepted=None;rejected=Counter();clients=Counter();pending=None;trial=[]
    calls_before_reject=Counter();unprotected=0;invalid_order=0
    last_accepted=-math.inf;records=0
    for text in lines:
        line=text.strip()
        if not line.startswith('ROLLBACK_AUDIT '):continue
        records+=1
        a=ACCEPT.fullmatch(line);r=REJECT.fullmatch(line);c=CLIENT.fullmatch(line)
        if a:
            time=float.fromhex(a[1])
            if pending is not None or time<=last_accepted:
                raise ValueError('Invalid accepted-point ordering')
            if any(t!=time for t in trial):invalid_order+=1
            if first_accepted is None:first_accepted=time
            accepted_count+=1;last_accepted=time;trial=[]
        elif r:
            kind=r[1];time=float.fromhex(r[2]);delta=float.fromhex(r[3])
            expected={'newton':None,'lte':'target_delta','breakpoint':'target'}[kind]
            if r[4]!=expected or delta<=0 or time<=last_accepted or pending is not None:
                raise ValueError('Invalid rejected-trial record')
            if r[5] is not None and not math.isfinite(float.fromhex(r[5])):
                raise ValueError('Invalid rejection target')
            rejected[kind]+=1
            if trial:
                calls_before_reject[kind]+=1
                if any(t!=time for t in trial):invalid_order+=1
            trial=[]
        elif c:
            phase,time,name,priority,index,count,breakpoint=c.groups()
            time=float.fromhex(time);priority,index,count=map(int,(priority,index,count))
            identity=(time,name,priority,index,count)
            if not 0<=index<count or priority<=0 or time<=last_accepted:
                raise ValueError('Invalid irreversible-client record')
            if phase=='before':
                if pending is not None:raise ValueError('Nested irreversible-client calls')
                pending=identity
            else:
                if pending!=identity:raise ValueError('Mismatched irreversible-client return')
                pending=None;trial.append(time);clients[name]+=1
                unprotected+=int(priority!=1 or index!=count-1)
        else:
            raise ValueError('Malformed rollback audit record')
    if pending is not None or trial or accepted_count<2:
        raise ValueError('Incomplete rollback audit')
    return {'records':records,'acceptedPoints':accepted_count,'firstAcceptedSeconds':first_accepted,
            'lastAcceptedSeconds':last_accepted,'rejectedTrials':dict(rejected),
            'clientCalls':dict(clients),'unprotectedClientCalls':unprotected,
            'trialsRejectedAfterClientCallbacks':dict(calls_before_reject),
            'invalidTrialOrdering':invalid_order,'qualified':False,
            'boundary':'Client callbacks are not proof of irreversible HDL advancement. Complete waveform controls and internal client-state evidence remain separate.'}
