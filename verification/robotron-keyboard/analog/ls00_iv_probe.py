#!/usr/bin/env python3
"""Capture NAND output I/V curves without treating typical curves as limits."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from failure_evidence import solver_diagnostic
from ls00_transistor_probe import sha

HERE = Path(__file__).resolve().parent


def parse_trace(text):
    lines = text.splitlines()
    if not lines or lines[0].lower().split()[1:] != ['v(y)', 'i(vforce)', 'i(vcc)']:
        raise ValueError('Unexpected I/V columns')
    rows = [list(map(float, line.split())) for line in lines[1:]]
    if len(rows) != 501 or any(len(r) != 4 or not all(map(math.isfinite, r)) for r in rows):
        raise ValueError('Incomplete or invalid I/V sweep')
    if any(abs(r[0] - i * .01) > 1e-10 or abs(r[1] - r[0]) > 1e-10 for i, r in enumerate(rows)):
        raise ValueError('Incorrect output clamp sweep')
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--ngspice', default='ngspice')
    args = p.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(args.model, out / 'model.cir')
    (out / 'spinit').write_text('* Pure SPICE initialization.\n')
    engine = Path(shutil.which(args.ngspice) or args.ngspice).resolve(strict=True)
    report = {'completed': False, 'qualified': False,
              'scope': 'Isolated NAND output clamped from 0 to 5 V in 10 mV steps. 5 V supply, 25 C, tied inputs at 0, 2 or 4.5 V. Conditions are explicit probe assumptions; not claimed identical to the typical TI graph or measured DL000 behavior.',
              'currentConvention': 'Positive output current leaves the gate into the clamp; negative current enters the gate. Supply current is positive into the gate.',
              'engineSha256': sha(engine), 'modelSha256': sha(out / 'model.cir'),
              'sources': {p.name: sha(p) for p in [Path(__file__), HERE / 'failure_evidence.py', HERE / 'ls00_transistor_probe.py']},
              'spinitSha256': sha(out / 'spinit'), 'cases': []}
    try:
        for name, vin in [('high', 0), ('low-threshold', 2), ('low-rail', 4.5)]:
            deck = out / (name + '.cir')
            deck.write_text('\n'.join(['NAND output I/V', '.include model.cir', '.temp 25',
                '.options reltol=1e-8 vntol=1e-10 abstol=1e-14', 'Vcc vp 0 5',
                f'Vin a 0 {vin}', 'Vforce y 0 0', 'Xgate a a y vp 0 LS00_TRANSISTOR_CANDIDATE',
                '.control', 'set numdgt=17', 'set wr_vecnames', 'set wr_singlescale',
                'dc Vforce 0 5 .01', f'wrdata {name}.txt v(y) i(Vforce) i(Vcc)',
                'quit', '.endc', '.end']) + '\n')
            log = out / (name + '.log')
            with log.open('w') as f:
                subprocess.run([str(engine), '-n', '-b', deck.name], cwd=out,
                    env=dict(os.environ, SPICE_SCRIPTS=str(out)), stdout=f, stderr=subprocess.STDOUT,
                    check=True, timeout=60)
            if solver_diagnostic(log.read_text()):
                raise ValueError('Solver diagnostics')
            trace = out / (name + '.txt')
            rows = parse_trace(trace.read_text())
            report['cases'].append({'name': name, 'inputVolts': vin,
                'selectedPoints': [{'outputVolts': rows[i][1], 'outputSourceAmps': rows[i][2],
                                    'supplyAmps': -rows[i][3]} for i in [0, 25, 40, 50, 100, 200, 300, 400, 500]],
                'artifacts': {p.name: sha(p) for p in [deck, log, trace]}})
        if sha(engine) != report['engineSha256']:
            raise ValueError('Engine changed')
        report['completed'] = True
    finally:
        (out / 'assessment.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
