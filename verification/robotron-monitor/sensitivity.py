#!/usr/bin/env python3
"""One-at-a-time finite-bound sensitivity, not a joint uncertainty interval."""
import argparse
import json
import math
from pathlib import Path

import reference


def metrics(directory):
    report = json.loads((directory/'report.json').read_text())
    solver = report['solver']
    rows = reference.read_samples(directory/'samples.txt', report['probes'],
                                  report['start_time'], report['end_time'], solver['step_s'])
    result = {}
    for column, probe in enumerate(report['probes'], 1):
        values = [row[column] for row in rows]
        # Time weighted trapezoidal integrals avoid dependence on sample count.
        integral = sum((b[0]-a[0])*(a[column]+b[column])/2 for a,b in zip(rows, rows[1:]))
        square = sum((b[0]-a[0])*(a[column]**2+b[column]**2)/2 for a,b in zip(rows, rows[1:]))
        result[probe['name']] = dict(unit=probe['unit'], minimum=min(values), maximum=max(values),
                                     mean=integral/report['duration'], rms=math.sqrt(square/report['duration']))
    return result


def run(profile_path, output, names=None, stop=.0004, step=1e-7):
    profile = reference.read_profile(profile_path)
    names = list(profile['parameters']) if names is None else names
    if len(set(names)) != len(names) or not set(names) <= profile['parameters'].keys():
        raise ValueError('duplicate or unknown sensitivity parameter')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    reference.run(profile_path, output/'nominal', stop=stop, step=step)
    nominal = metrics(output/'nominal')
    cases = []
    for name in names:
        for bound in ('minimum', 'maximum'):
            directory = output/(name+'-'+bound)
            value = profile['parameters'][name][bound]
            reference.run(profile_path, directory, stop=stop, step=step, changes={name:value})
            measured = metrics(directory)
            differences = {probe: {metric: values[metric]-nominal[probe][metric]
                                    for metric in ('minimum','maximum','mean','rms')}
                           for probe, values in measured.items()}
            cases.append(dict(parameter=name, bound=bound, value=value, directory=directory.name,
                              metrics=measured, delta_from_nominal=differences))
            print(directory, flush=True)
    report = dict(format='dac-monitor-sensitivity-v1', method='one-at-a-time endpoints',
                  limitations=['Not a probabilistic confidence interval or a joint worst-case search.',
                               'A successful solve does not validate parameter bounds against hardware.'],
                  nominal=nominal, cases=cases)
    (output/'sensitivity.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, default=reference.ROOT/'profiles/k7222-11-neck.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--parameter', action='append')
    args = parser.parse_args()
    run(args.profile, args.output, args.parameter)
