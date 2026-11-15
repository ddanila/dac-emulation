"""One-time authoring utility for the explicitly non-historical test circuit.

The checked-in KiCad schematic is authoritative during experiments. This script
is NOT part of the run command and must not overwrite visitors' edited circuits.
"""
import json
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

ROOT = Path(__file__).resolve().parent


def uid(s):
    return str(uuid5(NAMESPACE_URL, "dac-monitor-fixture/"+s))


def q(s):
    return json.dumps(s)


def generate(path):
    # Ideal stimulus blocks are deliberately named; this is a solver fixture,
    # NOT a transcription of K7222 SP2/SP3 or a model of its sync oscillator.
    components = [
        ("Vpower", ["supply", "0"], "PWL(0 0 1m 41 35m 41 35.01m 0)"),
        ("Rfeed", ["supply", "bplus"], "2"),
        ("Cfeed", ["bplus", "0"], "100u"),
        ("Lp", ["bplus", "collector"], "1m"),
        ("Ls", ["0", "secondary"], ".4"),
        ("Rsecondary", ["secondary", "rectifier"], "2000"),
        ("Deht", ["rectifier", "anode"], "HV"),
        ("Ceht", ["anode", "0"], "1n"),
        ("Rbleed", ["anode", "0"], "100meg"),
        ("Ddamper", ["0", "collector"], "FAST"),
        ("Cretrace", ["collector", "0"], "10n"),
        ("Qhot", ["collector", "base", "0"], "HOT"),
        ("Rbase", ["drive", "base"], "20"),
        ("Vdrive", ["drive", "0"], "PULSE(0 5 1m .1u .1u 30u 62.5u)"),
        ("Ch", ["collector", "hyoke"], "1u"),
        ("Lh", ["hyoke", "hreturn"], "2m"),
        ("Rh", ["hreturn", "0"], "3"),
        ("Vvertical", ["vdrive", "0"], "PWL(0 -10 1m -10 19m 10 20m -10 38m 10 39m -10 40m -9)"),
        ("Rv", ["vdrive", "vyoke"], "20"),
        ("Lv", ["vyoke", "0"], "10m"),
        ("Vvideo", ["video", "0"], "PULSE(0 5 1m 20n 20n 20u 62.5u)"),
        ("Rvideo", ["video", "video_base"], "1k"),
        ("Qvideo", ["cathode", "video_base", "0"], "VIDEO"),
        ("Rpullup", ["bplus", "cathode"], "10k"),
        ("Ccathode", ["cathode", "0"], "10p"),
        ("Vgrid", ["grid", "0"], "-10"),
        ("Rfocus1", ["anode", "focus"], "88meg"),
        ("Rfocus2", ["focus", "0"], "12meg"),
        ("Vheater", ["heater", "0"], "PWL(0 0 10m 1)"),
        ("Bbeam", ["anode", "cathode"], "I=2e-7*pow(max(v(grid)-v(cathode)+30,0),1.5)*min(max(v(heater),0),1)*min(max(v(anode)/500,0),1)"),
    ]
    root_uuid = uid("root")
    text = [f'(kicad_sch (version 20250114) (generator "eeschema") (uuid "{root_uuid}") (paper "A2")',
            '(title_block (title "Experimental CRT circuit - NOT a K7222 reconstruction") (comment 1 "Uncalibrated electrical fixture. See README and sources.json."))',
            '(lib_symbols']
    for count in (2, 3):
        name = f"Element{count}"
        pins = " ".join(f'(pin passive line (at -10.16 {5.08*(i-(count-1)/2):g} 0) (length 2.54) (name "{i+1}" (effects (font (size 1 1)))) (number "{i+1}" (effects (font (size 1 1)))))' for i in range(count))
        text.append(f'(symbol "Monitor:{name}" (pin_names (offset 0) hide) (in_bom yes) (on_board yes) (property "Reference" "R" (at 0 10 0) (effects (font (size 1.27 1.27)))) (property "Value" "" (at 0 -10 0) (effects (font (size 1 1)))) (symbol "{name}_0_1" (rectangle (start -7.62 7.62) (end 7.62 -7.62) (stroke (width .254) (type default)) (fill (type none)))) (symbol "{name}_1_1" {pins}))')
    text.append(')')
    counts = {}
    for index, (purpose, nets, value) in enumerate(components):
        prefix = purpose[0]
        counts[prefix] = counts.get(prefix, 0) + 1
        ref = prefix + str(counts[prefix])
        x, y = 55+(index%5)*110, 35+(index//5)*55
        symbol_uid = uid(ref)
        text.append(f'(symbol (lib_id "Monitor:Element{len(nets)}") (at {x} {y} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid "{symbol_uid}")')
        for key, val, yy in [("Reference",ref,y-12),("Value",value,y+12),("Purpose",purpose,y+16)]:
            # Expressions are kept as properties; hidden on sheet to avoid overlap.
            hide = " hide" if len(val)>28 else ""
            text.append(f'(property {q(key)} {q(val)} (at {x} {yy} 0) (effects (font (size 1.1 1.1)){hide}))')
        text.append(f'(instances (project "fixture" (path "/{root_uuid}" (reference "{ref}") (unit 1)))))')
        for i, net in enumerate(nets):
            yy=y-5.08*(i-(len(nets)-1)/2)
            text.append(f'(wire (pts (xy {x-35:g} {yy:g}) (xy {x-10.16:g} {yy:g})) (stroke (width 0) (type default)) (uuid "{uid(ref+str(i)+"wire")}"))')
            text.append(f'(label "{net}" (at {x-35:g} {yy:g} 0) (effects (font (size 1.3 1.3)) (justify left bottom)) (uuid "{uid(ref+str(i))}"))')
    text.append('(embedded_fonts no))')
    path.write_text('\n'.join(text)+'\n')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('refusing to overwrite an existing schematic')
    generate(args.output)
