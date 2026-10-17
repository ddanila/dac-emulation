#!/usr/bin/env python3
"""Measure sampled cable-data stability around observed firmware receiver edges."""
import argparse
import json
import math
from pathlib import Path
from trace_io import open_text

from compare_firmware_io import load_run, sha


def measure(trace, received, maximum_step_ns, required_ns=100, *, columns=3, data_column=1):
    if columns not in (3, 5) or not 0 < data_column < columns:
        raise ValueError('Invalid receiver trace column layout')
    if not received:
        raise ValueError('No receiver activity to qualify')
    intervals, active = [], None
    previous, first, count, maximum_gap = None, None, 0, 0
    with open_text(trace) as stream:
        next(stream)
        for line in stream:
            row = [float(x) for x in line.split()]
            if len(row) != columns or not all(map(math.isfinite, row)):
                raise ValueError('Invalid receiver waveform')
            time, data = row[0], row[data_column]
            if previous is not None:
                if time < previous:
                    raise ValueError('Waveform time reversal')
                maximum_gap = max(maximum_gap, time - previous)
            first = time if first is None else first
            level = 0 if data < .8 else 1 if data > 2 else None
            if active is not None and level != active['wireLevel']:
                intervals.append(active)
                active = None
            if level is not None:
                if active is None:
                    active = {'wireLevel': level, 'firstValidSampleSeconds': time,
                              'leftCensored': count == 0, 'rightCensored': False}
                active['lastValidSampleSeconds'] = time
            previous = time
            count += 1
    if active is not None:
        active['rightCensored'] = True
        intervals.append(active)
    # wrdata decimal formatting can round neighboring timestamps by about 1 ns.
    if not count or maximum_gap > (maximum_step_ns + 1) * 1e-9:
        raise ValueError('Waveform has missing samples or gaps beyond the declared timestep')
    events = []
    for stamp, bit in received:
        time = stamp * 1e-12
        candidates = [interval for interval in intervals
                      if interval['wireLevel'] == 1 - bit
                      and interval['firstValidSampleSeconds'] <= time <= interval['lastValidSampleSeconds']]
        if len(candidates) != 1:
            raise ValueError('Receiver bit lacks a unique stable voltage interval')
        interval = candidates[0]
        setup = (time - interval['firstValidSampleSeconds']) * 1e9
        hold = (interval['lastValidSampleSeconds'] - time) * 1e9
        events.append({'timePs': stamp, 'logicalBit': bit, **interval,
                       'sampledSetupNs': setup, 'sampledHoldNs': hold,
                       'withinBudget': min(setup, hold) >= required_ns})
    return {'thresholdVolts': [.8, 2], 'requiredSetupHoldNs': required_ns,
            'minimumSampledSetupNs': min(event['sampledSetupNs'] for event in events),
            'minimumSampledHoldNs': min(event['sampledHoldNs'] for event in events),
            'maximumSampleGapNs': maximum_gap * 1e9, 'waveformRows': count,
            'waveformStartSeconds': first, 'waveformEndSeconds': previous,
            'withinBudget': all(event['withinBudget'] for event in events), 'events': events,
            'interpretation': 'Conservative sampled stability intervals; endpoints may be censored by trace boundaries. '
                              'The budget is a fixture assumption, not a historical receiver specification.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    p.add_argument('--required-ns', type=float, default=100)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    if not math.isfinite(args.required_ns) or args.required_ns <= 0:
        p.error('required-ns must be positive and finite')
    result = {'passed': False, 'scope': __doc__,
              'validationSources': {name: sha(Path(__file__).resolve().parent / name) for name in
                                    ('receiver_margins.py', 'compare_firmware_io.py', 'serial_observation.py', 'led_observation.py', 'trace_io.py')}}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    try:
        original, transport = load_run(args.directory)
        result['originalReportSha256'] = sha(args.directory / 'report.json')
        result['traceSha256'] = original['traceSha256']
        result['observations'] = measure(args.directory / 'trace.txt', transport['received'],
                                         original['assumptions']['stepNs'], args.required_ns)
        if not result['observations']['withinBudget']:
            raise ValueError('Sampled receiver setup/hold does not meet the declared fixture budget')
        result['passed'] = True
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(args.out)


if __name__ == '__main__':
    main()
