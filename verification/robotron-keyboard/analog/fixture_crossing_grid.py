#!/usr/bin/env python3
"""Diagnostic time-grid control for the declared ideal clock/reset fixture."""
from decimal import Decimal as D

def add_crossings(deck, guard_ps=1, scenario=None):
    if guard_ps not in (1, .5, .25):
        raise ValueError('Use 1, 0.5 or 0.25 ps guard refinement')
    from io_scenario import reset_source
    reset = reset_source(scenario) if scenario else 'PWL(0 0 1000000n 0 1000001n 5)'
    if 'Vfixture_clock fixture_clock 0 PULSE(0 5 500n 1n 1n 499n 1u)' not in deck or ('Vfixture_reset fixture_reset 0 '+reset) not in deck:
        raise ValueError('Unrecognized ideal fixture')
    if '.model clock_receiver adc_bridge(in_low=1.4 in_high=1.4)' not in deck:
        raise ValueError('Unrecognized threshold')
    guard=D(str(guard_ps))/1000
    points={D(0),D('1000000.28')+guard}
    if scenario:
        for event in scenario['resets']:
            points.add(D(1000000+1000*event['cycle'])+D('.72' if event['asserted'] else '.28')+guard)
    for cycle in range(1001+scenario['cycles'] if scenario else 1161):
        points.update((D(500+1000*cycle)+D('.28')+guard,D(1000+1000*cycle)+D('.72')+guard))
    grid='Vfixture_crossing_grid fixture_crossing_grid 0 PWL(\n'+'\n'.join(f'+ {t}n 0' for t in sorted(points))+'\n+ )\n'
    # Isolated zero-voltage source introduces breakpoints only.
    return deck.replace('Vfixture_clock ',grid+'Vfixture_clock ',1)
