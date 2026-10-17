"""Stream electrical clock edges; compare phase without discarding accumulated drift."""
from trace_io import open_text
import itertools
import math


def timestamp_uncertainty(token, value):
    """Conservative uncertainty of a rounded decimal sample time."""
    if value == 0:
        return 0.0
    mantissa, separator, exponent = token.lower().partition('e')
    decimals = len(mantissa.partition('.')[2])
    return .5 * 10.0 ** ((int(exponent) if separator else 0) - decimals) + math.ulp(value)


def crossings(path, maximum_step_ns, stats, columns=5):
    previous = None
    last_rise = None
    periods = 0
    period_total = 0
    stats.update(samples=0, edges=0, minimumVolts=math.inf, maximumVolts=-math.inf,
                 maximumSampleGapNs=0, maximumTimestampUncertaintyNs=0,
                 minimumPeriodNs=math.inf, maximumPeriodNs=0)
    with open_text(path) as stream:
        next(stream)
        for line in stream:
            tokens = line.split()
            row = [float(value) for value in tokens]
            if len(row) != columns or not all(map(math.isfinite, row)):
                raise ValueError('Invalid clock waveform')
            time, voltage = row[:2]
            uncertainty = timestamp_uncertainty(tokens[0], time)
            stats['maximumTimestampUncertaintyNs'] = max(
                stats['maximumTimestampUncertaintyNs'], uncertainty * 1e9)
            stats['samples'] += 1
            stats['minimumVolts'] = min(stats['minimumVolts'], voltage)
            stats['maximumVolts'] = max(stats['maximumVolts'], voltage)
            if previous is not None:
                before, prior_voltage, prior_uncertainty = previous
                gap = (time - before) * 1e9
                if gap < 0 or gap > maximum_step_ns + (prior_uncertainty + uncertainty) * 1e9:
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
                           'afterSeconds': time, 'estimatedSeconds': estimate,
                           'earliestSeconds': before - prior_uncertainty,
                           'latestSeconds': time + uncertainty}
            else:
                stats['firstSampleSeconds'] = time
                stats['firstSampleUncertaintySeconds'] = uncertainty
            previous = time, voltage, uncertainty
    if not periods or stats['minimumVolts'] >= .8 or stats['maximumVolts'] <= 2:
        raise ValueError('Clock waveform lacks sustained rail-crossing activity')
    stats['lastSampleSeconds'] = previous[0]
    stats['lastSampleUncertaintySeconds'] = previous[2]
    stats['meanPeriodNs'] = period_total / periods
    stats['frequencyHz'] = 1e9 / stats['meanPeriodNs']


def compare_clocks(coarse_trace, fine_trace, coarse_step_ns, fine_step_ns,
                   tolerance_ns=15, voltage_tolerance=.05, columns=5):
    stats = {'coarse': {}, 'fine': {}}
    result = {'passed': True, 'thresholdVolts': 1.4, 'edgeBudgetNs': tolerance_ns,
              'sampledExtremaBudgetVolts': voltage_tolerance, 'waveforms': stats,
              'maximumEstimatedPhaseDifferenceNs': 0, 'maximumBracketDifferenceNs': 0,
              'firstDifference': None,
              'phaseEvolution': {'signConvention': 'fine minus coarse; positive means the fine edge is later',
                                 'byDirection': {}},
              'interpretation': 'Absolute edge order and phase over the saved window, with sample-bracket and printed timestamp uncertainty; '
                                'no phase realignment. Sampled voltage extrema are not a complete waveform or device calibration.'}
    a = crossings(coarse_trace, coarse_step_ns, stats['coarse'], columns)
    b = crossings(fine_trace, fine_step_ns, stats['fine'], columns)
    for ordinal, (left, right) in enumerate(itertools.zip_longest(a, b)):
        failed = left is None or right is None or left['direction'] != right['direction']
        if not failed:
            signed_phase = (right['estimatedSeconds'] - left['estimatedSeconds']) * 1e9
            phase = abs(signed_phase)
            event = {'edgeOrdinal': ordinal, 'coarseSeconds': left['estimatedSeconds'],
                     'fineSeconds': right['estimatedSeconds'], 'signedDifferenceNs': signed_phase}
            direction = result['phaseEvolution']['byDirection'].setdefault(
                left['direction'], {'matchedEdges': 0, 'first': event, 'last': event,
                                    'minimum': event, 'maximum': event})
            direction['matchedEdges'] += 1
            direction['last'] = event
            for key, select in (('minimum', min), ('maximum', max)):
                direction[key] = select(direction[key], event, key=lambda e: e['signedDifferenceNs'])
            direction['lastMinusFirstNs'] = signed_phase - direction['first']['signedDifferenceNs']
            direction['rangeNs'] = (direction['maximum']['signedDifferenceNs']
                                    - direction['minimum']['signedDifferenceNs'])
            bound = max(abs(left['earliestSeconds'] - right['latestSeconds']),
                        abs(left['latestSeconds'] - right['earliestSeconds'])) * 1e9
            result['maximumEstimatedPhaseDifferenceNs'] = max(result['maximumEstimatedPhaseDifferenceNs'], phase)
            result['maximumBracketDifferenceNs'] = max(result['maximumBracketDifferenceNs'], bound)
            failed = bound > tolerance_ns
        if failed:
            result['passed'] = False
            if result['firstDifference'] is None:
                result['firstDifference'] = {'signal': 'Clock voltage', 'edgeOrdinal': ordinal,
                                             'coarse': left, 'fine': right}
    result['sampledExtremaDifferencesVolts'] = {
        key: abs(stats['coarse'][key] - stats['fine'][key]) for key in ('minimumVolts', 'maximumVolts')}
    for key, difference in result['sampledExtremaDifferencesVolts'].items():
        if difference > voltage_tolerance:
            result['passed'] = False
            if result['firstDifference'] is None:
                result['firstDifference'] = {'signal': 'Clock voltage', 'statistic': key,
                                             'coarse': stats['coarse'][key], 'fine': stats['fine'][key]}
    for key in ('firstSampleSeconds', 'lastSampleSeconds'):
        uncertainty_key = key.replace('Seconds', 'UncertaintySeconds')
        if abs(stats['coarse'][key] - stats['fine'][key]) > (
                stats['coarse'][uncertainty_key] + stats['fine'][uncertainty_key]):
            raise ValueError('Clock waveform windows differ')
    return result
