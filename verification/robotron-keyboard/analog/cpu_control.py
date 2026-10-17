"""Schematic CPU control pullups with reference-maximum input capacitance."""
import json
from pathlib import Path

from circuit import elements, node


def wiring(components):
    cpu = components['A5']
    if cpu['type'] != 'U880':
        raise ValueError('Unsupported CPU control-pin device')
    pins = cpu['pins']
    groups = [('R6.4', ('16', '17', '24')), ('R6.5', ('25',))]
    expected = {
        pins['16']: {('A5', '16'), ('A5', '17'), ('A5', '24'), ('R6.4', '2')},
        pins['25']: {('A5', '25'), ('R6.5', '2'), ('X1', 'A9')},
    }
    if len(expected) != 2:
        raise ValueError('CPU control nets unexpectedly joined')
    for net, endpoints in expected.items():
        actual = {(ref, pin) for ref, c in components.items() for pin, attached in c['pins'].items() if attached == net}
        if not net or actual != endpoints:
            raise ValueError('Unexpected CPU control-net attachments')
    for ref, numbers in groups:
        if components[ref]['pins'] != {'1': pins['11'], '2': pins[numbers[0]]}:
            raise ValueError('CPU pullup supply or input connection differs')
    limits = json.loads(Path(__file__).with_name('cpu_clock_limits.json').read_text())
    capacitance = limits['ordinaryInput']['capacitanceMaximumFarads']
    lines, models = elements(components, ('R6.4', 'R6.5'))
    for _, numbers in groups:
        for pin in numbers:
            lines.append(f'Ccpu_control_{pin} {node(pins[pin])} {node(pins["29"])} {capacitance:.17g}')
    return lines, models, {
        'supply': node(pins['11']), 'ground': node(pins['29']),
        'interruptNmiWait': node(pins['16']), 'busRequest': node(pins['25']),
        'inputCapacitanceFaradsPerPin': capacitance,
        'qualified': False,
        'boundary': 'Reference-maximum capacitance, not measured capacitance; leakage and input clamps omitted. '
                    'X1:A9 is externally open. CPU brownout and power-off behavior remain unmodeled.',
    }
