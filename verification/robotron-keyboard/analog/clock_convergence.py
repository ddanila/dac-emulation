"""Stream electrical clock edges; compare phase without discarding accumulated drift."""
from trace_io import open_text
import itertools
import math


def crossings(path, maximum_step_ns, stats):
    previous = None
    last_rise = None
    periods = 0
    period_total = 0
    stats.update(samples=0, edges=0, minimumVolts=math.inf, maximumVolts=-math.inf,
                 maximumSampleGapNs=0, minimumPeriodNs=math.inf, maximumPeriodNs=0)
    with open_text(path) as stream:
        next(stream)
        for line in stream:
            row = [float(value) for value in line.split()]
            if len(row) != 5 or not all(map(math.isfinite, row)):
                raise ValueError('Invalid full-board clock waveform')
            time, voltage = row[:2]
            stats['samples'] += 1
            stats['minimumVolts'] = min(stats['minimumVolts'], voltage)
            stats['maximumVolts'] = max(stats['maximumVolts'], voltage)
            if previous is not None:
                before, prior_voltage = previous
                gap = (time - before) * 1e9
                if gap < 0 or gap > maximum_step_ns + 1:
                    raise ValueError('Clock waveform reverses or exceeds the declared timestep')
                stats['maximumSampleGapNs'] = max(stats['maximumSampleGapNs'], gap)
                if (prior_voltage < 1.4) != (voltage < 1.4):
                    direction = 'rise' if voltage >= 1.4 else 'fall'
                    estimate = before + (time - before) * (1.4 - prior_voltage) / (voltage - prior_voltage)
                    stats['edges'] += 1
                    if direction == 'rise':
                        if last_rise is not None:
                            period = (estimate - last_rise) * 1e9
                            stats['minimumPeriodNs'] = min(stats['minimumPeriodNs'], period)
                            stats['maximumPeriodNs'] = max(stats['maximumPeriodNs'], period)
                            period_total += period
                            periods += 1
                        last_rise = estimate
                    yield {'direction': direction, 'beforeSeconds': before,
                           'afterSeconds': time, 'estimatedSeconds': estimate}
            else:
                stats['firstSampleSeconds'] = time
            previous = time, voltage
    if not periods or stats['minimumVolts'] >= .8 or stats['maximumVolts'] <= 2:
        raise ValueError('Clock waveform lacks sustained rail-crossing activity')
    stats['lastSampleSeconds'] = previous[0]
    stats['meanPeriodNs'] = period_total / periods
    stats['frequencyHz'] = 1e9 / stats['meanPeriodNs']


def compare_clocks(coarse_trace, fine_trace, coarse_step_ns, fine_step_ns,
                   tolerance_ns=15, voltage_tolerance=.05):
    stats = {'coarse': {}, 'fine': {}}
    result = {'passed': True, 'thresholdVolts': 1.4, 'edgeBudgetNs': tolerance_ns,
              'sampledExtremaBudgetVolts': voltage_tolerance, 'waveforms': stats,
              'maximumEstimatedPhaseDifferenceNs': 0, 'maximumBracketDifferenceNs': 0,
              'firstDifference': None,
              'interpretation': 'Absolute edge order and phase over the saved window, with sample-bracket uncertainty; '
                                'no phase realignment. Sampled voltage extrema are not a complete waveform or device calibration.'}
    a = crossings(coarse_trace, coarse_step_ns, stats['coarse'])
    b = crossings(fine_trace, fine_step_ns, stats['fine'])
    for ordinal, (left, right) in enumerate(itertools.zip_longest(a, b)):
        failed = left is None or right is None or left['direction'] != right['direction']
        if not failed:
            phase = abs(left['estimatedSeconds'] - right['estimatedSeconds']) * 1e9
            bound = max(abs(left['beforeSeconds'] - right['afterSeconds']),
                        abs(left['afterSeconds'] - right['beforeSeconds'])) * 1e9
            result['maximumEstimatedPhaseDifferenceNs'] = max(result['maximumEstimatedPhaseDifferenceNs'], phase)
            result['maximumBracketDifferenceNs'] = max(result['maximumBracketDifferenceNs'], bound)
            failed = bound > tolerance_ns
        if failed:
            result['passed'] = False
            if result['firstDifference'] is None:
                result['firstDifference'] = {'signal': 'CPU clock voltage', 'edgeOrdinal': ordinal,
                                             'coarse': left, 'fine': right}
    result['sampledExtremaDifferencesVolts'] = {
        key: abs(stats['coarse'][key] - stats['fine'][key]) for key in ('minimumVolts', 'maximumVolts')}
    for key, difference in result['sampledExtremaDifferencesVolts'].items():
        if difference > voltage_tolerance:
            result['passed'] = False
            if result['firstDifference'] is None:
                result['firstDifference'] = {'signal': 'CPU clock voltage', 'statistic': key,
                                             'coarse': stats['coarse'][key], 'fine': stats['fine'][key]}
    for key in ('firstSampleSeconds', 'lastSampleSeconds'):
        if abs(stats['coarse'][key] - stats['fine'][key]) > 1e-9:
            raise ValueError('Clock waveform windows differ')
    return result
