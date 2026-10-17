"""Expose analog sense/column boundaries on the checked generated HDL wiring."""
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def generate():
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
