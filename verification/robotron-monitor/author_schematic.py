"""Author labeled KiCad circuit sheets; never used during simulation.

Every component carries the original board-qualified SourceId. KiCad's globally
unique reference is only an export identifier. Pin numbers follow SPICE order
(C,B,E for a transistor; A,K for a diode), stated on the sheet.
"""
import json
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL


def write(path, components, title):
    path = Path(path)
    if path.exists():
        raise ValueError('refusing to overwrite an authored schematic')
    uid = lambda s: str(uuid5(NAMESPACE_URL, 'dac-monitor/'+path.stem+'/'+s))
    q = json.dumps
    root = uid('root')
    lines = [f'(kicad_sch (version 20250114) (generator "eeschema") (uuid "{root}") (paper "A1")',
             f'(title_block (title {q(title)}) (comment 1 "Pins: passive 1,2; diode A,K; BJT C,B,E. SourceId retains board and original designator."))',
             '(lib_symbols']
    for count in sorted({len(c['nodes']) for c in components}):
        name = f'Element{count}'
        pins = ' '.join(f'(pin passive line (at -10.16 {5.08*(i-(count-1)/2):g} 0) (length 2.54) (name "{i+1}" (effects (font (size 1 1)))) (number "{i+1}" (effects (font (size 1 1)))))' for i in range(count))
        half_height=max(7.62,2.54*(count-1)+2.54)
        lines.append(f'(symbol "Monitor:{name}" (pin_names (offset 0) hide) (in_bom yes) (on_board yes) (property "Reference" "R" (at 0 10 0) (effects (font (size 1.27 1.27)))) (property "Value" "" (at 0 -10 0) (effects (font (size 1 1)))) (symbol "{name}_0_1" (rectangle (start -7.62 {half_height:g}) (end 7.62 {-half_height:g}) (stroke (width .254) (type default)) (fill (type none)))) (symbol "{name}_1_1" {pins}))')
    lines.append(')')
    row_heights=[max(60,5.08*(max(len(c['nodes']) for c in components[i:i+5])-1)+40)
                 for i in range(0,len(components),5)]
    if sum(row_heights)>560:
        raise ValueError('schematic exceeds sheet height; split into separate sheets')
    for index, c in enumerate(components):
        ref, nets = c['reference'], c['nodes']
        x, y = 60+(index%5)*110, 10+sum(row_heights[:index//5])+row_heights[index//5]/2
        lines.append(f'(symbol (lib_id "Monitor:Element{len(nets)}") (at {x} {y} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid "{uid(ref)}")')
        half_height=max(7.62,2.54*(len(nets)-1)+2.54)
        for key, value, offset in [('Reference',ref,-half_height-5), ('Value',c['value'],half_height+5), ('SourceId',c['source_id'],half_height+9)]:
            lines.append(f'(property {q(key)} {q(value)} (at {x} {y+offset} 0) (effects (font (size 1.1 1.1))))')
        lines.append(f'(instances (project {q(path.stem)} (path "/{root}" (reference "{ref}") (unit 1)))))')
        for i, net in enumerate(nets):
            yy = y-5.08*(i-(len(nets)-1)/2)
            lines.append(f'(wire (pts (xy {x-35:g} {yy:g}) (xy {x-10.16:g} {yy:g})) (stroke (width 0) (type default)) (uuid "{uid(ref+str(i)+"wire")}"))')
            lines.append(f'(label {q(net)} (at {x-35:g} {yy:g} 0) (effects (font (size 1.3 1.3)) (justify left bottom)) (uuid "{uid(ref+str(i))}"))')
    lines.append('(embedded_fonts no))')
    path.write_text('\n'.join(lines)+'\n')
