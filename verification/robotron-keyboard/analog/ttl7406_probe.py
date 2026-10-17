#!/usr/bin/env python3
"""Characterize a published-topology 7406 proxy; no automatic fitting or full-device qualification."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

from failure_evidence import solver_diagnostic

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def simulate(out, executable, env, supply, vin, pullup, load, input_br, sweep=False):
    out.mkdir()
    shutil.copy2(HERE / 'ttl7406_nominal.cir', out / 'ttl7406_nominal.cir')
    deck = '\n'.join([
        'Published-topology SN7406 nominal DC characterization',
        '.include ttl7406_nominal.cir', '.temp 25',
        '.options reltol=1e-8 vntol=1e-10 abstol=1e-15',
        f'VCC vp 0 {supply}', f'VIN a 0 {vin}',
        f'RLOAD vp y {pullup}', f'ILOAD 0 y {load}',
        f'Xdut a y vp 0 TTL7406_NOMINAL input_br={input_br:.17g}',
        '.control', 'set wr_singlescale', 'set wr_vecnames', 'set numdgt=17',
        'dc VIN 0 5.5 .01' if sweep else 'op',
        'wrdata trace.txt v(a) v(y) i(VCC) i(VIN)',
        'quit', '.endc', '.end', ''])
    (out / 'probe.cir').write_text(deck)
    proc = subprocess.run([str(executable), '-n', '-b', 'probe.cir'], cwd=out,
                          env=env, capture_output=True, text=True, timeout=60)
    log = proc.stdout + proc.stderr
    (out / 'ngspice.log').write_text(log)
    proc.check_returncode()
    diagnostic = solver_diagnostic(log)
    if diagnostic:
        raise ValueError(diagnostic)
    rows = [list(map(float, line.split())) for line in (out / 'trace.txt').read_text().splitlines()[1:]]
    if not rows or any(len(row) != 5 or not all(map(math.isfinite, row)) for row in rows):
        raise ValueError('Invalid device waveform')
    samples = [{'inputVolts': row[1], 'outputVolts': row[2],
                'supplyAmps': -row[3], 'inputAmps': -row[4]} for row in rows]
    return samples, {name: sha(out / name) for name in
                     ('probe.cir', 'ttl7406_nominal.cir', 'ngspice.log', 'trace.txt')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', default='ngspice')
    parser.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/ttl7406')
    parser.add_argument('--require-dc-points', action='store_true', help='Fail if any selected published DC limit is missed')
    parser.add_argument('--input-reverse-beta', type=float, default=1,
                        help='Explicit input-transistor reverse gain; generic default is not calibrated')
    args = parser.parse_args()
    if not math.isfinite(args.input_reverse_beta) or args.input_reverse_beta <= 0:
        parser.error('input-reverse-beta must be positive and finite')
    located = shutil.which(args.ngspice)
    if located is None:
        parser.error('ngspice executable not found')
    executable = Path(located).resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    runtime = out / 'runtime'
    runtime.mkdir()
    (runtime / 'spinit').write_text('* Pure SPICE device probe: no external code models or initialization commands.\n')
    env = dict(os.environ, SPICE_SCRIPTS=str(runtime))
    limits = json.loads((HERE / 'ttl7406_limits.json').read_text())
    report = {'completed': False, 'qualified': False, 'scope': __doc__, 'limits': limits,
              'executable': {'path': str(executable), 'sha256': sha(executable)},
              'spinitSha256': sha(runtime / 'spinit'),
              'sources': {name: sha(HERE / name) for name in
                          ('ttl7406_probe.py', 'ttl7406_nominal.cir', 'ttl7406_limits.json', 'failure_evidence.py')},
              'modelAssumptions': 'Generic NPN IS=1e-14, BF=100, BR=1, VAF=100; generic diode IS=1e-14, N=1. No transit/storage parameters or breakdown model.',
              'inputReverseBetaOverride': args.input_reverse_beta,
              'fixtureAssumptions': 'Input-current points use a 1 Gohm output pullup. Sink points inject the specified current and use a 1 Tohm numerical pullup. Transfer sweep uses a 1 kohm pullup.',
              'cases': {}}
    try:
        report['version'] = subprocess.check_output([str(executable), '--version'], text=True).strip()
        for case in limits['cases']:
            samples, artifacts = simulate(out / case['name'], executable, env,
                                          case['supplyVolts'], case['inputVolts'],
                                          case['pullupOhms'], case['injectedOutputAmps'], args.input_reverse_beta)
            if len(samples) != 1:
                raise ValueError('Operating point did not produce one sample')
            value = samples[0][case['metric']]
            within = case.get('minimum', -math.inf) <= value <= case.get('maximum', math.inf)
            report['cases'][case['name']] = {'sample': samples[0], 'withinLimit': within, 'artifacts': artifacts}
        samples, artifacts = simulate(out / 'transfer', executable, env, 5, 0, 1000, 0, args.input_reverse_beta, sweep=True)
        if len(samples) != 551 or abs(samples[0]['inputVolts']) > 1e-12 or abs(samples[-1]['inputVolts'] - 5.5) > 1e-9:
            raise ValueError('Incomplete transfer sweep')
        low = samples[80]
        high = samples[200]
        if low['outputVolts'] < 2 or high['outputVolts'] > .8:
            raise ValueError('Nominal fixture does not invert TTL input levels')
        report['transfer'] = {'lowInput': low, 'highInput': high, 'artifacts': artifacts}
        if sha(executable) != report['executable']['sha256']:
            raise ValueError('Simulator changed during device probe')
        report['dcPointsWithinPublishedLimits'] = all(case['withinLimit'] for case in report['cases'].values())
        report['completed'] = True
        if args.require_dc_points and not report['dcPointsWithinPublishedLimits']:
            raise ValueError('Nominal model misses selected DC limits')
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(out / 'report.json')


if __name__ == '__main__':
    main()
