"""Observe actual saved samples at requested diagnostic times; never interpolate."""
import math


def samples_at(rows, times):
    if not times or times != sorted(set(times)) or not all(math.isfinite(t) for t in times):
        raise ValueError('Expected sorted finite unique times')
    result=[];previous=None;index=0
    for row in rows:
        if previous is not None and row[0]<=previous[0]:
            raise ValueError('Non-increasing trace')
        while index<len(times) and times[index]<=row[0]:
            t=times[index]
            if previous is None and t<row[0]:raise ValueError('Uncovered time')
            chosen=min((previous,row) if previous is not None else (row,),key=lambda r:abs(r[0]-t))
            result.append({'requestedSeconds':t,'actualSeconds':chosen[0],
                           'timeErrorSeconds':chosen[0]-t,'exactTime':chosen[0]==t,
                           'values':list(chosen[1:])})
            index+=1
        previous=row
    if index!=len(times):raise ValueError('Uncovered time')
    return result


def compare_native(a, b, signals):
    if len(a)!=len(b) or not a or any(x['requestedSeconds']!=y['requestedSeconds'] for x,y in zip(a,b)):
        raise ValueError('Different requested times')
    if any(len(row['values'])!=len(signals) for rows in (a,b) for row in rows):
        raise ValueError('Different signal width')
    offsets=[abs(x['actualSeconds']-y['actualSeconds']) for x,y in zip(a,b)]
    result={'identicalActualTimes':all(t==0 for t in offsets),'maximumTimeDifferenceSeconds':max(offsets),'signals':None}
    if result['identicalActualTimes']:
        result['signals']={}
        for i,signal in enumerate(signals):
            difference,time=max((abs(x['values'][i]-y['values'][i]),x['actualSeconds']) for x,y in zip(a,b))
            result['signals'][signal]={'maximumAbsoluteDifference':difference,'timeSeconds':time}
    return result
