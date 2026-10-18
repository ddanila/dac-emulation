"""Separate schematic bus drivers from voltage-derived receiver logic."""
import json
import re
from pathlib import Path

from bus_inventory import DATA_PINS, inventory
from circuit import load
from controller_interface import generate as generate_controller


def generate():
    components, _ = load()
    inventory(components, json.loads(Path(__file__).with_name('bus_limits.json').read_text()))
    source = generate_controller(explicit_cpu_drive=True, resolved_bus=True)
    source = source.replace('module controller_analog #(', 'module controller_electrical_bus #(')
    source = source.replace('input [7:0] sense,',
                            'input [7:0] bus_sense, output [23:0] bus_low, bus_high, input [7:0] sense,')
    source = source.replace(');\n', ');\nwire [7:0] cpu_driver, rom_driver, latch_driver;\n', 1)
    declarations = []
    # Keep the original chip instance and its control pins. Only its bus outputs
    # terminate at separate driver wires instead of the receiver nets.
    matches = re.findall(r'^chip_I8282 A4\([^\n]+$', source, re.M)
    if len(matches) != 1:
        raise ValueError('Unexpected generated latch instance')
    latch = matches[0]
    for bit, pin in enumerate(DATA_PINS['A4'][2]):
        old = f'.p{pin}(n_D{bit})'
        if latch.count(old) != 1:
            raise ValueError('Unexpected generated latch bus pin')
        latch = latch.replace(old, f'.p{pin}(latch_driver[{bit}])')
    source = source.replace(matches[0], latch)
    for bit in range(8):
        pullup = f'pullup(n_D{bit});'
        if source.count(pullup) != 1:
            raise ValueError('Unexpected generated bus pullup')
        source = source.replace(pullup, f'assign n_D{bit}=bus_sense[{bit}];')
        pattern = rf'^assign n_D{bit}=([^;]+);$'
        assignments = re.findall(pattern, source, re.M)
        for driver in ('cpu', 'rom'):
            candidates = [a for a in assignments if f'{driver}_data[{bit}]' in a]
            if len(candidates) != 1:
                raise ValueError('Unexpected generated bus driver assignment')
            old = f'assign n_D{bit}={candidates[0]};'
            source = source.replace(old, f'assign {driver}_driver[{bit}]={candidates[0]};')
        for index, driver in enumerate(('cpu', 'rom', 'latch')):
            signal = f'{driver}_driver[{bit}]'
            # Independent low/high enables preserve release (00) and unknown
            # drive (XX). Opposing devices remain separate for analog resolution.
            for state, output in ((0, 'low'), (1, 'high')):
                declarations.append(
                    f"assign bus_{output}[{8 * index + bit}]=({signal}===1'bz) ? 1'b0 : "
                    f"({signal}===1'b{state}) ? 1'b1 : ({signal}===1'b{1-state}) ? 1'b0 : 1'bx;")
    if len(re.findall(r'^assign n_D[0-7]=bus_sense\[[0-7]\];$', source, re.M)) != 8:
        raise ValueError('Incomplete electrical bus receiver boundary')
    return source.replace('endmodule', '\n'.join(declarations) + '\nendmodule')
