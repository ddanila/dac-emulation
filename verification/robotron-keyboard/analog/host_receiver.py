"""Reference motherboard passives and explicitly experimental buffer/load models."""
import json
import math
from pathlib import Path

SOURCE = Path(__file__).with_suffix('.json')


def host_receiver(outputs, inductance_uh=1, resistance_ohms=1, input_reverse_beta=None, sio_load=None):
    if any(not math.isfinite(x) or x <= 0 for x in (inductance_uh, resistance_ohms)):
        raise ValueError('Host winding assumptions must be positive and finite')
    if input_reverse_beta is not None and (not math.isfinite(input_reverse_beta) or input_reverse_beta <= 0):
        raise ValueError('Input reverse beta must be positive and finite')
    if sio_load is not None:
        if input_reverse_beta is None:
            raise ValueError('SIO loads require an active host buffer')
        if set(sio_load) != {'dataPf', 'clockPf', 'leakageUa'}:
            raise ValueError('SIO load must declare both capacitances and leakage')
        if (any(not math.isfinite(v) for v in sio_load.values())
                or sio_load['dataPf'] <= 0 or sio_load['clockPf'] <= 0):
            raise ValueError('SIO capacitances must be positive and load values finite')
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
            if sio_load is not None:
                # Keep a DC path but replace the illustrative shunt load explicitly.
                lines[-1] = f'Chost_{label}_sio {output} {ground} {sio_load[label + "Pf"]}p'
                lines.append(f'Ihost_{label}_sio {output} {ground} {sio_load["leakageUa"]}u')
            buffers[label] = output
    return lines, {'bufferOutputs': buffers,
                   'bufferModel': {'inputReverseBeta': input_reverse_beta, 'qualified': False,
                                   'scope': 'TI standard 7404 topology, generic semiconductors; explicit assumed SIO loads, not measured or device-qualified',
                                   'sioLoad': dict(sio_load) if sio_load is not None else {'dataPf': 10, 'clockPf': 10, 'leakageUa': 0},
                                   'loadBoundary': '1 Gohm shunt plus specified capacitance and constant leakage; positive leakage flows from input to ground. Constant leakage is a stress assumption, not device I/V behavior.'},
                   'supply': supply, 'ground': ground, 'inputs': inputs,
                   'evidence': evidence, 'qualified': False,
                   'windingAssumptions': {'selfInductanceUh': inductance_uh,
                                          'seriesOhms': resistance_ohms, 'coupling': 0}}
