"""Bracket sampled clock valid-level widths and transitions against U880 references."""
import json
import math
from itertools import zip_longest
from pathlib import Path

from clock_convergence import timestamp_uncertainty
from trace_io import open_text


def inspect(primary, supply_trace, maximum_step_ns, *, diagnostic_columns=8):
    if diagnostic_columns not in (2, 8) or not math.isfinite(maximum_step_ns) or maximum_step_ns <= 0:
        raise ValueError('Invalid clock timing observation layout or timestep')
    limits = json.loads(Path(__file__).with_name('cpu_clock_limits.json').read_text())
    timing, voltage, power = limits['clockTiming'], limits['clockInput'], limits['operatingConditions']
    bounds = {'high': (timing['highWidthMinimumNs'], timing['highWidthMaximumNs']),
              'low': (timing['lowWidthMinimumNs'], timing['lowWidthMaximumNs']),
              'rise': (0, timing['riseTimeMaximumNs']), 'fall': (0, timing['fallTimeMaximumNs']),
              'period': (timing['periodMinimumNs'], math.inf)}
    result = {'passed': False, 'qualified': False,
              'scope': 'Sample-bracket comparison using clock valid-input voltage limits; no interpolation, '
                       'between-sample waveform proof, specimen speed-grade assignment or tester-threshold calibration',
              'samples': 0, 'validSupplySamples': 0, 'abortedExcursions': 0,
              'measurements': {kind: {'observations': 0, 'passed': 0, 'failed': 0, 'indeterminate': 0,
                                     'minimumLowerNs': None, 'maximumUpperNs': None, 'firstNonPass': None}
                               for kind in bounds}}

    def record(kind, start, end):
        lower, upper = max(0, end[0] - start[1]) * 1e9, max(0, end[1] - start[0]) * 1e9
        minimum, maximum = bounds[kind]
        status = ('failed' if upper < minimum or lower > maximum else
                  'passed' if lower >= minimum and upper <= maximum else 'indeterminate')
        stats = result['measurements'][kind]
        stats['observations'] += 1
        stats[status] += 1
        stats['minimumLowerNs'] = lower if stats['minimumLowerNs'] is None else min(stats['minimumLowerNs'], lower)
        stats['maximumUpperNs'] = upper if stats['maximumUpperNs'] is None else max(stats['maximumUpperNs'], upper)
        if status != 'passed' and stats['firstNonPass'] is None:
            stats['firstNonPass'] = {'status': status, 'startBracketSeconds': start, 'endBracketSeconds': end,
                                     'durationLowerNs': lower, 'durationUpperNs': upper}

    previous = active = last_interval = last_high = None
    with open_text(primary) as clocks, open_text(supply_trace) as rails:
        next(clocks, None)
        next(rails, None)
        for a, b in zip_longest(clocks, rails):
            if a is None or b is None:
                raise ValueError('Clock and supply lengths differ')
            tokens = a.split()
            c, r = list(map(float, tokens)), list(map(float, b.split()))
            if len(c) != 5 or len(r) != diagnostic_columns or not all(map(math.isfinite, c + r)):
                raise ValueError('Invalid clock timing waveform')
            t, clk, vcc = c[0], c[1], r[1]
            uncertainty = timestamp_uncertainty(tokens[0], t)
            if t != r[0] or (previous and (t < previous['time'] or
                    t - previous['time'] > maximum_step_ns * 1e-9 + uncertainty + previous['uncertainty'])):
                raise ValueError('Unaligned clock/supply samples or excessive sample gap')
            valid = power['supplyMinimumVolts'] <= vcc <= power['supplyMaximumVolts']
            level = ('low' if clk <= voltage['lowMaximumVolts'] else
                     'high' if clk >= vcc - voltage['highMinimumSupplyDropVolts'] else None)
            result['samples'] += 1
            result['validSupplySamples'] += int(valid)
            if not valid:
                active = last_interval = last_high = None
            else:
                if active is not None and level != active['level']:
                    end = (previous['time'] - previous['uncertainty'], t + uncertainty)
                    if active['start'] is not None:
                        record(active['level'], active['start'], end)
                    last_interval = {'level': active['level'], 'end': end}
                    active = None
                if level is not None and active is None:
                    start = ((previous['time'] - previous['uncertainty'], t + uncertainty)
                             if previous and previous['valid'] else None)
                    if start is not None and last_interval is not None:
                        if level == last_interval['level']:
                            result['abortedExcursions'] += 1
                        else:
                            record('rise' if level == 'high' else 'fall', last_interval['end'], start)
                    if level == 'high':
                        if start is not None and last_high is not None:
                            record('period', last_high, start)
                        last_high = start
                    active = {'level': level, 'start': start}
            previous = {'time': t, 'uncertainty': uncertainty, 'valid': valid}
    if not result['samples']:
        raise ValueError('Empty clock timing waveform')
    result['partialIntervalPolicy'] = 'Intervals clipped by file endpoints or invalid supply are excluded; transitions with both observed brackets may still be assessed'
    result['passed'] = not result['abortedExcursions'] and all(
        s['observations'] and not s['failed'] and not s['indeterminate'] for s in result['measurements'].values())
    return result
