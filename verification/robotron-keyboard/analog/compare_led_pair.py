#!/usr/bin/env python3
"""Compare firmware LED intent transition timing across electrical timesteps."""
import argparse
import itertools
import json
import math
from pathlib import Path

from clock_convergence import timestamp_uncertainty
from compare_firmware_io import load_run, compare, normalized_deck, sha
from trace_io import open_text

HERE = Path(__file__).resolve().parent


def edges(path, step_ns, start_seconds=.001):
    previous = None
    with open_text(path) as stream:
        next(stream)
        for line in stream:
            tokens = line.split()
            row = [float(value) for value in tokens]
            if len(row) != 5 or not all(map(math.isfinite, row)):
                raise ValueError('Invalid LED waveform')
            stamp, voltages = row[0], row[1:3]
            uncertainty = timestamp_uncertainty(tokens[0], stamp)
            if previous is not None:
                before, prior_voltages, prior_uncertainty = previous
                if stamp < before or stamp - before > step_ns * 1e-9 + prior_uncertainty + uncertainty:
                    raise ValueError('LED waveform reverses or exceeds the declared timestep')
                for channel, (prior, voltage) in enumerate(zip(prior_voltages, voltages)):
                    if before >= start_seconds and (prior < 2.5) != (voltage < 2.5):
                        yield {'channel': channel, 'direction': 'rise' if voltage >= 2.5 else 'fall',
                               'earliestSeconds': before - prior_uncertainty,
                               'latestSeconds': stamp + uncertainty}
            previous = stamp, voltages, uncertainty


def compare_edges(left, right, tolerance_ns):
    result = {'passed': True, 'matchedEdges': 0, 'maximumBracketDifferenceNs': 0,
              'firstDifference': None}
    for ordinal, (a, b) in enumerate(itertools.zip_longest(left, right)):
        bound = None
        failed = a is None or b is None or a['direction'] != b['direction']
        if not failed:
            bound = max(abs(a['earliestSeconds'] - b['latestSeconds']),
                        abs(a['latestSeconds'] - b['earliestSeconds'])) * 1e9
            result['matchedEdges'] += 1
            result['maximumBracketDifferenceNs'] = max(result['maximumBracketDifferenceNs'], bound)
            failed = bound > tolerance_ns
        if failed:
            result['passed'] = False
            if result['firstDifference'] is None:
                result['firstDifference'] = {'ordinal': ordinal, 'coarse': a, 'fine': b,
                                             'bracketDifferenceNs': bound}
    if not result['matchedEdges']:
        result['passed'] = False
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('coarse', type=Path)
    p.add_argument('fine', type=Path)
    p.add_argument('--tolerance-ns', type=float, default=15)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    if not math.isfinite(args.tolerance_ns) or args.tolerance_ns <= 0:
        p.error('tolerance-ns must be positive and finite')
    result = {'passed': False, 'scope': __doc__, 'edgeBudgetNs': args.tolerance_ns,
              'intentThresholdVolts': 2.5, 'checkStartSeconds': .001,
              'interpretation': 'DAC intent midpoint crossings with sample and printed timestamp uncertainty; '
                                'no phase realignment, historical propagation or brightness qualification.',
              'sources': {n: sha(HERE / n) for n in (
                  'compare_led_pair.py', 'compare_firmware_io.py', 'transient_analysis.py', 'clock_convergence.py',
                  'led_observation.py', 'serial_observation.py', 'failure_evidence.py', 'trace_io.py')}}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    try:
        if normalized_deck(args.coarse) != normalized_deck(args.fine):
            raise ValueError('Electrical decks differ beyond timestep')
        reports, transports = zip(*(load_run(d) for d in (args.coarse, args.fine)))
        if not all(r['assumptions'].get('ledTrace') for r in reports):
            raise ValueError('Both runs must retain electrical LED traces')
        result['inputs'] = {n: {'path': str(d.resolve()), 'reportSha256': sha(d / 'report.json')}
                            for n, d in (('coarse', args.coarse), ('fine', args.fine))}
        # Reuse the provenance and paired-timestep checks before interpreting LED differences.
        if not compare(*reports, *transports, args.tolerance_ns)['withinTolerance']:
            raise ValueError('Serial timing does not converge')
        timelines = []
        for d, r in zip((args.coarse, args.fine), reports):
            channels = [[], []]
            for event in edges(d / 'led-trace.txt', r['assumptions']['stepNs']):
                channels[event['channel']].append(event)
            timelines.append(channels)
        result['channels'] = {
            name: compare_edges(timelines[0][channel], timelines[1][channel], args.tolerance_ns)
            for channel, name in enumerate(('siso', 'caps'))}
        for n, d in (('coarse', args.coarse), ('fine', args.fine)):
            if sha(d / 'report.json') != result['inputs'][n]['reportSha256']:
                raise ValueError('Input report changed during comparison')
        result['passed'] = all(c['passed'] for c in result['channels'].values())
        if not result['passed']:
            raise ValueError('LED transition timing does not converge')
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(args.out)


if __name__ == '__main__':
    main()
