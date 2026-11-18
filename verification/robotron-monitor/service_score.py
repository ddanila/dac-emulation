"""Measure K7222 service points in a stage bench or connected ngspice run.

This reports the manual's approximate values independently of parameter fitting.
Absent probes and unspecified manual values remain explicit; neither is a pass.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REGISTER = ROOT/'reference/k7222-11/service-observations.json'


def samples(path):
    path = Path(path)
    if path.suffix == '.raw':
        import steady_supply
        yield from steady_supply.raw_rows(path)
        return
    with path.open(newline='') as stream:
        if path.suffix == '.csv':
            reader = csv.DictReader(stream)
            for row in reader:
                yield {key.lower(): float(value) for key, value in row.items() if value}
        else:
            names = next(stream).lower().split()
            if names[0] != 'time' or len(names) != len(set(names)):
                raise ValueError('invalid samples.txt header')
            for line in stream:
                values = [float(value) for value in line.split()]
                if len(values) != len(names):
                    raise ValueError('invalid samples.txt row')
                yield dict(zip(names, values))


def _cycles(times, values, threshold, falling):
    edges = []
    active = lambda v: v < threshold if falling else v > threshold
    for i in range(1, len(values)):
        if active(values[i]) and not active(values[i-1]):
            a, b = values[i-1], values[i]
            fraction = (threshold-a)/(b-a) if b != a else 0.
            edges.append(times[i-1] + fraction*(times[i]-times[i-1]))
    intervals = [b-a for a, b in zip(edges, edges[1:])]
    return edges, sorted(intervals)[len(intervals)//2] if intervals else None


def measure(times, values, waveform):
    if len(times) < 3 or times[-1] <= times[0] or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError('incomplete or nonmonotonic time series')
    if not all(math.isfinite(value) for value in values):
        raise ValueError('nonfinite waveform')
    low, high = min(values), max(values)
    mean = sum((a+b)*(tb-ta)*.5 for a,b,ta,tb in zip(values,values[1:],times,times[1:]))/(times[-1]-times[0])
    ordered = sorted(values)
    median = ordered[len(ordered)//2]
    positive = high-median
    negative = median-low
    polarity = 'positive' if positive > negative*1.5 else 'negative' if negative > positive*1.5 else 'bipolar'
    falling = waveform['polarity'] == 'negative'
    threshold = low + (high-low)*(.25 if falling else .75)
    edges, period = _cycles(times, values, threshold, falling)
    widths = []
    active = lambda v: v < threshold if falling else v > threshold
    begin = times[0] if active(values[0]) else None
    for i in range(1,len(values)):
        if active(values[i]) == active(values[i-1]):continue
        a,b=values[i-1],values[i]
        t=times[i-1]+(threshold-a)/(b-a)*(times[i]-times[i-1]) if b != a else times[i]
        if active(values[i]):begin=t
        elif begin is not None:
            widths.append(t-begin);begin=None
    pulse_width=sorted(widths)[len(widths)//2] if widths else None
    return dict(min_v=low,max_v=high,mean_v=mean,median_v=median,peak_to_peak_v=high-low,
                dominant_excursion=polarity,period_s=period,pulse_width_s=pulse_width,
                observed_edges=len(edges),window_s=times[-1]-times[0],samples=len(times))


def score(path, *, start=None, end=None, required=(), register=REGISTER):
    path=Path(path);register=Path(register)
    if start is not None and end is not None and not start < end:raise ValueError('invalid window')
    source=json.loads(register.read_text())
    if source.get('format')!='dac-monitor-service-observations-v2':raise ValueError('unsupported register')
    wanted={w['model_expression'].lower() for w in source['waveforms']}
    series={name:([],[]) for name in wanted}
    prior=None;rows=0
    for row in samples(path):
        t=row['time']
        if not math.isfinite(t) or prior is not None and t<=prior:raise ValueError('invalid input time order')
        prior=t
        if start is not None and t<start:continue
        if end is not None and t>end:break
        rows+=1
        for name,(ts,vs) in series.items():
            if name in row:ts.append(t);vs.append(row[name])
    if rows<3:raise ValueError('window has fewer than three samples')
    points=[];required=set(required)
    for w in source['waveforms']:
        n=w['test_point'];expression=w['model_expression'].lower()
        ts,vs=series[expression]
        entry=dict(test_point=n,source_node=w['node'],model_expression=expression,
                   role=w['calibration_role'],reference=dict(peak_to_peak_v=w['approximate_swing_v'],
                       peak_to_peak_range_v=w.get('approximate_swing_range_v'),period_s=w['period_s'],
                       pulse_width_s=w['pulse_width_s'],rise_time_s=w.get('rise_time_s'),dc_level_v=w['dc_level_v'],
                       shape_class=w['shape_class'],polarity=w['polarity']),
                   tolerance_fraction=w['acceptance_tolerance'])
        if len(ts)<3:
            entry.update(status='missing-probe',reason='mapped node was not recorded in this run')
        else:
            measured=measure(ts,vs,w);entry['measured']=measured
            expected=w['approximate_swing_v'];bounds=w.get('approximate_swing_range_v')
            if expected is not None:
                error=abs(measured['peak_to_peak_v']-expected)/expected
                entry['amplitude_relative_error']=error
                amplitude_ok=error<=w['acceptance_tolerance']
            elif bounds:
                amplitude_ok=bounds[0]<=measured['peak_to_peak_v']<=bounds[1]
            else:amplitude_ok=False
            checks={'amplitude':amplitude_ok}
            for key in ('period_s','pulse_width_s','dc_level_v'):
                target=w[key]
                # A period inferred from the mode's line/field budget is useful
                # context, but the sketch may have several edges per cycle.
                if target is not None and (key!='period_s' or w.get('period_evidence')!='inferred'):
                    observed=measured['mean_v'] if key=='dc_level_v' else measured[key]
                    checks[key]=observed is not None and abs(observed-target)<=abs(target)*w['acceptance_tolerance']
            # Excursion relative to the median is a diagnostic, not proof of
            # pulse direction for a mixed or asymmetric waveform.
            entry['polarity_match_hint']=(measured['dominant_excursion']==w['polarity'])
            entry['checks']=checks;entry['shape_review']='required'
            entry['status']='pass-numeric' if all(checks.values()) else 'fail-numeric'
        points.append(entry)
    missing=required-{p['test_point'] for p in points}
    if missing:raise ValueError('unknown required test points: '+str(sorted(missing)))
    required_failures=[p['test_point'] for p in points if p['test_point'] in required and p['status']!='pass-numeric']
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    input_hash=digest.hexdigest()
    return dict(format='dac-monitor-service-score-v1',input=str(path),input_sha256=input_hash,
                register_sha256=hashlib.sha256(register.read_bytes()).hexdigest(),requested_window_s=[start,end],
                samples_in_window=rows,required_points=sorted(required),required_failures=required_failures,
                numeric_status='pass' if not required_failures else 'fail',
                qualification='diagnostic-only; shape and source conditions require review',points=points)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path,help='ngspice trace.raw, samples.txt, or CSV with expression columns')
    parser.add_argument('--start',type=float)
    parser.add_argument('--end',type=float)
    parser.add_argument('--require',help='comma-separated points and inclusive ranges, e.g. 1-8,14')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    required=set()
    if args.require:
        for item in args.require.split(','):
            if '-' in item:
                a,b=map(int,item.split('-',1));required.update(range(a,b+1))
            else:required.add(int(item))
    result=score(args.input,start=args.start,end=args.end,required=required)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    for point in result['points']:
        m=point.get('measured',{})
        print(f"{point['test_point']:2} {point['status']:15} {point['model_expression']:24} "
              f"{m.get('peak_to_peak_v',float('nan')):9.3g} Vpp / {point['reference']['peak_to_peak_v'] or point['reference']['peak_to_peak_range_v']}")
    return 2 if result['required_failures'] else 0


if __name__=='__main__':raise SystemExit(main())
