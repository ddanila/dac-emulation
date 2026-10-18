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
    samples = iter(samples)
    def valid(row):
        if len(row) != 2 or not all(map(math.isfinite, row)):
            raise ValueError('Invalid input samples')
        return row
    try:
        first = valid(next(samples))
    except StopIteration:
        raise ValueError('No input samples') from None
    previous = first
    count = 1
    low = high = first[1]
    pulses = []
    start = first[0] if first[1] < 0 else None
    minimum = first[1] if start is not None else 0
    for row in samples:
        a, b = previous, valid(row)
        if b[0] <= a[0]:
            raise ValueError('Input sample times must increase')
        count += 1
        low, high = min(low, b[1]), max(high, b[1])
        previous = b
        if a[1] >= 0 and b[1] < 0:
            start = a[0] - a[1]*(b[0]-a[0])/(b[1]-a[1])
            minimum = b[1]
        if start is not None:
            minimum = min(minimum,b[1])
        if a[1] < 0 and b[1] >= 0:
            end = a[0] - a[1]*(b[0]-a[0])/(b[1]-a[1])
            pulses.append({'start':start,'end':end,'durationSeconds':end-start,'minV':minimum,
                           'complete':start > first[0]})
            start = None
    if count < 2:
        raise ValueError('Insufficient input samples')
    if start is not None:
        pulses.append({'start':start,'end':previous[0],'durationSeconds':previous[0]-start,
                       'minV':minimum,'complete':False})
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


def firmware_samples(path, signals, channel, end_seconds, step_ns):
    """Validate observation nodes and capture extent while streaming one input."""
    from trace_io import open_text
    expected = [f'v(host_{label}_buffer_input,host_receiver_gnd)' for label in ('data', 'clock')]
    if len(signals) != 6 or signals[2:4] != expected:
        raise ValueError('Wrong firmware host input observation nodes')
    if not math.isfinite(end_seconds) or end_seconds <= 0 or not math.isfinite(step_ns) or step_ns <= 0:
        raise ValueError('Invalid capture duration or timestep')
    with open_text(path) as stream:
        if stream.readline().split() != ['time', *signals]:
            raise ValueError('Host waveform header differs from report')
        previous = None
        for line in stream:
            row = list(map(float, line.split()))
            if len(row) != 7 or not all(map(math.isfinite, row)):
                raise ValueError('Invalid host waveform row')
            if previous is None:
                if abs(row[0]) > 1e-15:
                    raise ValueError('Missing host waveform start')
            elif not 0 < row[0] - previous <= step_ns * 1e-9 + 1e-15:
                raise ValueError('Host waveform time order or gap')
            previous = row[0]
            yield row[0], row[3 + channel]
        if previous is None or abs(previous - end_seconds) > 1e-12:
            raise ValueError('Incomplete host waveform extent')


def firmware_review(directory, limits):
    from compare_firmware_io import load_run
    import re
    report, _ = load_run(directory)
    if not report['assumptions'].get('hostBuffer') or report.get('qualified') is not False:
        raise ValueError('Requires an experimental host-buffer service run')
    deck = (directory / 'io.cir').read_text()
    analyses = re.findall(r'^\.?tran [0-9.eE+-]+n ([0-9.eE+-]+)n$', deck, re.M)
    if len(analyses) != 1:
        raise ValueError('Missing unambiguous executed analysis duration')
    end_seconds = float(analyses[0]) * 1e-9
    return {'boundary': 'Service firmware capture; CPU clock/reset externally supplied',
            'traceSha256': report['hostTraceSha256'],
            'inputs': {label: review(firmware_samples(directory / 'host-trace.txt',
                        report['hostTraceSignals'], i, end_seconds,
                        report['assumptions']['stepNs']), limits['input'])
                       for i, label in enumerate(('data', 'clock'))}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--firmware',action='store_true',help='Review a retained host-buffer service firmware capture')
    args=parser.parse_args()
    args.out.unlink(missing_ok=True)
    producer=args.run/'report.json'
    report=json.loads(producer.read_text())
    if not args.firmware and not report.get('hostPassives'):
        raise ValueError('Requires voltages at host buffer inputs, not cable-only traces')
    limits_path=HERE/'d104_limits.json'
    limits=json.loads(limits_path.read_text())
    result={'completed':False,'qualified':False,'producerReportSha256':sha(producer),
            'sources':{name:sha(HERE/name)for name in ('host_input_review.py','d104_limits.json')},
            'deviceSource':limits['source'],'runs':[]}
    if args.firmware:
        result['runs'].append(firmware_review(args.run, limits))
        from compare_firmware_io import sha as trace_sha
        for name in ('trace_io.py', 'compare_firmware_io.py', 'transient_analysis.py', 'serial_observation.py', 'led_observation.py', 'failure_evidence.py'):
            result['sources'][name] = trace_sha(HERE / name)
    for run in ([] if args.firmware else report['runs']):
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
