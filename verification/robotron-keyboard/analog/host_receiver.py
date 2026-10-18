"""Reference motherboard passives, separated from unmodeled input buffers."""
import json
import math
from pathlib import Path

SOURCE = Path(__file__).with_suffix('.json')


def host_receiver(outputs, inductance_uh=1, resistance_ohms=1, input_reverse_beta=None):
    if any(not math.isfinite(x) or x <= 0 for x in (inductance_uh, resistance_ohms)):
        raise ValueError('Host winding assumptions must be positive and finite')
    if input_reverse_beta is not None and (not math.isfinite(input_reverse_beta) or input_reverse_beta <= 0):
        raise ValueError('Input reverse beta must be positive and finite')
    evidence = json.loads(SOURCE.read_text())
    supply, ground = 'host_receiver_5v', 'host_receiver_gnd'
    lines, inputs = [], {}
    paths = {label: outputs['serial'][label]['cable'] for label in ('data', 'clock')}
    paths.update(supply=outputs['hostSupply'], ground=outputs['hostGround'])
    for label, cable in paths.items():
        endpoint = {'supply': supply, 'ground': ground}.get(label, 'host_' + label + '_filtered')
        middle = 'host_' + label + '_winding'
        lines += [f'Lhost_{label} {cable} {middle} {inductance_uh}u',
                  f'Rhost_{label}_winding {middle} {endpoint} {resistance_ohms}']
        if label in evidence['channels']:
            c = evidence['channels'][label]
            receiver = 'host_' + label + '_buffer_input'
            lines += [f'Rhost_{label}_pullup {supply} {endpoint} {c["pullupOhms"]}',
                      f'Rhost_{label}_series {endpoint} {receiver} {c["seriesOhms"]}',
                      f'Chost_{label} {receiver} {ground} {c["capacitancePf"]}p']
            inputs[label] = receiver
    buffers = {}
    if input_reverse_beta is not None:
        lines += (SOURCE.parent/'ttl7404_nominal.cir').read_text().splitlines()
        for label, receiver in inputs.items():
            output = 'host_' + label + '_buffer_output'
            lines += [f'Xhost_{label} {receiver} {output} {supply} {ground} TTL7404_NOMINAL input_br={input_reverse_beta}',
                      f'Rhost_{label}_sio {output} {ground} 1g',
                      f'Chost_{label}_sio {output} {ground} 10p']
            buffers[label] = output
    return lines, {'bufferOutputs': buffers,
                   'bufferModel': {'inputReverseBeta': input_reverse_beta, 'qualified': False,
                                   'scope': 'TI standard 7404 topology, generic semiconductors; illustrative 1 Gohm/10 pF SIO loads, not measured or device-qualified'},
                   'supply': supply, 'ground': ground, 'inputs': inputs,
                   'evidence': evidence, 'qualified': False,
                   'windingAssumptions': {'selfInductanceUh': inductance_uh,
                                          'seriesOhms': resistance_ohms, 'coupling': 0}}
