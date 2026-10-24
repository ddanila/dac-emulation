#!/usr/bin/env python3
"""Prepare nested, isolated solver-breakpoint grids around retained voltage peaks."""
import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path


def grids(assessment, common, stop_ns):
    stop_fs = int(Decimal(str(stop_ns)) * 1_000_000)
    if stop_fs <= 0:
        raise ValueError('Positive observation window required')
    centres = []
    for pair in assessment['refinementPairs']:
        for signal in pair['signals'].values():
            if signal['unit'] == 'V':
                t = int(Decimal(str(signal['timeSeconds'])) * 10**15)
                if not 0 <= t <= stop_fs:
                    raise ValueError('Peak outside observation window')
                centres.append(t)
    if not centres:
        raise ValueError('No voltage peaks')
    # A common origin and integer femtoseconds make each local grid a subset
    # of the next. Existing common sample requests remain identical at all levels.
    result = []
    for step_fs in (6_250_000, 3_125_000, 1_562_500):
        times = set(common['timesSeconds'])
        for centre in centres:
            lo = max(1, centre - 100_000_000)
            hi = min(stop_fs, centre + 100_000_000)
            first = ((lo + step_fs - 1) // step_fs) * step_fs
            times.update(t / 10**15 for t in range(first, hi + 1, step_fs))
        if len(times) > 10000:
            raise ValueError('Sampling grid exceeds harness limit')
        result.append({'timesSeconds': sorted(times), 'localStepNs': step_fs / 1_000_000,
                       'peakHalfWindowNs': 100, 'stopNs': stop_ns})
    for a, b in zip(result, result[1:]):
        assert set(a['timesSeconds']) <= set(b['timesSeconds'])
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--assessment', type=Path, required=True)
    p.add_argument('--common', type=Path, required=True)
    p.add_argument('--stop-ns', type=float, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    prepared = grids(json.loads(args.assessment.read_text()), json.loads(args.common.read_text()), args.stop_ns)
    args.out.mkdir(parents=True, exist_ok=False)
    sources = {name: hashlib.sha256(path.read_bytes()).hexdigest()
               for name, path in [('assessment', args.assessment), ('common', args.common), ('generator', Path(__file__))]}
    for i, grid in enumerate(prepared):
        grid.update(sources=sources, qualified=False,
                    scope='Requested solver breakpoints only; actual adaptive meshes need not be nested. Compare the full observation window without alignment or peak exclusions.')
        (args.out / f'{i}.json').write_text(json.dumps(grid, indent=2) + '\n')
        print(i, len(grid['timesSeconds']), 'requested times')
