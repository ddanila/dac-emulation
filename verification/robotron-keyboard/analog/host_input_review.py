#!/usr/bin/env python3
"""Review sampled D104 input stress without treating conditional limits as calibration."""
import argparse
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review(samples, limits):
    if len(samples) < 2 or any(len(row) != 2 or not all(map(math.isfinite, row)) for row in samples):
        raise ValueError('Invalid input samples')
    if any(b[0] <= a[0] for a,b in zip(samples,samples[1:])):
        raise ValueError('Input sample times must increase')
    pulses = []
    start = samples[0][0] if samples[0][1] < 0 else None
    minimum = samples[0][1] if start is not None else 0
    for a,b in zip(samples,samples[1:]):
        if a[1] >= 0 and b[1] < 0:
            start = a[0] - a[1]*(b[0]-a[0])/(b[1]-a[1])
            minimum = b[1]
        if start is not None:
            minimum = min(minimum,b[1])
        if a[1] < 0 and b[1] >= 0:
            end = a[0] - a[1]*(b[0]-a[0])/(b[1]-a[1])
            pulses.append({'start':start,'end':end,'durationSeconds':end-start,'minV':minimum,
                           'complete':start > samples[0][0]})
            start = None
    if start is not None:
        pulses.append({'start':start,'end':samples[-1][0],'durationSeconds':samples[-1][0]-start,
                       'minV':minimum,'complete':False})
    low, high = min(v for _,v in samples), max(v for _,v in samples)
    condition = limits['negativePulse']
    relevant = [p for p in pulses if p['minV'] < limits['staticMinV']]
    for p in relevant:
        p['amplitudeAndDurationWithinConditionalLimits'] = (
            p['complete'] and p['minV'] >= condition['minV'] and
            p['durationSeconds'] <= condition['maxDurationSeconds'])
    return {'minV':low,'maxV':high,'negativePulses':pulses,
            'withinStaticVoltageEnvelope':low >= limits['staticMinV'] and high <= limits['maxV'],
            'requiresNegativePulseException':bool(relevant),
            'conditionalAmplitudeAndDurationSatisfied':all(p['amplitudeAndDurationWithinConditionalLimits'] for p in relevant),
            'requiresAboveMaxCurrentException':high > limits['maxV'],
            'dynamicDutyQualified':False,
            'qualified':False,
            'boundary':'Piecewise-linear sampled voltage review only. Pulse duty, input currents, supply/temperature applicability, missed intersample extrema and receiver behavior remain separate.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    args.out.unlink(missing_ok=True)
    producer=args.run/'report.json'
    report=json.loads(producer.read_text())
    if not report.get('hostPassives'):
        raise ValueError('Requires voltages at host buffer inputs, not cable-only traces')
    limits_path=HERE/'d104_limits.json'
    limits=json.loads(limits_path.read_text())
    result={'completed':False,'qualified':False,'producerReportSha256':sha(producer),
            'sources':{name:sha(HERE/name)for name in ('host_input_review.py','d104_limits.json')},
            'deviceSource':limits['source'],'runs':[]}
    for run in report['runs']:
        path=args.run/f"{run['profile']}-{run['stepNs']}ns-{run['cablePf']}pf"
        for name,digest in run['artifacts'].items():
            if sha(path/name)!=digest:raise ValueError('Changed producer artifact: '+name)
        signals=[f'v(host_{label}_buffer_input,host_receiver_gnd)' for label in ('data','clock')]
        if run['signals'][:2]!=signals:raise ValueError('Wrong voltage observation nodes')
        rows=[list(map(float,line.split()))for line in (path/'trace.txt').read_text().splitlines()[1:]]
        if (not rows or any(len(row)!=len(run['signals'])+1 or not all(map(math.isfinite,row)) for row in rows)
                or rows[0][0]>1e-9 or abs(rows[-1][0]-40e-6)>1e-12
                or any(b[0]-a[0]>run['stepNs']*1e-9+1e-15 for a,b in zip(rows,rows[1:]))):
            raise ValueError('Incomplete host trace')
        result['runs'].append({'profile':run['profile'],'stepNs':run['stepNs'],'cablePf':run['cablePf'],
                               'traceSha256':sha(path/'trace.txt'),
                               'inputs':{label:review([[row[0],row[i+1]]for row in rows],limits['input'])for i,label in enumerate(('data','clock'))}})
    if not result['runs']:raise ValueError('No host input captures')
    result['completed']=True
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(args.out)


if __name__=='__main__':main()
