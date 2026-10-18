#!/usr/bin/env python3
"""Test finite perturbation recovery of isolated NAND model branches."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from failure_evidence import solver_diagnostic
from ls00_transistor_probe import sha
from ls00_branch_probe import topology, signals_for

HERE = Path(__file__).resolve().parent
BUDGET = 1e-6  # Numerical comparison only, not a device specification.


def summarize(rows, signals):
    if not rows or rows[-1][0] < math.nextafter(2e-6, 0):
        raise ValueError('Incomplete transient')
    if any(len(r) != len(signals) + 1 or not all(map(math.isfinite, r)) for r in rows):
        raise ValueError('Invalid transient samples')
    if any(b[0] <= a[0] for a, b in zip(rows, rows[1:])):
        raise ValueError('Nonmonotonic transient')
    windows = [[r for r in rows if lo <= r[0] <= hi]
               for lo, hi in [(8e-7, 9e-7), (1.8e-6, 2e-6)]]
    if any(len(window) < 2 for window in windows):
        raise ValueError('Missing comparison window')
    result = {}
    for i, signal in enumerate(signals, 1):
        means = [math.fsum(r[i] for r in w) / len(w) for w in windows]
        spans = [max(r[i] for r in w) - min(r[i] for r in w) for w in windows]
        result[signal] = {'beforeVolts': means[0], 'afterVolts': means[1],
                          'recoveryDifferenceVolts': abs(means[1] - means[0]),
                          'maximumWindowSpanVolts': max(spans)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--ngspice', default='ngspice')
    args = parser.parse_args()
    model = args.model.read_text()
    signals = [s for s in signals_for(topology(model)) if s.startswith('v(')]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'model.cir').write_text(model)
    (out / 'spinit').write_text('* Pure SPICE initialization.\n')
    engine = Path(shutil.which(args.ngspice) or args.ngspice).resolve(strict=True)
    report = {'completed': False, 'qualified': False,
              'scope': 'Isolated unloaded NAND with tied inputs, ideal 5 V supply, 25 C and gmin=1e-15 S. Slow ramps from either logic rail followed by finite input disturbances. Recovery in these cases is not a general stability proof or physical hysteresis measurement.',
              'comparisonBudgetVolts': BUDGET, 'engineSha256': sha(engine),
              'sources': {p.name: sha(p) for p in [Path(__file__), args.model,
                  HERE / 'ls00_branch_probe.py', HERE / 'failure_evidence.py', HERE / 'ls00_transistor_probe.py']},
              'spinitSha256': sha(out / 'spinit'), 'cases': [], 'pairs': []}
    try:
        for direction, start in [('forward', 0), ('reverse', 3)]:
            for perturb in [-.001, 0, .001]:
                pair = []
                for step in [.2e-9, .1e-9]:
                    name = f'{direction}-{perturb:+.3f}-{step:.0e}'
                    deck = out / (name + '.cir')
                    deck.write_text('\n'.join(['LS00 branch perturbation', '.include model.cir',
                        '.temp 25', '.options reltol=1e-8 vntol=1e-10 abstol=1e-14 gmin=1e-15',
                        'Vcc vp 0 5',
                        f'Vin a 0 PWL(0 {start} 500n 1.1158 1u 1.1158 1001n {1.1158 + perturb:.17g} 1100n {1.1158 + perturb:.17g} 1101n 1.1158 2u 1.1158)',
                        'Xgate a a y vp 0 LS00_TRANSISTOR_CANDIDATE', '.control',
                        'set numdgt=17', 'set wr_vecnames', 'set wr_singlescale',
                        'save ' + ' '.join(signals), f'tran {step:.17g} 2u 0 {step:.17g}',
                        f'wrdata {name}.txt ' + ' '.join(signals), 'quit', '.endc', '.end']) + '\n')
                    log = out / (name + '.log')
                    with log.open('w') as f:
                        subprocess.run([str(engine), '-n', '-b', deck.name], cwd=out,
                            env=dict(os.environ, SPICE_SCRIPTS=str(out)), stdout=f,
                            stderr=subprocess.STDOUT, check=True, timeout=60)
                    if solver_diagnostic(log.read_text()):
                        raise ValueError('Solver diagnostics')
                    trace = out / (name + '.txt')
                    lines = trace.read_text().splitlines()
                    if lines[0].split()[1:] != signals:
                        raise ValueError('Unexpected waveform columns')
                    rows = [list(map(float, line.split())) for line in lines[1:]]
                    values = summarize(rows, signals)
                    input_index = signals.index('v(a)') + 1
                    pulse = [r[input_index] for r in rows if 1.02e-6 <= r[0] <= 1.08e-6]
                    if not pulse or max(abs(v - (1.1158 + perturb)) for v in pulse) > BUDGET:
                        raise ValueError('Input disturbance missing or incorrect')
                    if abs(values['v(a)']['beforeVolts'] - 1.1158) > BUDGET:
                        raise ValueError('Incorrect input plateau')
                    result = {'name': name, 'direction': direction, 'inputPerturbationVolts': perturb,
                              'stepSeconds': step, 'nodes': values,
                              'artifacts': {p.name: sha(p) for p in [deck, log, trace]}}
                    report['cases'].append(result)
                    pair.append(result)
                difference = max(abs(pair[0]['nodes'][s][which] - pair[1]['nodes'][s][which])
                                 for s in signals for which in ['beforeVolts', 'afterVolts'])
                report['pairs'].append({'cases': [c['name'] for c in pair],
                                        'maximumPlateauDifferenceVolts': difference})
        if sha(engine) != report['engineSha256']:
            raise ValueError('Engine changed')
        report['completed'] = True
        report['finiteRecoveryPassed'] = all(v['recoveryDifferenceVolts'] <= BUDGET and
            v['maximumWindowSpanVolts'] <= BUDGET for c in report['cases'] for v in c['nodes'].values())
        report['plateauRefinementPassed'] = all(p['maximumPlateauDifferenceVolts'] <= BUDGET for p in report['pairs'])
    finally:
        (out / 'assessment.json').write_text(json.dumps(report, indent=2) + '\n')
    if not report['finiteRecoveryPassed'] or not report['plateauRefinementPassed']:
        raise SystemExit('Branch recovery or plateau refinement failed')


if __name__ == '__main__':
    main()
