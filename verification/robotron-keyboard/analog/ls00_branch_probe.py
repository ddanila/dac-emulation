#!/usr/bin/env python3
"""Check internal-node current balance on both isolated-gate DC branches."""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from failure_evidence import solver_diagnostic
from ls00_transistor_probe import sha

HERE = Path(__file__).resolve().parent


def topology(model):
    """Flatten the supported R/D/Q/X subset; reject unreviewed circuit syntax."""
    subcircuits = {}
    active = None
    for raw in model.lower().splitlines():
        fields = raw.split()
        if not fields or fields[0].startswith(('*', '+')):
            continue
        if fields[0] == '.subckt':
            if active or fields[1] in subcircuits or any('=' in f for f in fields):
                raise ValueError('Unsupported subcircuit declaration')
            active = fields[1]
            subcircuits[active] = (fields[2:], [])
        elif fields[0] == '.ends':
            active = None
        elif active:
            subcircuits[active][1].append(fields)
        elif fields[0] != '.model':
            raise ValueError('Unsupported model syntax')
    elements = []

    def expand(name, ports, path, ancestors=()):
        if name in ancestors:
            raise ValueError('Recursive subcircuit')
        pins, lines = subcircuits[name]
        if len(pins) != len(ports):
            raise ValueError('Subcircuit pin mismatch')
        mapping = dict(zip(pins, ports))
        def node(n):
            return '0' if n == '0' else mapping.get(n, path + '.' + n)
        for f in lines:
            kind = f[0][0]
            if kind == 'x':
                expand(f[-1], [node(n) for n in f[1:-1]], path + '.' + f[0], ancestors + (name,))
            elif kind in 'rdq' and len(f) == (5 if kind == 'q' else 4):
                nodes = [node(n) for n in f[1:4 if kind == 'q' else 3]]
                value = None
                if kind == 'r':
                    match = re.fullmatch(r'(\d+(?:\.\d+)?)(k|meg)?', f[-1])
                    if not match:
                        raise ValueError('Unsupported resistor value')
                    value = float(match[1]) * {None: 1, 'k': 1e3, 'meg': 1e6}[match[2]]
                    if value <= 0:
                        raise ValueError('Nonpositive resistance')
                elements.append((kind, kind + '.' + path + '.' + f[0], nodes, value))
            else:
                raise ValueError('Unsupported circuit element: ' + ' '.join(f))
    expand('ls00_transistor_candidate', ['a', 'a', 'y', 'vp', '0'], 'xgate')
    return elements


def signals_for(elements):
    nodes = sorted({n for _, _, ns, _ in elements for n in ns} - {'0'})
    signals = ['v(' + n + ')' for n in nodes]
    for kind, name, _, _ in elements:
        if kind in 'dq':
            signals += ['@' + name + '[' + terminal + ']'
                        for terminal in (['id'] if kind == 'd' else ['ic', 'ib', 'ie'])]
    return signals


