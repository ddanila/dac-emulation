"""Electrical serial, cable, supply-decoupling and external LED load model."""
from circuit import elements, node


def output_circuit(components, cable_pf=1000, choke_uh=1, choke_ohms=1):
    refs = ['R10.1', 'R10.2', 'R11.1', 'R11.2', 'C3.1', 'C3.2',
            *[f'C5.{i}' for i in range(1, 6)]]
    lines, models = elements(components, refs)
    for ref in ('L1.1', 'L1.2', 'L1.3', 'L1.4'):
        c = components[ref]
        if c['type'] != 'CHOKE' or set(c['pins']) != {'1', '2'}:
            raise ValueError('Unexpected cable filter component: ' + ref)
        first, second = (node(c['pins'][p]) for p in ('1', '2'))
        middle = ref.replace('.', '_') + '_series'
        lines += [f'{ref} {first} {middle} {choke_uh}u',
                  f'R{ref} {middle} {second} {choke_ohms}']
        models[ref] = 'uncoupled nominal series RL; no characterized ferrite/coupling model'
    connector = components['XT1']['pins']
    host_ground, host_supply = (node(connector[p]) for p in ('A3', 'B4'))
    channels = {'data': ('4', 'A1'), 'clock': ('2', 'B2')}
    metadata = {'models': models, 'hostGround': host_ground, 'hostSupply': host_supply,
                'serial': {}, 'leds': {}}
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
