"""Explore the long TP8 falling ramp without scoring the unresolved 10 V arrow.

The manual sketch marks a shoulder-to-trough excursion, whereas the current
stage has a brief reset undershoot. This fits the longest approximately linear
falling part of a field and reports its sensitivity; it is not an A3 gate.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import service_score


def long_falling_ramp(times, values, period, *, bins=128,
                      max_rms_fraction=.02, min_duration_fraction=.65):
    if bins < 16 or not 0 < max_rms_fraction < 1 or not 0 < min_duration_fraction < 1:
        raise ValueError('invalid falling-ramp feature parameters')
    profile=service_score._phase_profile(times,values,period,bins=bins)
    if profile is None:
        return None
    span=max(profile)-min(profile)
    if span <= 0:
        return None
    doubled=profile+profile
    sx=[0.];sxx=[0.];sy=[0.];syy=[0.];sxy=[0.]
    for i,value in enumerate(doubled):
        sx.append(sx[-1]+i);sxx.append(sxx[-1]+i*i)
        sy.append(sy[-1]+value);syy.append(syy[-1]+value*value)
        sxy.append(sxy[-1]+i*value)
    minimum=math.ceil(min_duration_fraction*bins)
    for length in range(bins,minimum-1,-1):
        best=None
        for start in range(bins):
            stop=start+length
            x=sx[stop]-sx[start];xx=sxx[stop]-sxx[start]
            y=sy[stop]-sy[start];yy=syy[stop]-syy[start]
            xy=sxy[stop]-sxy[start]
            denominator=length*xx-x*x
            slope=(length*xy-x*y)/denominator
            if slope >= 0:
                continue
            intercept=(y-slope*x)/length
            rms=math.sqrt(max(0.,yy-intercept*y-slope*xy)/length)
            if rms > max_rms_fraction*span:
                continue
            candidate=(rms,start,slope)
            if best is None or candidate[:2] < best[:2]:
                best=candidate
        if best is not None:
            rms,start,slope=best
            return dict(excursion_v=-slope*(length-1),
                        duration_fraction=length/bins,fit_rms_v=rms,
                        fit_rms_fraction=rms/span,span_v=span,
                        bins=bins,start_bin=start,end_bin=(start+length-1)%bins,
                        max_rms_fraction=max_rms_fraction,
                        min_duration_fraction=min_duration_fraction)
    return None


def from_trace(path, expression, start, end, period, *, bins=128,
               max_rms_fraction=.02):
    rows=[row for row in service_score.samples(path) if start <= row['time'] <= end]
    expression=expression.lower()
    if len(rows)<3 or any(expression not in row for row in rows):
        raise ValueError('trace is missing the requested window or expression')
    times=[row['time'] for row in rows]
    values=service_score.bandwidth_response(
        times,[row[expression] for row in rows],
        json.loads(service_score.INSTRUMENT.read_text())['vertical_bandwidth_hz']['value'])
    feature=long_falling_ramp(times,values,period,bins=bins,
                              max_rms_fraction=max_rms_fraction)
    return dict(format='dac-monitor-tp8-ramp-feature-v1',qualification='diagnostic only',
                trace=str(Path(path)),trace_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                expression=expression,window_s=[start,end],period_s=period,
                samples=len(rows),feature=feature)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace',type=Path)
    parser.add_argument('expression')
    parser.add_argument('--start',type=float,required=True)
    parser.add_argument('--end',type=float,required=True)
    parser.add_argument('--period',type=float,required=True)
    parser.add_argument('--bins',type=int,default=128)
    parser.add_argument('--max-rms-fraction',type=float,default=.02)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=from_trace(args.trace,args.expression,args.start,args.end,args.period,
                      bins=args.bins,max_rms_fraction=args.max_rms_fraction)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['feature'],indent=2))


if __name__=='__main__':
    main()