def balances(elements, values):
    currents = {}
    def add(node, label, current):
        if node not in {'0', 'vp', 'a'}:  # These nodes have external ideal sources.
            currents.setdefault(node, {})[label] = current
    for kind, name, nodes, resistance in elements:
        if kind == 'r':
            voltage = lambda n: 0 if n == '0' else values['v(' + n + ')']
            current = (voltage(nodes[0]) - voltage(nodes[1])) / resistance
            terms = [current, -current]
        elif kind == 'd':
            current = values['@' + name + '[id]']
            terms = [current, -current]
        else:
            terms = [values['@' + name + '[' + t + ']'] for t in ['ic', 'ib', 'ie']]
        for i, (node, current) in enumerate(zip(nodes, terms)):
            add(node, name + ':' + str(i), current)
    result = {}
    for node, terms in currents.items():
        residual = math.fsum(terms.values())
        budget = 100e-14 + 1e-8 * math.fsum(abs(i) for i in terms.values())
        result[node] = {'signedLeavingCurrentsAmps': terms, 'residualAmps': residual,
                        'numericalBudgetAmps': budget, 'balanced': abs(residual) <= budget}
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--ngspice', default='ngspice')
    p.add_argument('--gmin', type=float, default=1e-12, help='Explicit numerical junction conductance (siemens)')
    args = p.parse_args()
    if not math.isfinite(args.gmin) or args.gmin <= 0:
        p.error('--gmin must be positive and finite')
    model = args.model.read_text()
    elements = topology(model)
    signals = signals_for(elements)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'model.cir').write_text(model)
    (out / 'spinit').write_text('* Pure SPICE initialization.\n')
    engine = Path(shutil.which(args.ngspice) or args.ngspice).resolve(strict=True)
    report = {'completed': False, 'qualified': False,
              'scope': 'Unloaded isolated gate, tied inputs, 5 V and 25 C. KCL at internal/output nodes at the comparison input only; not independent device equations, stability, physical hysteresis or DL000 accuracy.',
              'engineSha256': sha(engine), 'gminSiemens': args.gmin,
              'sources': {x.name: sha(x) for x in [Path(__file__), args.model, HERE / 'failure_evidence.py', HERE / 'ls00_transistor_probe.py']},
              'spinitSha256': sha(out / 'spinit'), 'inputComparisonVolts': 1.1158, 'branches': []}
    try:
        for name, start, stop, step in [('forward', 0, 1.116, .0001), ('reverse', 3, 1.1156, -.0001)]:
            deck = out / (name + '.cir')
            deck.write_text('\n'.join(['LS00 internal-node KCL', '.include model.cir', '.temp 25',
                f'.options reltol=1e-8 vntol=1e-10 abstol=1e-14 gmin={args.gmin:.17g}', 'Vcc vp 0 5', 'Vin a 0 0',
                'Xgate a a y vp 0 LS00_TRANSISTOR_CANDIDATE', '.control', 'set numdgt=17',
                'set wr_singlescale', 'set wr_vecnames', 'save ' + ' '.join(signals),
                f'dc Vin {start} {stop} {step}', f'wrdata {name}.txt ' + ' '.join(signals),
                'quit', '.endc', '.end']) + '\n')
            log = out / (name + '.log')
            with log.open('w') as f:
                run = subprocess.run([str(engine), '-n', '-b', deck.name], cwd=out,
                    env=dict(os.environ, SPICE_SCRIPTS=str(out)), stdout=f, stderr=subprocess.STDOUT, timeout=60)
            run.check_returncode()
            if solver_diagnostic(log.read_text()):
                raise ValueError('Solver diagnostics')
            trace = out / (name + '.txt')
            lines = trace.read_text().splitlines()
            if lines[0].split()[1:] != signals:
                raise ValueError('Unexpected current columns')
            rows = [list(map(float, line.split())) for line in lines[1:]]
            if any(len(r) != len(signals) + 1 or not all(map(math.isfinite, r)) for r in rows):
                raise ValueError('Invalid waveform')
            row = min(rows, key=lambda r: abs(r[0] - report['inputComparisonVolts']))
            if abs(row[0] - report['inputComparisonVolts']) > 1e-9:
                raise ValueError('Comparison point missing')
            values = dict(zip(signals, row[1:]))
            report['branches'].append({'direction': name, 'inputVolts': row[0],
                'outputVolts': values['v(y)'], 'nodes': balances(elements, values),
                'artifacts': {x.name: sha(x) for x in [deck, log, trace]}})
        if sha(engine) != report['engineSha256']:
            raise ValueError('Engine changed')
        report['completed'] = True
        report['nodeKclPassed'] = all(n['balanced'] for b in report['branches'] for n in b['nodes'].values())
    finally:
        (out / 'assessment.json').write_text(json.dumps(report, indent=2) + '\n')
    if not report['nodeKclPassed']:
        raise SystemExit('Internal-node current balance failed')


if __name__ == '__main__':
    main()
