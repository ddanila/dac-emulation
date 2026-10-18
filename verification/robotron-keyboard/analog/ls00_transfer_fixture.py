#!/usr/bin/env python3
"""Diagnose gate transfer branches under explicit interpretations of a 500-ohm load."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from failure_evidence import capture, solver_diagnostic
from ls00_transistor_probe import sha

HERE = Path(__file__).resolve().parent


def read_sweep(text, step, reverse):
    lines = text.splitlines()
    if not lines or lines[0].lower().split()[1:] != ['v(y)', 'i(vin)']:
        raise ValueError('Unexpected transfer columns')
    rows = [list(map(float, line.split())) for line in lines[1:]]
    count = round(1.6 / step) + 1
    if len(rows) != count or any(len(r) != 3 or not all(map(math.isfinite, r)) for r in rows):
        raise ValueError('Incomplete or nonfinite transfer sweep')
    if reverse:
        rows.reverse()
    if any(abs(row[0] - i * step) > 1e-9 for i, row in enumerate(rows)):
        raise ValueError('Reordered or incorrect transfer grid')
    return rows


def compare(forward, reverse):
    if len(forward) != len(reverse) or any(abs(a[0] - b[0]) > 1e-9 for a, b in zip(forward, reverse)):
        raise ValueError('Different sweep grids')
    a, b = max(zip(forward, reverse), key=lambda pair: abs(pair[0][1] - pair[1][1]))
    return {'maximumOutputDifferenceVolts': abs(a[1] - b[1]),
            'inputVolts': a[0], 'forwardOutputVolts': a[1], 'reverseOutputVolts': b[1]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--ngspice', default='ngspice')
    args = p.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    engine = Path(shutil.which(args.ngspice) or args.ngspice).resolve(strict=True)
    shutil.copyfile(args.model, out / 'model.cir')
    (out / 'spinit').write_text('* Pure SPICE transfer diagnostic.\n')
    report = {'completed': False, 'qualified': False, 'modelSha256': sha(out / 'model.cir'),
              'engineSha256': sha(engine), 'spinitSha256': sha(out / 'spinit'),
              'sources': {f.name: sha(f) for f in [Path(__file__), HERE / 'failure_evidence.py', HERE / 'ls00_transistor_probe.py']},
              'scope': 'Isolated candidate gate, 5 V, 25 C, 500 ohms. Load to ground or supply and tied or supply-held complementary input are explicit alternatives, not a recovered manufacturer fixture. Forward/reverse and step refinement are diagnostics, not physical hysteresis or device qualification.',
              'cases': [], 'comparisons': [], 'refinementComparisons': []}
    try:
        for load_label, load_node in [('ground', '0'), ('supply', 'vp')]:
            for input_label, input_node in [('tied', 'a'), ('high', 'vp')]:
                refinements = {}
                for step in [.001, .0005]:
                    traces = {}
                    for reverse in [False, True]:
                        name = f'{load_label}-{input_label}-{step:g}-' + ('reverse' if reverse else 'forward')
                        start, stop, delta = (1.6, 0, -step) if reverse else (0, 1.6, step)
                        deck = out / (name + '.cir'); log = out / (name + '.log'); trace = out / (name + '.txt')
                        deck.write_text('\n'.join(['500-ohm gate transfer diagnostic', '.include model.cir', '.temp 25',
                            '.options reltol=1e-8 vntol=1e-10 abstol=1e-14 gmin=1e-15', 'Vcc vp 0 5', 'Vin a 0 0',
                            f'Xgate a {input_node} y vp 0 LS00_TRANSISTOR_CANDIDATE', f'Rload y {load_node} 500',
                            '.control', 'set numdgt=17', 'set wr_singlescale', 'set wr_vecnames',
                            f'dc Vin {start} {stop} {delta}', f'wrdata {trace.name} v(y) i(Vin)', 'quit', '.endc', '.end']) + '\n')
                        with log.open('w') as f:
                            subprocess.run([str(engine), '-n', '-b', deck.name], cwd=out,
                                env=dict(os.environ, SPICE_SCRIPTS=str(out)), stdout=f,
                                stderr=subprocess.STDOUT, check=True, timeout=60)
                        if solver_diagnostic(log.read_text()):
                            raise ValueError('Solver diagnostic: ' + name)
                        rows = read_sweep(trace.read_text(), step, reverse); traces[reverse] = rows
                        report['cases'].append({'name': name, 'loadConnection': load_label,
                            'complementaryInput': input_label, 'stepVolts': step, 'reverse': reverse,
                            'maximumAdjacentOutputChangeVolts': max(abs(a[1] - b[1]) for a, b in zip(rows, rows[1:])),
                            'outputAtSweepEndpointsVolts': [rows[0][1], rows[-1][1]],
                            'artifacts': {f.name: sha(f) for f in [deck, log, trace]}})
                    refinements[step] = traces
                    report['comparisons'].append({'loadConnection': load_label, 'complementaryInput': input_label,
                                                 'stepVolts': step, **compare(traces[False], traces[True])})
                for reverse in [False, True]:
                    delta = compare(refinements[.001][reverse], refinements[.0005][reverse][::2])
                    report['refinementComparisons'].append({'loadConnection': load_label,
                        'complementaryInput': input_label, 'reverse': reverse,
                        'maximumOutputDifferenceVolts': delta['maximumOutputDifferenceVolts'],
                        'inputVolts': delta['inputVolts'], 'coarseOutputVolts': delta['forwardOutputVolts'],
                        'fineOutputVolts': delta['reverseOutputVolts']})
        if sha(engine) != report['engineSha256']:
            raise ValueError('Runtime changed')
        report['completed'] = True
    except Exception as error:
        report['error'] = str(error)
        report['failureEvidence'] = capture(out, [f.name for f in out.iterdir() if f.suffix in {'.cir', '.log', '.txt'}])
        raise
    finally:
        (out / 'assessment.json').write_text(json.dumps(report, indent=2) + '\n')
    print(out / 'assessment.json')


if __name__ == '__main__':
    main()
