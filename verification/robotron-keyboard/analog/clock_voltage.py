"""Supply-aware U880 clock excursions, not switching or timing qualification."""
import json
import math
from itertools import zip_longest
from pathlib import Path

from trace_io import open_text

LIMITS = Path(__file__).with_name('cpu_clock_limits.json')


def inspect(primary, diagnostic, *, diagnostic_columns=8):
    """Join retained clock and supply samples exactly; never interpolate startup."""
    if diagnostic_columns not in (2, 8):
        raise ValueError('Unsupported supply waveform layout')
    limits = json.loads(LIMITS.read_text())
    supply = limits['operatingConditions']
    clock = limits['clockInput']
    result = {
        'qualified': False,
        'scope': 'Sampled excursions within the published supply range only; '
                 'does not qualify pulse widths, between-sample behavior, temperature, or CPU behavior below that range',
        'samples': 0, 'validSupplySamples': 0, 'belowSupplySamples': 0,
        'aboveSupplySamples': 0, 'lowExcursionObserved': False,
        'highExcursionObserved': False, 'firstValidSupplySeconds': None,
        'bestLowMarginVolts': None, 'bestHighMarginVolts': None,
        'inputRangeViolations': 0, 'firstInputRangeViolation': None,
        'cycles': {'completed': 0, 'assessedWithinSupplyRange': 0, 'excludedForSupply': 0,
                   'missingLowExcursion': 0, 'missingHighExcursion': 0, 'firstFailure': None,
                   'boundary': 'Complete cycles delimited by rising 1.4 V numerical crossings; '
                               'leading/trailing partial cycles are not assessed. No pulse-width or slew claim.'},
    }
    previous, previous_voltage, cycle = None, None, None
    with open_text(primary) as clocks, open_text(diagnostic) as rails:
        next(clocks, None)
        next(rails, None)
        for a, b in zip_longest(clocks, rails):
            if a is None or b is None:
                raise ValueError('Clock and supply waveform lengths differ')
            c, r = list(map(float, a.split())), list(map(float, b.split()))
            if len(c) != 5 or len(r) != diagnostic_columns or not all(map(math.isfinite, c + r)):
                raise ValueError('Invalid clock/supply waveform')
            t, voltage, vcc = c[0], c[1], r[1]
            if t != r[0] or (previous is not None and t < previous):
                raise ValueError('Clock/supply samples are not time aligned')
            previous = t
            valid_supply = supply['supplyMinimumVolts'] <= vcc <= supply['supplyMaximumVolts']
            low = clock['lowMaximumVolts'] - voltage
            high = voltage - (vcc - clock['highMinimumSupplyDropVolts'])
            if previous_voltage is not None and previous_voltage < 1.4 <= voltage:
                if cycle is not None:
                    cycles = result['cycles']
                    cycles['completed'] += 1
                    if cycle['validSupply'] and valid_supply:
                        cycles['assessedWithinSupplyRange'] += 1
                        cycles['missingLowExcursion'] += int(not cycle['low'])
                        cycles['missingHighExcursion'] += int(not cycle['high'])
                        if not (cycle['low'] and cycle['high']) and cycles['firstFailure'] is None:
                            cycles['firstFailure'] = {'cycleOrdinal': cycles['completed'] - 1,
                                'startSeconds': cycle['start'], 'endSeconds': t,
                                'lowExcursionObserved': cycle['low'], 'highExcursionObserved': cycle['high']}
                    else:
                        cycles['excludedForSupply'] += 1
                cycle = {'start': t, 'validSupply': True, 'low': False, 'high': False}
            if cycle is not None:
                cycle['validSupply'] &= valid_supply
                cycle['low'] |= low >= 0
                cycle['high'] |= high >= 0
            previous_voltage = voltage
            result['samples'] += 1
            if vcc < supply['supplyMinimumVolts']:
                result['belowSupplySamples'] += 1
                continue
            if vcc > supply['supplyMaximumVolts']:
                result['aboveSupplySamples'] += 1
                continue
            result['validSupplySamples'] += 1
            if not clock['minimumVolts'] <= voltage <= vcc + clock['maximumSupplyOffsetVolts']:
                result['inputRangeViolations'] += 1
                if result['firstInputRangeViolation'] is None:
                    result['firstInputRangeViolation'] = {'timeSeconds': t, 'clockVolts': voltage, 'supplyVolts': vcc}
            if result['firstValidSupplySeconds'] is None:
                result['firstValidSupplySeconds'] = t
            for key, margin in (('bestLowMarginVolts', low), ('bestHighMarginVolts', high)):
                result[key] = margin if result[key] is None else max(result[key], margin)
            result['lowExcursionObserved'] |= low >= 0
            result['highExcursionObserved'] |= high >= 0
    if not result['samples']:
        raise ValueError('Empty clock/supply waveform')
    result['bothExcursionsObserved'] = result['lowExcursionObserved'] and result['highExcursionObserved']
    return result
