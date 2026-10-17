#!/usr/bin/env python3
"""Scan a contact-matrix fixture through the electrical reference sensing network."""
import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

from circuit import load
from controller_interface import generate
from matrix import LATCH_LOADS, matrix_circuit, reached_rows

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SELECTIONS = [{col} for col in range(13)] + [set(range(13)), set()]


def simulate(args, components, name, contacts):
    out = args.out.resolve() / name
    out.mkdir(parents=True, exist_ok=True)
    (out / 'sweep.txt').unlink(missing_ok=True)
    lines, metadata = matrix_circuit(components, args.contact_ohms, args.beta, latch_load=args.latch_load)
    lines = ['Robotron reference electrical matrix scan; external contact fixture',
             'Vcc n_p5V 0 5', 'Vscan scan 0 0', *lines]
    for col in range(13):
        lines.append(f'Bselect{col} sink{col} 0 V=ternary_fcn((abs(V(scan)-{col})<0.1)||(abs(V(scan)-13)<0.1),5,0)')
    for index in range(104):
        lines.append(f'Vcontact{index} contact{index} 0 {5 if index in contacts else 0}')
    lines += ['.control', 'set wr_singlescale', 'set wr_vecnames', 'dc Vscan 0 14 1',
              'wrdata sweep.txt ' + ' '.join(f'v({n})' for n in metadata['outputs']),
              'quit', '.endc', '.end']
    deck = '\n'.join(lines) + '\n'
    (out / 'matrix.cir').write_text(deck)
    proc = subprocess.run([args.ngspice, '-b', 'matrix.cir'], cwd=out,
                          capture_output=True, text=True, timeout=60)
    log = proc.stdout + proc.stderr
    (out / 'ngspice.log').write_text(log)
    proc.check_returncode()
    if re.search(r'warning|error|failed|singular', log, re.I):
        raise ValueError('Solver diagnostics: ' + str(out / 'ngspice.log'))
    sweep = [[float(x) for x in line.split()] for line in (out / 'sweep.txt').read_text().splitlines()[1:]]
    if len(sweep) != len(SELECTIONS) or any(len(r) != 9 or not all(map(math.isfinite, r)) for r in sweep):
        raise ValueError('Incomplete/invalid matrix sweep')
    expected = []
    for column, row in enumerate(sweep):
        if row[0] != column:
            raise ValueError('Missing scanned column')
        high = reached_rows(contacts, SELECTIONS[column])
        expected.append(sorted(high))
        for bit, voltage in enumerate(row[1:]):
            if not (voltage > 2 if bit in high else voltage < .8):
                raise ValueError(f'{name}: column {column}, row {bit}: {voltage} V disagrees with contact connectivity')
    return {'name': name, 'closedContacts': sorted(contacts), 'expectedRowsBySelection': expected,
            'senseVoltsBySelection': [row[1:] for row in sweep],
            'deckSha256': hashlib.sha256(deck.encode()).hexdigest()}


def check_hdl(args, report):
    out = args.out.resolve()
    generated = generate()
    (out / 'controller_analog.v').write_text(generated)
    vectors = []
    for case in report['cases']:
        for col, voltages in enumerate(case['senseVoltsBySelection']):
            bits = sum((1 << bit) for bit, voltage in enumerate(voltages) if voltage > 2)
            vectors.append(f'{((0x8000 | sum(1 << c for c in SELECTIONS[col])) << 8) | bits:06x}')
    (out / 'matrix-vectors.hex').write_text('\n'.join(vectors) + '\n')
    subprocess.run([args.iverilog, '-g2012', '-s', 'matrix_interface_tb',
                    '-Pmatrix_interface_tb.COUNT=' + str(len(vectors)), '-o', str(out / 'matrix.vvp'),
                    str(HERE.parent / 'chips.v'), str(out / 'controller_analog.v'),
                    str(HERE / 'matrix_interface_tb.v')], check=True)
    proc = subprocess.run([args.vvp, 'matrix.vvp'], cwd=out, capture_output=True, text=True, timeout=60)
    (out / 'hdl.log').write_text(proc.stdout + proc.stderr)
    proc.check_returncode()
    if proc.stdout.strip() != f'MATRIX_INTERFACE_PASS {len(vectors)}' and not re.search(
            rf'^MATRIX_INTERFACE_PASS {len(vectors)}$', proc.stdout, re.M):
        raise ValueError('HDL matrix boundary did not complete')
    report['hdlInterface'] = {'passed': True,
        'generatedSha256': hashlib.sha256(generated.encode()).hexdigest(),
        'vectorsSha256': hashlib.sha256((out / 'matrix-vectors.hex').read_bytes()).hexdigest(),
        'chipsSha256': hashlib.sha256((HERE.parent / 'chips.v').read_bytes()).hexdigest(),
        'generatedSourceSha256': hashlib.sha256((HERE.parent / 'generated/controller.v').read_bytes()).hexdigest(),
        'iverilog': subprocess.run([args.iverilog, '-V'], capture_output=True, text=True, check=True).stdout.splitlines()[0],
        'scope': 'DC analog sense samples through generated latch/bus wiring; no analog/digital timing feedback yet'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--iverilog', default='iverilog')
    p.add_argument('--vvp', default='vvp')
    p.add_argument('--ngspice', default='ngspice')
    p.add_argument('--beta', type=float, default=100)
    p.add_argument('--contact-ohms', type=float, default=100)
    p.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/matrix')
    p.add_argument('--latch-load', choices=LATCH_LOADS, default='ideal')
    args = p.parse_args()
    if any(not math.isfinite(x) or x <= 0 for x in (args.beta, args.contact_ohms)):
        p.error('beta and contact-ohms must be finite and positive')
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / 'report.json'
    path.unlink(missing_ok=True)
    report = {'passed': False, 'scope': __doc__, 'cases': [], 'selectedColumns': [sorted(s) for s in SELECTIONS],
              'sources': {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                          for name in ('matrix_probe.py', 'matrix.py', 'latch_limits.json', 'circuit.py', 'controller_interface.py', 'matrix_interface_tb.v')},
              'assumptions': {'semiconductors': 'Generic SPICE models, not characterized SC308 devices',
                              'beta': args.beta, 'contactOhms': args.contact_ohms,
                              'sinkOhms': 20, 'openOhms': 1e12, 'latchLoad': args.latch_load,
                              'contacts': 'External diode-free resistive switch fixture; not a claim about specimen key construction',
                              'drivers': 'Each column alone, all columns, then no columns; unselected columns are released',
                              'scope': 'DC connectivity/voltage check; excludes timing, bounce and firmware'}}
    try:
        components, report['connectivitySha256'] = load()
        _, report['circuit'] = matrix_circuit(components, args.contact_ohms, args.beta, latch_load=args.latch_load)
        report['tool'] = subprocess.check_output([args.ngspice, '--version'], text=True).strip()
        cases = [('open', set()), *[(f'contact-{index}', {index}) for index in range(104)],
                 ('same-column', {0, 1}), ('same-row', {0, 8}),
                 ('rectangle-three-corners', {0, 8, 9}), ('all-closed', set(range(104)))]
        for name, contacts in cases:
            report['cases'].append(simulate(args, components, name, contacts))
        check_hdl(args, report)
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        path.write_text(json.dumps(report, indent=2) + '\n')
    print(path)


if __name__ == '__main__':
    main()
