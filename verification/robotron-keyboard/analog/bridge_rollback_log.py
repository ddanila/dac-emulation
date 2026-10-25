"""Correlate bridge time observations with solver callbacks and rejected trials."""
from collections import Counter
import math
import re
from rollback_audit_log import ACCEPT, CLIENT, REJECT

NUMBER=r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
ADVANCE=re.compile(r'TIME_AUDIT advance target=('+NUMBER+r') actual=('+NUMBER+r') base=('+NUMBER+r') tick=('+NUMBER+r') pending=(\d+)')
OUTPUT=re.compile(r'TIME_AUDIT output actual=('+NUMBER+r') target=('+NUMBER+r') base=('+NUMBER+r') port=(\S+)')


def analyze(lines, *, expected_end=None):
    active=None;trial=[];completed=0;requests=0;outputs=0;last_actual=0.;last_target=None
    backwards_actual=0;backwards_requests=0;violations=[];violation_count=0;max_ahead=0.
    rejected=Counter();with_requests=Counter();without_requests=Counter();with_outputs=Counter()
    ticks=set();ports=Counter();last_accept=None;terminal_observation=None
    for text in lines:
        line=text.strip()
        c=CLIENT.fullmatch(line);r=REJECT.fullmatch(line);a=ACCEPT.fullmatch(line)
        advance=ADVANCE.fullmatch(line);output=OUTPUT.fullmatch(line)
        if terminal_observation is not None and (c or r or a or advance or output):
            raise ValueError('Audit activity after terminal bridge observation')
        if c:
            phase,time,name,priority,index,count,breakpoint=c.groups()
            identity=(float.fromhex(time),name,int(priority),int(index),int(count))
            if phase=='before':
                if active is not None:raise ValueError('Nested client callback')
                active={'identity':identity,'requests':0,'outputs':0}
            else:
                if active is None or active['identity']!=identity:raise ValueError('Unmatched client return')
                trial.append(active);active=None;completed+=1
        elif advance or output:
            if active is None:
                # cleanup() resumes VVP once after the final accepted point.
                # Admit only a zero-tick request at the declared endpoint.
                # VPI truncates (target - actual) / tick to uint64_t.
                if advance and expected_end is not None and last_accept is not None:
                    target,actual,base,tick=map(float,advance.groups()[:4])
                    if (not trial and last_accept==last_target==target==base
                            and abs(target-expected_end)<=2*math.ulp(expected_end)
                            and all(map(math.isfinite,(target,actual,base,tick)))
                            and tick in ticks and tick>0
                            and last_actual<=actual<=target
                            and (target-actual)/tick<1 and advance[5]=='0'):
                        terminal_observation={'target':target,'actual':actual,'base':base,'tick':tick}
                        continue
                raise ValueError('Bridge observation outside client callback')
            if advance:
                target,actual,base,tick=map(float,advance.groups()[:4])
                if not all(map(math.isfinite,(target,actual,base,tick))) or min(target,actual,base)<0 or tick<=0:
                    raise ValueError('Invalid bridge request')
                ticks.add(tick);requests+=1;active['requests']+=1
                if last_target is not None and target<last_target:backwards_requests+=1
                last_target=target;max_ahead=max(max_ahead,actual-target)
                # Match the actual bridge guard; do not add a new tolerance.
                if target+tick<actual:
                    violation_count+=1
                    if len(violations)<20:violations.append({'target':target,'actual':actual,'tick':tick,'callbackTime':active['identity'][0]})
            else:
                actual,target,base=map(float,output.groups()[:3])
                if not all(map(math.isfinite,(actual,target,base))) or min(actual,target,base)<0:
                    raise ValueError('Invalid bridge output')
                outputs+=1;active['outputs']+=1;ports[output[4]]+=1
            if actual<last_actual:backwards_actual+=1
            last_actual=actual
        elif r or a:
            if active is not None:raise ValueError('Solver transition inside client callback')
            if r:
                kind=r[1];rejected[kind]+=1
                for group in trial:
                    (with_requests if group['requests'] else without_requests)[kind]+=1
                    if group['outputs']:with_outputs[kind]+=1
            if a:last_accept=float.fromhex(a[1])
            trial=[]
        elif line.startswith(('TIME_AUDIT ','ROLLBACK_AUDIT ')):
            raise ValueError('Malformed bridge/rollback audit record')
    if active is not None or trial or requests==0:raise ValueError('Incomplete bridge audit')
    return {'advanceRequests':requests,'outputCallbacks':outputs,'completedClientCallbacks':completed,
            'terminalBridgeObservation':terminal_observation,
            'hdlTicksSeconds':sorted(ticks),'outputPorts':dict(ports),'rejectedTrials':dict(rejected),
            'callbacksBeforeRejectionWithAdvanceRequests':dict(with_requests),
            'callbacksBeforeRejectionWithoutAdvanceRequests':dict(without_requests),
            'callbacksBeforeRejectionWithOutputs':dict(with_outputs),
            'decreasingRequestedTargets':backwards_requests,'decreasingObservedHdlTime':backwards_actual,
            'maximumObservedHdlAheadOfTargetSeconds':max_ahead,'requestsEarlierThanActualByMoreThanOneTick':violation_count,
            'firstTimeOrderViolations':violations,'timeOrderScreenPassed':violation_count==0 and backwards_actual==0,
            'qualified':False,'boundary':'Observed request/output times in the declared logger window. A callback without a logged request does not prove absence of all internal state changes. No full-repeat or general rollback claim.'}
