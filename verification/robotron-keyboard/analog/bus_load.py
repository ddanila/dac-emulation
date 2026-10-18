"""Schematic-derived data-pin capacitances; unknown values require explicit fixtures."""
import math

from bus_inventory import inventory
from circuit import node


def wiring(components, limits, unknown_pf):
    """unknown_pf specifies per-pin fixture capacitance for undocumented devices."""
    buses = inventory(components, limits)['buses']
    missing = {pin['profile'] for bus in buses for pin in bus['endpoints']
               if pin['capacitanceReference'] is None}
    if set(unknown_pf) != missing:
        raise ValueError(f'Explicit unknown-capacitance fixtures required for {sorted(missing)}')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or
           not math.isfinite(v) or v < 0 for v in unknown_pf.values()):
        raise ValueError('Fixture capacitances must be finite nonnegative pF')
    ground_pins = {'A5': '29', 'A8': '12', 'A4': '10', 'A1': '7'}
    lines, loads = [], []
    for bus in buses:
        for pin in bus['endpoints']:
            ref, number = pin['reference'], pin['pin']
            ground = components[ref]['pins'][ground_pins[ref]]
            if ground != '/GND':
                raise ValueError(f'Unexpected data-pin reference ground: {ref}')
            reference = pin['capacitanceReference']
            if reference is None:
                capacitance = unknown_pf[pin['profile']] * 1e-12
                basis = 'explicit fixture assumption'
            else:
                capacitance = reference['maximumFarads']
                basis = 'published reference maximum'
            if not math.isfinite(capacitance) or capacitance < 0:
                raise ValueError('Invalid reference capacitance')
            if capacitance:
                lines.append(f'Cbus_{ref}_{number} {node(bus["net"])} {node(ground)} {capacitance:.17g}')
            loads.append(dict(pin, net=bus['net'], ground=ground,
                              capacitanceFarads=capacitance, basis=basis))
    return lines, {'qualified': False, 'loads': loads,
                   'boundary': 'Pin capacitance only. No driver I/V, leakage, clamps, trace capacitance, '
                               'contention current or released voltage qualification. Zero fixture loads '
                               'are explicit omissions, not measured zero capacitance.'}
