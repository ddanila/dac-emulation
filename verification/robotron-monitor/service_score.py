"""Measure K7222 service points in a stage bench or connected ngspice run.

This reports the manual's approximate values independently of parameter fitting.
Absent probes and unspecified manual values remain explicit; neither is a pass.
"""
import argparse
import bisect
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REGISTER = ROOT/'reference/k7222-11/service-observations.json'
INSTRUMENT = ROOT/'reference/k7222-11/service-instrument.json'


def bandwidth_response(times, values, bandwidth_hz):
    """One-pole oscilloscope response to linearly interpolated trace samples."""
    if not math.isfinite(bandwidth_hz) or bandwidth_hz <= 0:
        raise ValueError('invalid instrument bandwidth')
    tau=1/(2*math.pi*bandwidth_hz)
    output=[values[0]]
    for a,b,u0,u1 in zip(times,times[1:],values,values[1:]):
        dt=b-a
        if dt<=0:raise ValueError('nonmonotonic instrument input')
        slope=(u1-u0)/dt
        decay=math.exp(-dt/tau)
        output.append(u1-slope*tau+(output[-1]-u0+slope*tau)*decay)
    return output


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


def _time_above(times, values, threshold):
    """Fraction above threshold, interpolating crossings on irregular samples."""
    above = 0.
    for a, b, ta, tb in zip(values, values[1:], times, times[1:]):
        duration = tb-ta
        if a >= threshold and b >= threshold:
            above += duration
        elif a < threshold and b < threshold:
            continue
        else:
            crossing = (threshold-a)/(b-a)
            above += duration*(crossing if a >= threshold else 1-crossing)
    return above/(times[-1]-times[0])


def _phase_profile(times, values, period, bins=64):
    """Fold complete cycles; one final field is sufficient after settling."""
    if not period or period <= 0:
        return None
    if any(b-a > period/16 for a,b in zip(times,times[1:])):
        return None
    duration = times[-1]-times[0]
    if duration < .98*period:
        return None
    # The connected scorer selects exactly one final field. Its boundary may
    # differ from the manual period by a small rounding error.
    period_used = min(period,duration) if duration < period else period
    cycles = max(1,int(duration/period_used))
    cycles = min(cycles, 1000)
    sums = [0.]*bins
    for cycle in range(cycles):
        origin = times[0]+cycle*period_used
        for slot in range(bins):
            target = origin+(slot+.5)*period_used/bins
            right = bisect.bisect_left(times, target)
            if right == 0 or right == len(times):
                return None
            left = right-1
            fraction = (target-times[left])/(times[right]-times[left])
            sums[slot] += values[left]+fraction*(values[right]-values[left])
    return [value/cycles for value in sums]


def shape_checks(times, values, waveform, measured):
    """Check only features legible in the service-manual sketches."""
    descriptor = waveform['shape_descriptor']
    span = measured['peak_to_peak_v']
    if span <= 0:
        return {'nonflat':False}, {}
    family = descriptor['family']
    checks = {}
    if family == 'pulse':
        polarity = descriptor['pulse_polarity']
        above = _time_above(times, values, (measured['min_v']+measured['max_v'])/2)
        duty = above if polarity == 'positive' else 1-above
        checks['pulse_polarity'] = polarity in ('positive','negative') and 0 < duty <= .55
        checks['repeated_pulse'] = measured['observed_edges'] >= 2
        sampling_period = descriptor.get('sampling_period_s', waveform['period_s'])
        checks['sample_resolution'] = (sampling_period is not None
            and max(b-a for a,b in zip(times,times[1:])) <= sampling_period/16)
        if waveform['period_s'] is not None:
            period = measured['period_s']
            checks['period_match'] = (period is not None
                and abs(period-waveform['period_s']) <= .1*waveform['period_s'])
        if 'duty_fraction_range' in descriptor:
            lo, hi = descriptor['duty_fraction_range']
            checks['duty_fraction'] = lo <= duty <= hi
        return checks, {'active_fraction':duty,'positive_fraction':above}
    if family in ('rising-sawtooth','falling-sawtooth'):
        profile = _phase_profile(times, values, waveform['period_s'])
        if profile is None:
            return {'complete_cycles':False}, {}
        differences = [b-a for a,b in zip(profile,profile[1:]+profile[:1])]
        threshold = .002*span
        increasing = sum(d > threshold for d in differences)
        decreasing = sum(d < -threshold for d in differences)
        total = increasing+decreasing
        rising = family == 'rising-sawtooth'
        direction = increasing if rising else decreasing
        reset = -min(differences) if rising else max(differences)
        checks['ramp_direction'] = total > 0 and direction/total >= .65
        checks['sharp_reset'] = reset >= .15*span
        return checks, {'direction_fraction':direction/total if total else None,
                        'reset_fraction':reset/span}
    if family == 'bipolar-ramp':
        baseline = descriptor['baseline_v']
        checks['crosses_baseline'] = (measured['min_v'] < baseline-.15*span
                                     and measured['max_v'] > baseline+.15*span)
        profile = _phase_profile(times, values, waveform['period_s'])
        checks['complete_cycles'] = profile is not None
        if profile is not None:
            differences = [b-a for a,b in zip(profile,profile[1:]+profile[:1])]
            checks['steep_rise'] = max(differences) >= .1*span
        return checks, {'baseline_v':baseline}
    raise ValueError('unknown manual shape family: '+str(family))


