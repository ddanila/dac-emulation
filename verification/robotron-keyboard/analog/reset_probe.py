#!/usr/bin/env python3
"""Run the reference reset topology with explicit exploratory device/load models."""
import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

from circuit import elements, load, node, nominal_models

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RESET_REFS = ('C1', 'C2', 'C4', 'R3', 'R4.1', 'R4.2', 'R5', 'R6.1',
              'R7', 'R8', 'V1.1', 'V1.2', 'V2', 'V3.1', 'V3.2', 'V4.9')


def simulate(args, components, step_us, isolated):
    out = args.out.resolve() / f'{"isolated" if isolated else "closed"}-{step_us}us'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'trace.txt').unlink(missing_ok=True)
    lines, models = elements(components, RESET_REFS)
    bridge = components['BR2']
    if bridge['type'] != 'BRIDGE' or set(bridge['pins']) != {'1', '2'}:
        raise ValueError('Unexpected BR2 topology')
    source, cpu = [node(bridge['pins'][p]) for p in ('1', '2')]
    if cpu != node(components['A5']['pins']['26']):
        raise ValueError('BR2 no longer feeds the CPU reset pin')
    rise = args.rise_us * 1e-6
    lines = ['Robotron reference reset; nominal exploratory semiconductor models',
             f'Vcc n_p5V 0 PWL(0 0 {rise} 5 .3 5 {.3+rise} 0 1.3 0 {1.3+rise} 5 1.6 5)',
             *nominal_models(args.beta), *lines,
             f'RBR2 {source} {cpu} {"1t" if isolated else ".001"}',
             f'Rcpu {cpu} 0 1g', f'Ccpu {cpu} 0 10p']
    if isolated:
        lines += [f'Rfixture {cpu} 0 100']
    signals = ['n_p5V', source, cpu, 'n_RESET_RC', 'n_RESET_BIAS', 'n_RESET_BASE']
    lines += ['.control', 'set wr_singlescale', 'set wr_vecnames',
              f'tran {step_us}u 1.6', 'wrdata trace.txt ' + ' '.join(f'v({n})' for n in signals),
              'quit', '.endc', '.end']
    deck = '\n'.join(lines) + '\n'
    (out / 'reset.cir').write_text(deck)
    proc = subprocess.run([args.ngspice, '-b', 'reset.cir'], cwd=out,
                          capture_output=True, text=True, timeout=60)
    log = proc.stdout + proc.stderr
    (out / 'ngspice.log').write_text(log)
    proc.check_returncode()
    if re.search(r'warning|error|failed|singular', log, re.I):
        raise ValueError('Solver diagnostics: ' + str(out / 'ngspice.log'))
    rows = [[float(x) for x in line.split()] for line in (out / 'trace.txt').read_text().splitlines()[1:]]
    if not rows or any(len(r) != len(signals) + 1 or not all(map(math.isfinite, r)) for r in rows):
        raise ValueError('Incomplete/invalid reset waveform')
    if rows[0][0] > rise or rows[-1][0] < 1.6:
        raise ValueError('Reset transient endpoints missing')
    boots = []
    for start in (0, 1.3):
        low_window = [r for r in rows if start + rise + .001 <= r[0] <= start + .05]
        high_window = [r for r in rows if start + .25 <= r[0] <= start + .29]
        if not low_window or not high_window:
            raise ValueError('Reset observation window missing')
        if max(r[2] for r in low_window) >= .8 or min(r[2] for r in high_window) <= 2:
            raise ValueError('Reference reset did not assert/release in the exploratory observation windows')
        releases = [(a, b) for a, b in zip(rows, rows[1:])
                    if start + .05 < a[0] < start + .25 and a[2] < 2 <= b[2]]
        if len(releases) != 1:
            raise ValueError('Expected one reset release per power cycle')
        a, b = releases[0]
        release = a[0] + (2-a[2]) * (b[0]-a[0]) / (b[2]-a[2]) - start
        boots.append({'releaseSecondsAt2V': release,
                      'maximumAssertedVolts': max(r[2] for r in low_window),
                      'minimumReleasedVolts': min(r[2] for r in high_window)})
    if isolated:
        if max(abs(r[3]) for r in rows) >= .01:
            raise ValueError('Opened BR2 failed to isolate the grounded CPU reset fixture')
    elif max(abs(r[2] - r[3]) for r in rows) > .01:
        raise ValueError('Closed BR2 failed to carry reset to CPU pin')
    return {'stepUs': step_us, 'br2Closed': not isolated, 'boots': boots,
            'models': {**models, 'BR2': '1 milliohm closed / 1 teraohm open'},
            'signals': signals, 'deckSha256': hashlib.sha256(deck.encode()).hexdigest()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ngspice', default='ngspice')
    p.add_argument('--beta', type=float, default=100)
    p.add_argument('--rise-us', type=float, default=1)
    p.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/reset')
    args = p.parse_args()
    if not math.isfinite(args.beta) or args.beta <= 0 or not 0 < args.rise_us <= 10000:
        p.error('beta must be positive and finite; rise-us must be in (0, 10000]')
    args.out.mkdir(parents=True, exist_ok=True)
    report_path = args.out / 'report.json'
    report_path.unlink(missing_ok=True)
    report = {'passed': False, 'scope': __doc__, 'runs': [],
              'assumptions': {'semiconductors': 'Generic SPICE BJTs and diode, not SC236/SC308 characterization',
                              'beta': args.beta, 'riseUs': args.rise_us,
                              'passives': 'Ideal nominal R/C values; no ESR, leakage or tolerance model',
                              'cpuLoad': '1 gigaohm and 10 pF; illustrative, not measured',
                              'supply': 'Ideal source with programmed ramps and a one-second power interruption',
                              'thresholdVolts': [.8, 2],
                              'timing': 'Observation windows test nominal behavior, not historical reset duration'},
              'sources': {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                          for name in ('reset_probe.py', 'circuit.py')}}
    try:
        components, report['connectivitySha256'] = load()
        report['tool'] = subprocess.check_output([args.ngspice, '--version'], text=True).strip()
        for isolated in (False, True):
            pair = [simulate(args, components, step, isolated) for step in (100, 50)]
            report['runs'].extend(pair)
            for coarse, fine in zip(pair[0]['boots'], pair[1]['boots']):
                if abs(coarse['releaseSecondsAt2V'] - fine['releaseSecondsAt2V']) > 100e-6:
                    raise ValueError('Reset release failed timestep convergence within 100 us')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(report_path)


if __name__ == '__main__':
    main()
