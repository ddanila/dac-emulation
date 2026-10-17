"""Supply-aware U880 clock excursions, not switching or timing qualification."""
import json
import math
from itertools import zip_longest
from pathlib import Path

from trace_io import open_text

LIMITS = Path(__file__).with_name('cpu_clock_limits.json')


def inspect(primary, diagnostic):
    """Join retained clock and supply samples exactly; never interpolate startup."""
    limits = json.loads(LIMITS.read_text())
    supply = limits['operatingConditions']
    clock = limits['clockInput']
    result = {
        'qualified': False,
        'scope': 'Sampled excursions within the published supply range only; '
                 'does not qualify pulse widths, every cycle, temperature, or CPU behavior below that range',
        'samples': 0, 'validSupplySamples': 0, 'belowSupplySamples': 0,
        'aboveSupplySamples': 0, 'lowExcursionObserved': False,
        'highExcursionObserved': False, 'firstValidSupplySeconds': None,
        'bestLowMarginVolts': None, 'bestHighMarginVolts': None,
    }
    previous = None
    with open_text(primary) as clocks, open_text(diagnostic) as rails:
        next(clocks, None)
        next(rails, None)
        for a, b in zip_longest(clocks, rails):
            if a is None or b is None:
                raise ValueError('Clock and supply waveform lengths differ')
            c, r = list(map(float, a.split())), list(map(float, b.split()))
            if len(c) != 5 or len(r) != 8 or not all(map(math.isfinite, c + r)):
                raise ValueError('Invalid clock/supply waveform')
            t, voltage, vcc = c[0], c[1], r[1]
            if t != r[0] or (previous is not None and t < previous):
                raise ValueError('Clock/supply samples are not time aligned')
            previous = t
            result['samples'] += 1
            if vcc < supply['supplyMinimumVolts']:
                result['belowSupplySamples'] += 1
                continue
            if vcc > supply['supplyMaximumVolts']:
                result['aboveSupplySamples'] += 1
                continue
            result['validSupplySamples'] += 1
            if result['firstValidSupplySeconds'] is None:
                result['firstValidSupplySeconds'] = t
            low = clock['lowMaximumVolts'] - voltage
            high = voltage - (vcc - clock['highMinimumSupplyDropVolts'])
            for key, margin in (('bestLowMarginVolts', low), ('bestHighMarginVolts', high)):
                result[key] = margin if result[key] is None else max(result[key], margin)
            result['lowExcursionObserved'] |= low >= 0
            result['highExcursionObserved'] |= high >= 0
    if not result['samples']:
        raise ValueError('Empty clock/supply waveform')
    result['bothExcursionsObserved'] = result['lowExcursionObserved'] and result['highExcursionObserved']
    return result
