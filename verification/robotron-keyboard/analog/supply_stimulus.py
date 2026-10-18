"""Explicit host-supply stimuli; voltages are test inputs, not specimen measurements."""
import json
import math


def load(path, stop_seconds):
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or set(data) != {'pointsSecondsVolts'}:
        raise ValueError('Supply stimulus requires only pointsSecondsVolts')
    points = data['pointsSecondsVolts']
    if not isinstance(points, list) or len(points) < 2:
        raise ValueError('Supply stimulus needs at least two points')
    for point in points:
        if (not isinstance(point, list) or len(point) != 2 or
                any(isinstance(v, bool) or not isinstance(v, (int, float)) or
                    not math.isfinite(v) or v < 0 for v in point)):
            raise ValueError('Supply points must be finite nonnegative [seconds, volts] pairs')
    if points[0] != [0, 0]:
        raise ValueError('Supply stimulus must start at zero time and voltage')
    if any(b[0] <= a[0] for a, b in zip(points, points[1:])):
        raise ValueError('Supply stimulus times must strictly increase')
    if points[-1][0] != stop_seconds:
        raise ValueError('Supply stimulus must end at the simulation stop time')
    return data


def source(data, rise_us):
    if data is None:
        return f'PWL(0 0 {rise_us}u 5)'
    return 'PWL(' + ' '.join(format(v, '.17g') for point in data['pointsSecondsVolts'] for v in point) + ')'
