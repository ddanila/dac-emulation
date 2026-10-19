"""Electrical serial, cable, supply-decoupling and external LED load model."""
import math
from itertools import combinations

from circuit import elements, node


CHOKE_REFS = ('L1.1', 'L1.2', 'L1.3', 'L1.4')


def add_filter_options(parser):
    parser.add_argument('--filter-coupling', type=float, default=0,
                        help='Experimental uniform cable-winding coupling in [0, 1); not measured')
    parser.add_argument('--filter-dot-pins', type=int, nargs=4, default=(1, 1, 1, 1),
                        metavar='PIN', help='Assumed dot terminal (1 or 2) for L1.1 through L1.4')


def filter_options(args, enabled=True):
    coupling = getattr(args, 'filter_coupling', 0)
    dots = tuple(getattr(args, 'filter_dot_pins', (1, 1, 1, 1)))
    if not math.isfinite(coupling) or not 0 <= coupling < 1:
        raise ValueError('Filter coupling must be finite and in [0, 1)')
    if len(dots) != 4 or any(type(pin) is not int or pin not in (1, 2) for pin in dots):
        raise ValueError('Filter requires four dot terminals, each 1 or 2')
    if not enabled and (coupling != 0 or dots != (1, 1, 1, 1)):
        raise ValueError('Filter hypotheses require electrical outputs')
    return {'coupling': coupling, 'dots': dots}


def choke_circuit(components, choke_uh=1, choke_ohms=1, coupling=0,
                  dots=(1, 1, 1, 1)):
    """Equal windings with uniform coupling; dot pins are explicit hypotheses.

    In board pin-1 current coordinates L = Lself*((1-k)I + k*s*s^T).
    Its eigenvalues are Lself*(1-k) and Lself*(1+3k), positive for 0<=k<1.
    Reversing node order implements dot polarity without arbitrary pair signs.
    """
    if any(not math.isfinite(x) or x <= 0 for x in (choke_uh, choke_ohms)):
        raise ValueError('Choke inductance and resistance must be positive and finite')
    if not math.isfinite(coupling) or not 0 <= coupling < 1:
        raise ValueError('Coupling must be finite and in [0, 1)')
    if len(dots) != 4 or any(type(pin) is not int or pin not in (1, 2) for pin in dots):
        raise ValueError('Supply one dot pin (1 or 2) per L1.1 through L1.4')
    lines, models = [], {}
    for ref, dot in zip(CHOKE_REFS, dots):
        c = components[ref]
        if c['type'] != 'CHOKE' or set(c['pins']) != {'1', '2'}:
            raise ValueError('Unexpected cable filter component: ' + ref)
        first, second = (node(c['pins'][p]) for p in ('1', '2'))
        middle = ref.replace('.', '_') + '_series'
        ends = (first, middle) if dot == 1 else (middle, first)
        lines += [f'{ref} {ends[0]} {ends[1]} {choke_uh}u',
                  f'R{ref} {middle} {second} {choke_ohms}']
        models[ref] = ('uncoupled nominal series RL; no characterized ferrite/coupling model'
                       if coupling == 0 else
                       'uniform coupled nominal series RL; assumed dot polarity, no characterized ferrite model')
    if coupling:
        for i, j in combinations(range(4), 2):
            lines.append(f'Kfilter{i+1}{j+1} {CHOKE_REFS[i]} {CHOKE_REFS[j]} {coupling:.17g}')
    return lines, models


def output_circuit(components, cable_pf=1000, choke_uh=1, choke_ohms=1,
                   *, coupling=0, dots=(1, 1, 1, 1)):
    refs = ['R10.1', 'R10.2', 'R11.1', 'R11.2', 'C3.1', 'C3.2',
            *[f'C5.{i}' for i in range(1, 6)]]
    lines, models = elements(components, refs)
    choke_lines, choke_models = choke_circuit(components, choke_uh, choke_ohms, coupling, dots)
    lines += choke_lines
    models.update(choke_models)
    connector = components['XT1']['pins']
    host_ground, host_supply = (node(connector[p]) for p in ('A3', 'B4'))
    channels = {'data': ('4', 'A1'), 'clock': ('2', 'B2')}
    metadata = {'models': models, 'hostGround': host_ground, 'hostSupply': host_supply,
                'serial': {}, 'leds': {},
                'filter': {'coupling': coupling, 'dotPins': dict(zip(CHOKE_REFS, dots)),
                           'qualified': False, 'selfInductanceUh': choke_uh,
                           'seriesOhms': choke_ohms,
                           'scope': 'Linear equal-winding hypothesis; ferrite losses, saturation and parasitics omitted'}}
    lines += ['.model OUTPUT_SINK_NOMINAL SW(RON=20 ROFF=1t VT=2.5 VH=0)',
              '.model LED_NOMINAL D(IS=1e-20 N=2 RS=2)']
    for label, (pin, connector_pin) in channels.items():
        board = node(components['A1']['pins'][pin])
        cable = node(connector[connector_pin])
        lines += [f'S{label} {board} 0 {label}_intent 0 OUTPUT_SINK_NOMINAL',
                  f'C{label}_load {cable} {host_ground} {cable_pf}p',
                  f'R{label}_load {cable} {host_ground} 100k']
        metadata['serial'][label] = {'board': board, 'cable': cable, 'connectorPin': connector_pin}
    for label, pin, connector_pin in [('siso', '8', 'A5'), ('caps', '6', 'A6')]:
        output = node(components['A6']['pins'][pin])
        cathode = node(components['X1']['pins'][connector_pin])
        anode = node(components['X1']['pins']['A7'])
        # LED intent is active high. These are illustrative push-pull output
        # levels/impedance, not the open-collector model used for serial lines.
        lines += [f'B{label}_target {label}_target 0 V=V(n_p5V)*(0.7-0.66*V({label}_intent)/5)',
                  f'R{label}_output {label}_target {output} 30',
                  f'D{label}_led {anode} {cathode} LED_NOMINAL']
        metadata['leds'][label] = {'output': output, 'cathode': cathode, 'anode': anode,
                                  'connectorPin': connector_pin, 'diode': f'D{label}_led'}
    metadata['shield'] = {'net': connector['A5'], 'model': 'Unconnected external shield boundary; no invented ground bond'}
    return lines, metadata
