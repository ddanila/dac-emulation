"""Expose analog sense/column boundaries on the checked generated HDL wiring."""
import re
import subprocess
import sys
from pathlib import Path
from circuit import load

HERE = Path(__file__).resolve().parent


def generate(explicit_cpu_drive=False, resolved_bus=False):
    # Consume the existing schematic-generated interconnect. Only its declared
    # analog boundary is replaced; numbered chip wiring/behavior stay untouched.
    subprocess.run([sys.executable, str(HERE.parent / 'generate.py'), '--check'], check=True,
                   stdout=subprocess.DEVNULL)
    source = (HERE.parent / 'generated/controller.v').read_text()
    controller, sep, _ = source.partition('endmodule')
    if not sep or controller.count('module controller(') != 1:
        raise ValueError('Unexpected generated controller structure')
    old = 'input [103:0] contacts'
    if controller.count(old) != 1:
        raise ValueError('Unexpected contact boundary declaration')
    controller = controller.replace('module controller(', 'module controller_analog(')
    controller = controller.replace(old, 'input [7:0] sense, output [12:0] column_sink')
    if explicit_cpu_drive:
        controller = controller.replace('input [7:0] sense,', 'input cpu_drive, input [7:0] sense,')
        for bit in range(8):
            old_drive = f"assign n_D{bit}=!wr_n ? cpu_data[{bit}] : 1'bz;"
            if controller.count(old_drive) != 1:
                raise ValueError('Unexpected CPU data-drive boundary')
            controller = controller.replace(old_drive, old_drive.replace('!wr_n', 'cpu_drive'))
    if resolved_bus:
        components, _ = load()
        rom = components['A8']
        if rom['type'] != 'U556_2716':
            raise ValueError('Unsupported ROM pinout')
        def net(name):
            return 'n_' + re.sub('[^a-zA-Z0-9_]', '_', name.lstrip('/'))
        controller = controller.replace('input [7:0] sense,',
            'input mreq_n, input [7:0] rom_data, output [10:0] rom_address, input [7:0] sense,')
        controller += 'assign ' + net(components['A5']['pins']['19']) + '=mreq_n;\n'
        enable = '(!' + net(rom['pins']['18']) + ' && !' + net(rom['pins']['20']) + ')'
        for bit, pin in enumerate((8,7,6,5,4,3,2,1,23,22,19)):
            controller += f'assign rom_address[{bit}]={net(rom["pins"][str(pin)])};\n'
        for bit, pin in enumerate((9,10,11,13,14,15,16,17)):
            controller += f"assign {net(rom['pins'][str(pin)])}={enable} ? rom_data[{bit}] : 1'bz;\n"
    for row in range(8):
        pattern = rf'^assign n_SENSE{row}=([^;]*);$'
        found = re.findall(pattern, controller, re.M)
        if len(found) != 1 or 'contacts[' not in found[0]:
            raise ValueError('Unexpected generated sensing boundary')
        controller = re.sub(pattern, f'assign n_SENSE{row}=sense[{row}];', controller, flags=re.M)
    if 'contacts' in controller:
        raise ValueError('Residual digital contact logic at analog boundary')
    for col in range(13):
        if f'wire n_COL{col};' not in controller:
            raise ValueError('Missing generated column net')
        net = f'n_COL{col}'
        controller += (f"assign column_sink[{col}]={net}===1'b0 ? 1'b1 : "
                       f"({net}===1'b1 || {net}===1'bz) ? 1'b0 : 1'bx;\n")
    return controller + 'endmodule\n'
