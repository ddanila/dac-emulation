"""CPU WR output stress circuit with explicit low/high/release ownership."""
import math

from circuit import node


def wiring(components, limits, input_pf):
    if input_pf is None or not math.isfinite(input_pf) or input_pf < 0:
        raise ValueError('Explicit nonnegative 7406 input capacitance required')
    cpu, gate = components['A5'], components['A1']
    net = cpu['pins']['22']
    if cpu['type'] != 'U880' or gate['type'] != '7406' or gate['pins']['1'] != net:
        raise ValueError('Unexpected CPU WR/clock gate mapping')
    pins = sorted(f'{ref}:{pin}' for ref, part in components.items()
                  for pin, connected in part['pins'].items() if connected == net)
    if pins != ['A1:1', 'A5:22']:
        raise ValueError('Unmodeled WR connection: ' + repr(pins))
    if cpu['pins']['11'] != '/+5V' or node(cpu['pins']['29']) != '0':
        raise ValueError('Unexpected CPU supply or ground')
    profile = limits['profiles']['U880']
    low, high = profile['outputLow'], profile['outputHigh']
    rlow = low['maximumVolts'] / low['sinkAmps']
    rhigh = (5 - high['minimumVolts']) / high['sourceMagnitudeAmps']
    capacitance = profile['outputCapacitance']['maximumFarads']
    if not all(math.isfinite(v) and v > 0 for v in (rlow, rhigh, capacitance)):
        raise ValueError('Invalid WR reference endpoints or capacitance')
    signal, supply = node(net), node(cpu['pins']['11'])
    lines = [
        f'Bwr_low {signal} 0 I=V({signal})*V(wr_low)/(5*{rlow:.17g})',
        f'Bwr_high {supply} {signal} I=(V({supply})-V({signal}))*V(wr_high)/(5*{rhigh:.17g})',
        f'Cwr_cpu {signal} 0 {capacitance:.17g}',
        f'Rwr_numerical {signal} 0 1e12',
    ]
    if input_pf:
        lines.append(f'Cwr_gate {signal} 0 {input_pf:.17g}p')
    return lines, {
        'net': net, 'pins': pins, 'lowOhms': rlow, 'highOhms': rhigh,
        'cpuOutputCapacitanceFarads': capacitance, 'gateInputFixturePf': input_pf,
        'source': limits['sources'][profile['source']],
        'ownership': 'Independent 0/5 V wr_low/wr_high enables: 00 release, 10 low, 01 high; 11 contention stress only',
        'boundary': '5 V linear DC-endpoint stress fixture, not calibrated I/V or CPU control-pin timing. '
                    'Caller supplies drive/release states; no assumed reset or BUSACK behavior. '
                    'No CPU leakage, clamps, brownout or package supply model. '
                    '7406 input bias requires the separate transistor clock gate.',
    }
