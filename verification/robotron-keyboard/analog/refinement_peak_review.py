#!/usr/bin/env python3
"""Inspect retained absolute-time voltage maxima without changing their acceptance."""
import argparse
import json
from decimal import Decimal, localcontext
from pathlib import Path
from host_waveform_comparison import rows
from ttl7406_probe import sha

HERE = Path(__file__).resolve().parent


def interpolate(bracket, time):
    with localcontext() as context:
        context.prec = 64
        (ta, va), (tb, vb) = [[Decimal.from_float(float(x)) for x in row] for row in bracket]
        t = Decimal.from_float(float(time))
        if not ta <= t <= tb or ta == tb:
            raise ValueError('Invalid interpolation bracket')
        return va + (t-ta)*(vb-va)/(tb-ta)


def witnesses(path, signals, step, requests):
    # One streaming pass per capture, retaining only the requested brackets.
    pending = sorted(requests, key=lambda x: x['timeSeconds'])
    result = {}
    previous = None
    index = 0
    for row in rows(path, signals, step):
        if previous is not None:
            while index < len(pending) and pending[index]['timeSeconds'] <= row[0]:
                request = pending[index]
                column = signals.index(request['signal']) + 1
                bracket = [[previous[0], previous[column]], [row[0], row[column]]]
                value = interpolate(bracket, request['timeSeconds'])
                result[request['id']] = {'bracket': bracket, 'interpolatedValue': str(value),
                    'intervalSeconds': row[0]-previous[0],
                    'atSavedKnot': request['timeSeconds'] in (previous[0], row[0])}
                index += 1
        previous = row
    if index != len(pending):
        raise ValueError('Uncovered peak time')
    return result


def review(root, evidence):
    assessment = json.loads((evidence / 'assessment.json').read_text())
    requests = {name: [] for name in ('25', '12.5', '6.25')}
    peaks = []
    for pair in assessment['refinementPairs']:
        for signal, entry in pair['signals'].items():
            if entry['unit'] != 'V':
                continue
            request = {'id': len(peaks), 'signal': signal, 'timeSeconds': entry['timeSeconds']}
            peaks.append({**request, 'coarse': pair['coarse'], 'fine': pair['fine'],
                          'reportedDifferenceVolts': entry['maximumAbsoluteDifference']})
            for name in (pair['coarse'], pair['fine']):
                requests[name].append(request)
    captured = {}
    hashes = {}
    for name, pending in requests.items():
        path = root / ('fixture-grid-reset-' + name) / 'network_witness.txt'
        run = json.loads((evidence / name / 'run.json').read_text())
        endpoint = json.loads((evidence / name / 'trace-endpoints.json').read_text())['network_witness.txt']
        hashes[name] = sha(path)
        if hashes[name] != endpoint['sha256']:
            raise ValueError('Changed raw capture')
        captured[name] = witnesses(path, run['observationSignals'], run['stepNs'], pending)
    for peak in peaks:
        a, b = [captured[peak[name]][peak['id']] for name in ('coarse', 'fine')]
        with localcontext() as context:
            context.prec = 64
            difference = abs(Decimal(a['interpolatedValue'])-Decimal(b['interpolatedValue']))
        peak.update(coarseWitness=a, fineWitness=b, independentDifferenceVolts=str(difference),
                    comparisonArithmeticDifferenceVolts=abs(float(difference)-peak['reportedDifferenceVolts']))
    return {'schema': 1, 'peaks': peaks, 'rawCaptureSha256': hashes,
        'assessmentSha256': sha(evidence / 'assessment.json'),
        'sources': {name: sha(HERE/name) for name in ('refinement_peak_review.py', 'host_waveform_comparison.py')},
        'qualified': False,
        'scope': 'Independent 64-digit interpolation of the same binary64 sample values at previously reported absolute-time voltage maxima. Brackets identify sampling intervals and simulation phases; arithmetic agreement does not exclude intersample curvature, trajectory error or device uncertainty. No peaks are omitted from acceptance.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.write_text(json.dumps(review(args.runs, args.evidence), indent=2)+'\n')
