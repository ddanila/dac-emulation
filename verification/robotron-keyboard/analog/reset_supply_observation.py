"""Sampled reset levels by supply-stimulus segment; no undervoltage logic claims."""
import json
import math
from pathlib import Path

LIMITS = json.loads((Path(__file__).parent/'cpu_clock_limits.json').read_text())


def observe(rows, stimulus):
    if (len(rows) < 2 or any(len(r) != 8 or not all(map(math.isfinite, r)) for r in rows)
            or any(b[0] <= a[0] for a, b in zip(rows, rows[1:]))):
        raise ValueError('Invalid reset waveform')
    points = stimulus['pointsSecondsVolts']
    if rows[0][0] != 0 or rows[-1][0] < points[-1][0] - 4 * math.ulp(points[-1][0]):
        raise ValueError('Incomplete reset waveform')
    supply = LIMITS['operatingConditions']
    inputs = LIMITS['ordinaryInput']
    result = []
    for start, end in zip(points, points[1:]):
        samples = [r for r in rows if start[0] <= r[0] <= end[0]]
        if not samples:
            raise ValueError('Supply segment has no reset samples')
        valid = [r for r in samples if supply['supplyMinimumVolts'] <= r[1] <= supply['supplyMaximumVolts']]
        counts = {'low': 0, 'high': 0, 'unknown': 0, 'outsideInputRange': 0}
        for r in valid:
            reset = r[3]
            if not inputs['minimumVolts'] <= reset <= r[1] + inputs['maximumSupplyOffsetVolts']:
                counts['outsideInputRange'] += 1
            elif reset <= inputs['lowMaximumVolts']:
                counts['low'] += 1
            elif reset >= inputs['highMinimumVolts']:
                counts['high'] += 1
            else:
                counts['unknown'] += 1
        result.append({'startSeconds': start[0], 'endSeconds': end[0],
                       'programmedStartVolts': start[1], 'programmedEndVolts': end[1],
                       'sampleCount': len(samples), 'validSupplySamples': len(valid),
                       'cpuResetStatesWithinSupplyRange': counts,
                       'supplyVolts': [min(r[1] for r in samples), max(r[1] for r in samples)],
                       'sourceResetVolts': [min(r[2] for r in samples), max(r[2] for r in samples)],
                       'cpuResetVolts': [min(r[3] for r in samples), max(r[3] for r in samples)],
                       'firstSampleSeconds': samples[0][0], 'lastSampleSeconds': samples[-1][0]})
    return {'segments': result, 'maximumSampleGapSeconds': max(b[0]-a[0] for a,b in zip(rows, rows[1:])),
            'maximumBridgeDifferenceVolts': max(abs(r[2]-r[3]) for r in rows),
            'scope': 'Sampled voltage ranges only. No logic interpretation below rated supply, interpolation, restart or convergence qualification.'}
