"""DC-only bus alternatives satisfying published loaded-output inequalities.

Neither alternative is an extracted device model. Supply tracking is undefined
outside the rated supply range and must not be used for startup or brownout.
"""
import math

MODES = ('minimum-supply', 'supply-tracking')


def parameters(profile, conditions):
    lo, hi = conditions['supplyRangeVolts']
    low, high = profile['outputLow'], profile['outputHigh']
    values = (lo, hi, low['maximumVolts'], low['sinkAmps'],
              high['minimumVolts'], high['sourceMagnitudeAmps'])
    if not all(math.isfinite(v) and v > 0 for v in values) or not high['minimumVolts'] < lo <= 5 <= hi:
        raise ValueError('Invalid rated output conditions')
    return lo, hi, low['maximumVolts'] / low['sinkAmps'], high


def resistance(profile, conditions, mode, supply):
    lo, hi, _, high = parameters(profile, conditions)
    if mode not in MODES or not math.isfinite(supply) or not lo <= supply <= hi:
        raise ValueError('Candidate applies only within its declared rated supply range')
    anchor = lo if mode == 'minimum-supply' else supply
    return (anchor - high['minimumVolts']) / high['sourceMagnitudeAmps']


def branch(profile, conditions, mode, supply_node='vcc', output_node='high'):
    """SPICE current leaving the supply and entering one enabled output."""
    lo, _, _, high = parameters(profile, conditions)
    if mode not in MODES:
        raise ValueError('Unknown endpoint candidate')
    anchor = format(lo, '.17g') if mode == 'minimum-supply' else f'V({supply_node})'
    denominator = f'(({anchor}-{high["minimumVolts"]:.17g})/{high["sourceMagnitudeAmps"]:.17g})'
    return f'Bhigh {supply_node} {output_node} I=(V({supply_node})-V({output_node}))/{denominator}'
