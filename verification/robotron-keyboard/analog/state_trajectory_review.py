#!/usr/bin/env python3
"""Match logged solver trials to saved cable-voltage samples without interpolation."""
import argparse
import json
import math
from pathlib import Path

from analog_driver_replay import sha


def fields(line, skip):
    return dict(item.split('=', 1) for item in line.split()[skip:])


def trials(text):
    result = []
    for line in text.splitlines():
        if line.startswith('TRUNC_AUDIT solver '):
            f = fields(line, 2)
            result.append({'timeSeconds': float.fromhex(f['time']),
                           'deltaSeconds': float.fromhex(f['delta']),
                           'newtonResult': int(f['result']), 'order': int(f['order']),
                           'nodes': {}})
        elif line.startswith('NODE_AUDIT '):
            f = fields(line, 1)
            if not result or float.fromhex(f['time']) != result[-1]['timeSeconds']:
                raise ValueError('Node record without matching trial')
            if f['name'] in result[-1]['nodes']:
                raise ValueError('Duplicate trial node')
            result[-1]['nodes'][f['name']] = float.fromhex(f['oldrhs'])
        elif line.startswith('TRUNC_AUDIT step '):
            f = fields(line, 2)
            if not result or float.fromhex(f['time']) != result[-1]['timeSeconds']:
                raise ValueError('Truncation record without matching trial')
            result[-1]['proposedSeconds'] = float.fromhex(f['proposed'])
    for trial in result:
        nodes = trial.pop('nodes')
        trial['cableDataV'] = nodes['n_cable_daten'] - nodes['host_receiver_gnd']
        if not all(math.isfinite(v) for v in trial.values()):
            raise ValueError('Nonfinite trial')
        if trial['deltaSeconds'] <= 0:
            raise ValueError('Nonpositive trial step')
    if not result:
        raise ValueError('Missing trial records')
    return result


def samples(text):
    lines = text.splitlines()
    expected = ['time', 'v(n_CABLE_DATEN,host_receiver_gnd)',
                'v(n_CABLE_TAKT,host_receiver_gnd)',
                'v(host_data_buffer_input,host_receiver_gnd)',
                'v(host_clock_buffer_input,host_receiver_gnd)',
                'v(host_data_buffer_output,host_receiver_gnd)',
                'v(host_clock_buffer_output,host_receiver_gnd)']
    if not lines or lines[0].split() != expected:
        raise ValueError('Unexpected host trace header')
    result = []
    for line in lines[1:]:
        row = list(map(float, line.split()))
        if len(row) != 7 or not all(map(math.isfinite, row)):
            raise ValueError('Invalid sample')
        if (not result and row[0] != 0) or (result and row[0] <= result[-1][0]):
            raise ValueError('Invalid sample time order or start')
        result.append(row)
    if not result:
        raise ValueError('Missing samples')
    return result


def review(audit, waveform, start, end, excursion):
    if not all(map(math.isfinite, (start, end, excursion))) or not 0 <= start < end or excursion <= 0:
        raise ValueError('Invalid review interval or diagnostic threshold')
    selected = [dict(t) for t in audit if start <= t['timeSeconds'] <= end]
    saved = {r[0]: r for r in waveform if start <= r[0] <= end}
    times = [t['timeSeconds'] for t in selected]
    if not selected or not saved or len(times) != len(set(times)):
        raise ValueError('Missing window evidence or ambiguous repeated trial times')
    prior = [r[0] for r in waveform if r[0] < start]
    if not prior:
        raise ValueError('Missing saved sample preceding audit window')
    previous_saved = prior[-1]
    for trial in selected:
        row = saved.get(trial['timeSeconds'])
        advance = trial['timeSeconds'] - previous_saved
        if advance <= 0:
            raise ValueError('Trial does not advance beyond preceding saved sample')
        trial['previousSavedTimeSeconds'] = previous_saved
        trial['representedAdvanceSeconds'] = advance
        trial['advanceVsDeltaRelativeDifference'] = (advance - trial['deltaSeconds']) / trial['deltaSeconds']
        trial['timeUlpSeconds'] = math.ulp(trial['timeSeconds'])
        trial['savedSample'] = row is not None
        if row is not None and (trial['newtonResult'] != 0 or trial['cableDataV'] != row[1]):
            raise ValueError('Saved sample does not match converged trial voltage exactly')
        if row is not None:
            previous_saved = trial['timeSeconds']
    if set(saved) - set(times):
        raise ValueError('Saved samples lack matching trial records')
    first_trial = next((t for t in selected if abs(t['cableDataV']) > excursion), None)
    first_saved = next((t for t in selected if t['savedSample'] and abs(t['cableDataV']) > excursion), None)
    window = list(saved.values())
    return {'intervalSeconds': [start, end], 'diagnosticExcursionV': excursion,
            'firstExcursionTrial': first_trial, 'firstExcursionSavedSample': first_saved,
            'savedCableDataRangeV': [min(r[1] for r in window), max(r[1] for r in window)],
            'savedBufferInputRangeV': [min(r[3] for r in window), max(r[3] for r in window)],
            'trials': selected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--start', type=float, required=True)
    parser.add_argument('--end', type=float, required=True)
    parser.add_argument('--excursion-v', type=float, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    parent = json.loads((args.run/'report.json').read_text())
    if parent.get('completed') is not False or not parent.get('solverDiagnostic'):
        raise ValueError('Expected a failed diagnostic replay')
    for name, digest in parent['artifacts'].items():
        if sha(args.run/name) != digest:
            raise ValueError('Source artifact differs: '+name)
    result = review(trials((args.run/'ngspice.log').read_text()),
                    samples((args.run/'host-trace.txt').read_text()),
                    args.start, args.end, args.excursion_v)
    result.update(qualified=False, sourceReportSha256=sha(args.run/'report.json'),
                  sources={name: sha(Path(__file__).parent/name) for name in
                           ('state_trajectory_review.py', 'analog_driver_replay.py')},
                  boundary='Exact timestamp and logged oldrhs voltage matches identify saved samples. '
                  'Unsaved trials are not independently classified by rejection cause. '
                  'The excursion threshold is a diagnostic locator, not a device limit or acceptance budget. '
                  'Saved samples from a failed numerical trajectory are not physical predictions. '
                  'Represented time advance is compared with the logged integration step; a mismatch alone does not establish its cause. '
                  'Audit windows do not establish behavior outside their coverage.')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    print(args.out)


if __name__ == '__main__':
    main()
