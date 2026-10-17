"""Electrical boundary for latch/flip-flop control pullups from canonical wiring."""
import math

from circuit import elements, node


def wiring(components, load_pf=0):
    if not math.isfinite(load_pf) or load_pf < 0:
        raise ValueError('Control fixture capacitance must be finite and nonnegative')
    expected_types = {'A2.2': 'DL003', 'A4': 'I8282', 'A6': 'DL074'}
    if any(components[ref]['type'] != kind for ref, kind in expected_types.items()):
        raise ValueError('Unexpected control-path devices')
    groups = {
        'latchEnable': ('R6.3', {('A2.2', '8'), ('A4', '9'), ('R6.3', '2')}),
        'flipFlopRelease': ('R6.6', {('A6', '1'), ('A6', '4'), ('A6', '10'), ('A6', '13'), ('R6.6', '2')}),
        'ioActive': ('R9.9', {('A2.2', '6'), ('A4', '11'), ('A6', '3'), ('A6', '11'), ('R9.9', '2')}),
    }
    supply, ground = components['A6']['pins']['14'], components['A6']['pins']['7']
    if (components['A2.2']['pins']['14'] != supply or components['A4']['pins']['20'] != supply
            or components['A2.2']['pins']['7'] != ground or components['A4']['pins']['10'] != ground):
        raise ValueError('Control devices no longer share supply and return')
    nets = {'supply': node(supply), 'ground': node(ground)}
    for name, (ref, endpoints) in groups.items():
        pins = components[ref]['pins']
        if set(pins) != {'1', '2'} or pins['1'] != supply or pins['2'] in (supply, ground, None):
            raise ValueError('Unexpected control pullup boundary: ' + ref)
        actual = {(r, p) for r, c in components.items() for p, n in c['pins'].items() if n == pins['2']}
        if actual != endpoints:
            raise ValueError('Unexpected control-net attachments: ' + ref)
        nets[name] = node(pins['2'])
    lines, models = elements(components, tuple(ref for ref, _ in groups.values()))
    for name in ('latchEnable', 'ioActive'):
        lines.append(f'Scontrol_{name} {nets[name]} {nets["ground"]} control_{name}_sink 0 CONTROL_OC_NOMINAL')
    lines.append('.model CONTROL_OC_NOMINAL SW(Ron=20 Roff=1e12 Vt=2.5 Vh=0)')
    if load_pf:
        for name in groups:
            lines.append(f'Ccontrol_{name} {nets[name]} {nets["ground"]} {load_pf:.17g}p')
    info = {'qualified': False, 'nets': nets, 'fixtureLoadPfPerNet': load_pf,
            'drivers': {'latchEnable': {'reference': 'A2.2', 'pin': '8'},
                        'ioActive': {'reference': 'A2.2', 'pin': '6'}},
            'boundary': 'Canonical resistors and nominal open-collector sinks; 20-ohm on resistance and optional per-net fixture capacitance are assumptions. '
                        'Input leakage, device capacitances, DL003 propagation and supply-current models remain unqualified.'}
    return lines, models, info
