"""Time-weighted electrical signatures and explicit interval ambiguity.

Feature envelopes are ranges of simulated cases, never probabilities. Signature
distance is normalized by declared numerical floors and observed healthy spread.
"""
import bisect
import math


def interpolate(rows,time):
    if not rows[0][0]<=time<=rows[-1][0]+1e-12:raise ValueError('window outside recording')
    i=bisect.bisect_right([r[0] for r in rows],time)-1
    if i>=len(rows)-1:return rows[-1][:]
    a,b=rows[i:i+2];f=(time-a[0])/(b[0]-a[0])
    return [time]+[x+f*(y-x) for x,y in zip(a[1:],b[1:])]


def extract(rows,probes,windows):
    result={}
    for window in windows:
        start,stop=window['start'],window['stop']
        if not 0<=start<stop:raise ValueError('invalid feature window')
        data=[interpolate(rows,start)]+[r for r in rows if start<r[0]<stop]+[interpolate(rows,stop)]
        for col,p in enumerate(probes,1):
            values=[r[col] for r in data]
            mean=sum((b[0]-a[0])*(a[col]+b[col])/2 for a,b in zip(data,data[1:]))/(stop-start)
            square=sum((b[0]-a[0])*(a[col]**2+a[col]*b[col]+b[col]**2)/3 for a,b in zip(data,data[1:]))/(stop-start)
            for stat,value in dict(mean=mean,rms=math.sqrt(max(0,square)),minimum=min(values),maximum=max(values),ripple=max(values)-min(values)).items():
                key=p['id']+'|'+window['id']+'|'+stat
                result[key]=dict(value=value,unit=p['unit'],probe_id=p['id'],window=window['id'],statistic=stat)
    return result


def envelope(features):
    if not features:raise ValueError('no accepted feature samples')
    keys=set(features[0])
    if any(set(f)!=keys for f in features):raise ValueError('incompatible features')
    return {key:dict(minimum=min(f[key]['value'] for f in features),maximum=max(f[key]['value'] for f in features),
                     **{k:v for k,v in features[0][key].items() if k!='value'}) for key in sorted(keys)}


def floor(feature):
    # Numerical comparison floors, NOT instrument precision or service limits.
    return {'V':.001,'A':1e-7,'s':1e-9}.get(feature['unit'],1e-9)


def refinement(a,b):
    if a.keys()!=b.keys():raise ValueError('incompatible refinement features')
    failures=[]
    for key,x in a.items():
        y=b[key]['value'];scale=max(abs(x['value']),abs(y),floor(x))
        delta=abs(x['value']-y)
        # Flat ripple near zero is below the declared numerical reporting floor.
        if delta>max(.01*scale,floor(x)):
            failures.append(dict(feature=key,relative_change=delta/scale,absolute_change=delta))
    return dict(passed=not failures,relative_tolerance=.01,numerical_floors={'V':.001,'A':1e-7},failures=failures)


def compare(a,b):
    if a.keys()!=b.keys():raise ValueError('incompatible probe/condition signatures')
    separating=[]
    for key,x in a.items():
        y=b[key];gap=max(y['minimum']-x['maximum'],x['minimum']-y['maximum'])
        if gap>floor(x):separating.append(dict(feature=key,gap=gap,unit=x['unit'],probe_id=x['probe_id']))
    return dict(ambiguous=not separating,separating_features=separating,
                interpretation='Sampled interval overlap only; no probability or exhaustive distinguishability claim.')
