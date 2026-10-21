#!/usr/bin/env python3
"""Compare only the common prefix of explicitly budget-truncated accepted captures."""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

from compare_mpfr_replays import compatible, step_and_normalized
from host_waveform_comparison import rows, compare_samples


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def budget_stop(notices, deck, limit, after, declared_stop):
    if len(notices) != 2:
        raise ValueError('Budget was not reached cleanly')
    configured = re.fullmatch(r'ACCEPTED_BUDGET configured limit=(\d+) after=(\S+)',notices[0])
    match = re.fullmatch(r'ACCEPTED_BUDGET stopped count=(\d+) time=(\S+) requested=(\S+)',notices[1])
    deck_stop = re.findall(r'^\.tran \S+ (\S+)$',deck,re.M)
    if (not configured or int(configured[1]) != limit or float(configured[2]) != after or
            not match or int(match[1]) != limit or len(deck_stop) != 1):
        raise ValueError('Budget result differs')
    effective, requested, accepted = float(match[3]), float(deck_stop[0]), float(match[2])
    # ngspice's decimal parser can differ by one ULP from Python. Record it;
    # this comparison does not relax any electrical or convergence criterion.
    if (not all(map(math.isfinite,(effective,requested,declared_stop,accepted,after))) or
            abs(effective-requested) > math.ulp(requested) or
            abs(effective-declared_stop) > math.ulp(declared_stop) or
            not after <= accepted < effective):
        raise ValueError('Budget endpoint differs')
    return {'effectiveStopSeconds':effective, 'acceptedSeconds':accepted,
            'stopParseDifferenceUlps':(effective-requested)/math.ulp(requested)}


def prefix(samples, stop):
    """Keep original knots; interpolate one final boundary, never extrapolate."""
    previous = None
    for sample in samples:
        if sample[0] > stop:
            if previous is None:
                raise ValueError('Prefix ends before first sample')
            fraction = (stop-previous[0])/(sample[0]-previous[0])
            yield (stop, *(a+fraction*(b-a) for a,b in zip(previous[1:],sample[1:])))
            return
        yield sample
        if sample[0] == stop:
            return
        previous = sample
    raise ValueError('Prefix exceeds available samples')


def load(path):
    report = json.loads((path/'report.json').read_text())
    receipt = json.loads((path/'capture-control.json').read_text())
    if receipt['reportSha256'] != sha(path/'report.json'):
        raise ValueError('Producer report changed')
    for name, digest in report['artifacts'].items():
        if sha(path/name) != digest:
            raise ValueError('Producer artifact changed: '+name)
    if (report.get('error') or report['completed'] or report['solverDiagnostic'] or
            report['precisionGuardDiagnostics'] or not receipt['operationallyTruncated'] or
            receipt['completed'] or report['exitCode'] != 0 or
            report['timeStepMode'] != 'represented' or report['integrationArithmetic'] != '256' or
            report['integration']['selection'] != 'original' or
            receipt['environment']['ROBOTRON_CAP_ASSEMBLY'] != 'exact'):
        raise ValueError('Expected clean operational truncation of exact-addition replay')
    if set(report['waveforms']) != {'trace.txt','host-trace.txt','driver-trace.txt','boundary-trace.txt'}:
        raise ValueError('Missing accepted-state observations')
    step, deck = step_and_normalized((path/'io.cir').read_text())
    return {'report':report, 'receipt':receipt, 'stepNs':step, 'normalizedDeck':deck}



def tail_summary(path, capture, signals):
    after = float(capture['receipt']['environment']['ROBOTRON_ACCEPTED_AFTER'])
    first = previous = last = None
    intervals = []
    extrema = None
    count = 0
    for sample in rows(path/'host-trace.txt', signals, capture['stepNs']):
        if sample[0] < after:
            continue
        if first is None:
            first = sample[0]
            extrema = [[v,v] for v in sample[1:]]
        if previous is not None:
            intervals.append(sample[0]-previous)
        for limits,value in zip(extrema,sample[1:]):
            limits[0],limits[1] = min(limits[0],value),max(limits[1],value)
        previous = last = sample[0]
        count += 1
    if count != int(capture['receipt']['environment']['ROBOTRON_ACCEPTED_LIMIT']):
        raise ValueError('Saved accepted-point count differs from budget')
    return {'samples':count, 'firstSeconds':first, 'lastSeconds':last,
            'advanceSeconds':last-first,
            'minimumIntervalSeconds':min(intervals) if intervals else None,
            'sampledVoltages':[{'signal':name,'minV':v[0],'maxV':v[1]} for name,v in zip(signals,extrema)]}


def review(coarse_path, fine_path):
    coarse, fine = load(coarse_path), load(fine_path)
    compatible(coarse, fine, 'timestep')
    if coarse['receipt']['environment'] != fine['receipt']['environment']:
        raise ValueError('Capture budgets or arithmetic modes differ')
    stop = min(c['report']['waveforms']['host-trace.txt']['lastSampleSeconds'] for c in (coarse,fine))
    headers = []
    for path in (coarse_path, fine_path):
        with (path/'host-trace.txt').open() as stream:
            headers.append(stream.readline().split()[1:])
    if headers[0] != headers[1]:
        raise ValueError('Host observations differ')
    comparison = compare_samples(*(prefix(rows(path/'host-trace.txt', headers[0], c['stepNs']),stop)
                                   for path,c in ((coarse_path,coarse),(fine_path,fine))))
    for name, item in zip(headers[0], comparison['signals']):
        item['signal'] = name
    return {'completed':True, 'qualified':False, 'pairCompleted':False,
            'scope':__doc__, 'absoluteTimePrefix':comparison,
            'sources':{name:sha(Path(__file__).parent/name) for name in
                       ('accepted_capture_review.py','compare_mpfr_replays.py','host_waveform_comparison.py','trace_io.py')},
            'captures':{name:{'reportSha256':sha(path/'report.json'),
                              'receiptSha256':sha(path/'capture-control.json'),
                              'waveforms':c['report']['waveforms'], 'notices':c['receipt']['notices'],
                              'budgetWindow':tail_summary(path,c,headers[0])}
                        for name,path,c in [('coarse',coarse_path,coarse),('fine',fine_path,fine)]},
            'boundary':'Common accepted-state prefix only, with one interpolated endpoint if needed. No phase alignment, extrapolation, completed refinement, intersample-peak or convergence claim. Budget termination is operational, not a solver failure.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('coarse', type=Path)
    p.add_argument('fine', type=Path)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.write_text(json.dumps(review(a.coarse,a.fine),indent=2)+'\n')