def score(path, *, start=None, end=None, required=(), register=REGISTER,
          probe_manifest=None, stimulus=None):
    path=Path(path);register=Path(register)
    if start is not None and end is not None and not start < end:raise ValueError('invalid window')
    if stimulus not in (None,'grid'):raise ValueError('unknown service waveform stimulus')
    if probe_manifest is not None and register.resolve()!=REGISTER.resolve():
        raise ValueError('probe manifest requires the current service point register')
    source=json.loads(register.read_text())
    if source.get('format')!='dac-monitor-service-observations-v2':raise ValueError('unsupported register')
    instrument=json.loads(INSTRUMENT.read_text())
    if instrument.get('format')!='dac-monitor-service-instrument-v1':
        raise ValueError('unsupported service instrument model')
    bandwidth=instrument['vertical_bandwidth_hz']['value']
    conditions={item['id']:item for item in source['waveform_conditions']}
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
    loaded_traces={}
    if probe_manifest is not None:
        import service_probe
        loaded_traces=service_probe.validate(probe_manifest,path)
    for w in source['waveforms']:
        n=w['test_point'];expression=w['model_expression'].lower()
        condition=conditions[w['condition_id']]
        ts,vs=series[expression]
        entry=dict(test_point=n,source_node=w['node'],model_expression=expression,
                   role=w['calibration_role'],reference=dict(peak_to_peak_v=w['approximate_swing_v'],
                       peak_to_peak_range_v=w.get('approximate_swing_range_v'),period_s=w['period_s'],
                       pulse_width_s=w['pulse_width_s'],rise_time_s=w.get('rise_time_s'),dc_level_v=w['dc_level_v'],
                       shape_class=w['shape_class'],polarity=w['polarity'],
                       shape_descriptor=w['shape_descriptor'],
                       condition_id=w['condition_id'],instrument=condition['instrument'],
                       operating_conditions=condition['manual_note'],
                       manual_stimulus=condition['manual_stimulus'],
                       scoring_stimulus=condition['scoring_stimulus']),
                   tolerance_fraction=w['acceptance_tolerance'])
        if len(ts)<3:
            entry.update(status='missing-probe',reason='mapped node was not recorded in this run')
        else:
            entry['raw_measured']=measure(ts,vs,w)
            observed_times,observed_values=ts,vs
            if n in loaded_traces:
                observed_times=[];observed_values=[];prior_loaded=None
                for row in samples(loaded_traces[n]):
                    t=row['time']
                    if not math.isfinite(t) or prior_loaded is not None and t<=prior_loaded:
                        raise ValueError(f'invalid loaded trace time order at point {n}')
                    prior_loaded=t
                    if start is not None and t<start:continue
                    if end is not None and t>end:break
                    if expression in row:
                        observed_times.append(t);observed_values.append(row[expression])
                if len(observed_times)<3 or observed_times[0]>ts[0]+2*max(b-a for a,b in zip(ts,ts[1:])) or observed_times[-1]<ts[-1]-2*max(b-a for a,b in zip(ts,ts[1:])):
                    raise ValueError(f'loaded trace does not cover the scoring window at point {n}')
                entry['loaded_unfiltered_measured']=measure(observed_times,observed_values,w)
                entry['probe_trace']=str(loaded_traces[n])
                entry['instrument_model_status']='circuit probe load and bandwidth applied'
            else:
                entry['instrument_model_status']='bandwidth-applied; probe loading pending'
            scope_values=bandwidth_response(observed_times,observed_values,bandwidth)
            measured=measure(observed_times,scope_values,w);entry['measured']=measured
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
            shape,features=shape_checks(observed_times,scope_values,w,measured)
            entry['shape_checks']=shape;entry['shape_features']=features
            entry['shape_status']='pass' if all(shape.values()) else 'fail'
            entry['checks']=checks
            entry['status']='pass-numeric' if all(checks.values()) else 'fail-numeric'
        points.append(entry)
    missing=required-{p['test_point'] for p in points}
    if missing:raise ValueError('unknown required test points: '+str(sorted(missing)))
    required_failures=[p['test_point'] for p in points if p['test_point'] in required
                       and (p['status']!='pass-numeric' or p.get('shape_status')!='pass')]
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    input_hash=digest.hexdigest()
    numeric_failures=[p['test_point'] for p in points if p['test_point'] in required
                      and p['status']!='pass-numeric']
    shape_failures=[p['test_point'] for p in points if p['test_point'] in required
                    and p.get('shape_status')!='pass']
    loaded_points=sorted(p['test_point'] for p in points
                         if p.get('instrument_model_status')=='circuit probe load and bandwidth applied')
    loading_complete=bool(required) and required<=set(loaded_points)
    modeled=loading_complete and stimulus=='grid'
    if modeled:
        qualification='probe-and-bandwidth-modeled grid comparison; manual values are guidelines'
    elif loading_complete:
        qualification='diagnostic-only; grid stimulus not established'
    elif stimulus=='grid':
        qualification='diagnostic-only; required probe loads incomplete'
    else:
        qualification='diagnostic-only; probe loading and grid stimulus not established'
    return dict(format='dac-monitor-service-score-v1',input=str(path),input_sha256=input_hash,
                register_sha256=hashlib.sha256(register.read_bytes()).hexdigest(),requested_window_s=[start,end],
                instrument_model_sha256=hashlib.sha256(INSTRUMENT.read_bytes()).hexdigest(),
                instrument_loading_status=('required points circuit-loaded' if loading_complete
                                           else instrument['probe_loading_status']),
                probe_manifest=str(Path(probe_manifest).resolve()) if probe_manifest is not None else None,
                probe_manifest_sha256=(hashlib.sha256(Path(probe_manifest).read_bytes()).hexdigest()
                                       if probe_manifest is not None else None),
                probe_loaded_points=loaded_points,stimulus=stimulus,
                samples_in_window=rows,required_points=sorted(required),required_failures=required_failures,
                numeric_status='pass' if not numeric_failures else 'fail',
                shape_status='pass' if not shape_failures else 'fail',
                qualification=qualification,
                points=points)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path,help='ngspice trace.raw, samples.txt, or CSV with expression columns')
    parser.add_argument('--start',type=float)
    parser.add_argument('--end',type=float)
    parser.add_argument('--require',help='comma-separated points and inclusive ranges, e.g. 1-8,14')
    parser.add_argument('--probe-manifest',type=Path,help='manifest from service_probe.py with separate loaded solves')
    parser.add_argument('--stimulus',choices=('grid',),help='declare the scoring input when the manual does not')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    required=set()
    if args.require:
        for item in args.require.split(','):
            if '-' in item:
                a,b=map(int,item.split('-',1));required.update(range(a,b+1))
            else:required.add(int(item))
    result=score(args.input,start=args.start,end=args.end,required=required,
                 probe_manifest=args.probe_manifest,stimulus=args.stimulus)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    for point in result['points']:
        m=point.get('measured',{})
        print(f"{point['test_point']:2} {point['status']:15} {point['model_expression']:24} "
              f"{m.get('peak_to_peak_v',float('nan')):9.3g} Vpp / {point['reference']['peak_to_peak_v'] or point['reference']['peak_to_peak_range_v']}")
    return 2 if result['required_failures'] else 0


if __name__=='__main__':raise SystemExit(main())
