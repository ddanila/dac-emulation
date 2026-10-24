#!/usr/bin/env python3
"""Exact sensitivity of logged divided differences to hypothetical charge rounding."""
import argparse
import json
import lzma
import math
from decimal import Decimal, localcontext
from fractions import Fraction as F
from pathlib import Path
from filter_truncation_log import filter_truncation_record
from ttl7406_probe import sha

HERE = Path(__file__).resolve().parent


def exact_difference(values, deltas, order):
    if order not in (1,2) or len(values) != order+2 or len(deltas) != order+1 or any(d <= 0 for d in deltas):
        raise ValueError('Invalid history shape')
    diff=list(values); original=list(deltas); spans=list(deltas)
    for count in range(order+1,0,-1):
        for i in range(count):diff[i]=(diff[i]-diff[i+1])/spans[i]
        for i in range(count-1):spans[i]=spans[i+1]+original[i]
    return diff[0]


def sensitivity(values, deltas, order):
    if not all(math.isfinite(v) for v in values+deltas):
        raise ValueError('Nonfinite history')
    q=list(map(F.from_float,values)); dt=list(map(F.from_float,deltas))
    value=exact_difference(q,dt,order)
    weights=[]
    for i in range(len(q)):
        basis=[F(0)]*len(q);basis[i]=F(1)
        weights.append(exact_difference(basis,dt,order))
    half_ulps=[F.from_float(math.ulp(v))/2 for v in values]
    radius=sum((abs(w)*u for w,u in zip(weights,half_ulps)),F(0))
    return {'difference':value,'weights':weights,'halfUlps':half_ulps,'radius':radius,
            'relativeRadius':radius/abs(value) if value else None,
            'intervalIncludesZero':abs(value)<=radius}


def decimal(value):
    if value is None:return None
    with localcontext() as context:
        context.prec=64
        return str(Decimal(value.numerator)/Decimal(value.denominator))


def step_policy_screen(delta, proposed):
    if not all(math.isfinite(x) and x > 0 for x in (delta, proposed)):
        raise ValueError('Invalid candidate step')
    # ngspice CKTtrunc caps growth at 2*delta; dctran accepts only >0.9*delta.
    # Other devices, order checks and event breakpoints still affect the outcome.
    return {'belowGrowthCap': proposed < 2*delta,
            'atOrBelowRejectionThreshold': proposed <= .9*delta}


def policy_summary():
    return {'records':0, 'maximumRelativeRadius':None, 'worstWitness':None}


def retain(source, out):
    # Require the retained full-waveform controls before using the diagnostic log.
    manifest=json.loads((source/'manifest.json').read_text())
    for name,digest in manifest.items():
        if sha(source/name)!=digest:raise ValueError('Changed filter evidence: '+name)
    prior=json.loads((source/'assessment.json').read_text())
    if set(prior['cases'])!={'disabled','enabled'} or not all(c['completed'] and c['allFiveWaveformsByteIdenticalToBaseline'] for c in prior['cases'].values()):
        raise ValueError('Missing waveform-preserving controls')
    states={}; records=0
    policy={name:policy_summary() for name in ('atOrAboveGrowthCap','belowGrowthCap','atOrBelowRejectionThreshold')}
    with lzma.open(source/'enabled/ngspice.log.xz','rt') as stream:
        for line in stream:
            line=line.rstrip('\n')
            if not filter_truncation_record(line):continue
            raw=dict(item.split('=',1) for item in line.split()[2:]);order=int(raw['order']);state=raw['state']
            values=[float.fromhex(raw['q'+str(i)]) for i in range(order+2)]
            deltas=[float.fromhex(raw['dt'+str(i)]) for i in range(order+1)]
            result=sensitivity(values,deltas,order);records+=1
            screen=step_policy_screen(float.fromhex(raw['delta']),float.fromhex(raw['proposed']))
            groups=['belowGrowthCap' if screen['belowGrowthCap'] else 'atOrAboveGrowthCap']
            if screen['atOrBelowRejectionThreshold']:groups.append('atOrBelowRejectionThreshold')
            for group in groups:
                summary=policy[group];summary['records']+=1;ratio=result['relativeRadius']
                if ratio is not None and (summary['maximumRelativeRadius'] is None or ratio>summary['maximumRelativeRadius']):
                    summary['maximumRelativeRadius']=ratio
                    summary['worstWitness']={'logged':raw,'instance':prior['analysis']['states'][state]['instance'],
                        'exactDifference':decimal(result['difference']),'halfUlpRadius':decimal(result['radius'])}
            entry=states.setdefault(state,{'instance':prior['analysis']['states'][state]['instance'],
                'records':0,'intervalIncludesZero':0,'zeroDifferenceRecords':0,'maximumRelativeRadius':None,'worstWitness':None})
            entry['records']+=1;entry['intervalIncludesZero']+=result['intervalIncludesZero'];entry['zeroDifferenceRecords']+=result['difference']==0
            ratio=result['relativeRadius']
            # Compare exact rational ratios; decimal strings are presentation only.
            if ratio is not None and (entry['maximumRelativeRadius'] is None or ratio>entry['maximumRelativeRadius']):
                entry['maximumRelativeRadius']=ratio
                entry['worstWitness']={'logged':raw,'exactDifference':decimal(result['difference']),
                    'halfUlpRadius':decimal(result['radius']), 'weights':[decimal(w) for w in result['weights']],
                    'halfUlps':[decimal(u) for u in result['halfUlps']],
                    'interval':[decimal(result['difference']-result['radius']),decimal(result['difference']+result['radius'])]}
    if records!=prior['analysis']['records']:raise ValueError('Diagnostic record count differs')
    for entry in states.values():entry['maximumRelativeRadius']=decimal(entry['maximumRelativeRadius'])
    for entry in policy.values():entry['maximumRelativeRadius']=decimal(entry['maximumRelativeRadius'])
    result={'schema':1,'records':records,'states':states,'stepPolicyScreens':policy,'qualified':False,
        'filterAssessmentSha256':sha(source/'assessment.json'),'filterLogSha256':sha(source/'enabled/ngspice.log.xz'),
        'scope':'Exact rational propagation of independent hypothetical ±half-current-ULP perturbations of the logged binary64 charge/flux histories, with time history fixed. This is a sensitivity box, not a bound on actual nonlinear-evaluation or accumulated history error. The step-policy screens compare each proposal with CKTtrunc’s 2*delta growth cap and dctran’s 0.9*delta acceptance threshold. A proposal above the growth cap does not constrain that cap; proposals below it can still be superseded by other devices, order changes or event breakpoints. They do not identify final accepted or rejected steps; counts depend on device order. The symmetric box can conservatively exceed the rounding cell at binade boundaries. No voltage-error correction, acceptance waiver or production change follows.',
        'sources':{n:sha(HERE/n) for n in ('charge_history_sensitivity.py','filter_truncation_log.py','startup_truncation_log.py')}}
    out.mkdir(parents=True,exist_ok=False)
    (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'manifest.json').write_text(json.dumps({'assessment.json':sha(out/'assessment.json')},indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,required=True);parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    result=retain(args.source,args.out)
    print(json.dumps({k:{n:v for n,v in s.items() if n!='worstWitness'} for k,s in result['states'].items()},indent=2))
