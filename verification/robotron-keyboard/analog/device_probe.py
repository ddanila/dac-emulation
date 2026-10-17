#!/usr/bin/env python3
"""Compare exploratory device models with published DC limits; no automatic fitting."""
import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

from circuit import nominal_models

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def interpolate(samples, ic):
    pair = next(((a, b) for a, b in zip(samples, samples[1:]) if a[1] <= ic < b[1]), None)
    if pair is None:
        raise ValueError('Sweep does not bracket specified collector current')
    a, b = pair
    fraction = (ic - a[1]) / (b[1] - a[1])
    return a[0] + fraction * (b[0] - a[0]), a[2] + fraction * (b[2] - a[2])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', default='ngspice')
    parser.add_argument('--beta', type=float, default=100)
    parser.add_argument('--npn-profile', choices=('generic', 'sc236-dc'), default='generic')
    parser.add_argument('--require-qualified', action='store_true')
    parser.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/devices')
    args = parser.parse_args()
    if not math.isfinite(args.beta) or args.beta <= 0:
        parser.error('beta must be positive and finite')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    trace = out / 'trace.txt'
    trace.unlink(missing_ok=True)
    limits = json.loads((HERE / 'device_limits.json').read_text())['SC236D']
    report = {'completed': False, 'qualified': False, 'scope': __doc__,
              'device': 'SC236D', 'limits': limits, 'beta': args.beta, 'npnProfile': args.npn_profile,
              'qualificationScope': 'Selected DC gain points only; not transient, saturation, temperature or full-device qualification',
              'points': [], 'vbeComparisons': [], 'sources': {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                                      for name in ('device_probe.py', 'device_limits.json', 'circuit.py', 'sc236_dc.cir')}}
    try:
        deck = '\n'.join([
            'SC236D nominal model DC characterization', *nominal_models(args.beta, args.npn_profile),
            f'.temp {limits["temperatureC"]}', f'Vc c 0 {limits["vceVolts"]}',
            'Vb b 0 0', 'Qdut c b 0 NPN_NOMINAL',
            '.control', 'set wr_singlescale', 'set wr_vecnames',
            'dc Vb .3 .9 .0001', 'wrdata trace.txt v(b) i(Vc) i(Vb)',
            'quit', '.endc', '.end', ''])
        (out / 'device.cir').write_text(deck)
        report['deckSha256'] = hashlib.sha256(deck.encode()).hexdigest()
        report['tool'] = subprocess.check_output([args.ngspice, '--version'], text=True).strip()
        proc = subprocess.run([args.ngspice, '-n', '-b', 'device.cir'], cwd=out,
                              capture_output=True, text=True, timeout=60)
        log = proc.stdout + proc.stderr
        (out / 'ngspice.log').write_text(log)
        proc.check_returncode()
        if re.search(r'warning|error|failed|singular', log, re.I):
            raise ValueError('Solver diagnostics; inspect ngspice.log')
        rows = [[float(x) for x in line.split()] for line in trace.read_text().splitlines()[1:]]
        if not rows or any(len(row) != 4 or not all(map(math.isfinite, row)) for row in rows):
            raise ValueError('Invalid DC sweep')
        # Voltage-source currents enter their positive terminals; DUT currents have opposite sign.
        samples = [(row[1], -row[2], -row[3]) for row in rows]
        if any(b[1] <= a[1] for a, b in zip(samples, samples[1:])):
            raise ValueError('Collector current sweep is not strictly increasing')
        for target in limits['dcGain']:
            ic = target['collectorAmps']
            vbe, ib = interpolate(samples, ic)
            if ib <= 0:
                raise ValueError('Invalid base current')
            gain = ic / ib
            report['points'].append({**target, 'modelGain': gain,
                                     'modelVbeVolts': vbe,
                                     'withinLimits': target['minimum'] <= gain <= target['maximum']})
        # Typical voltages have no published acceptance band; report residuals, not pass/fail.
        for target in limits['vbeTypical']:
            vbe, _ = interpolate(samples, target['collectorAmps'])
            report['vbeComparisons'].append({**target, 'modelVolts': vbe,
                                             'differenceVolts': vbe - target['volts']})
        report['qualified'] = all(p['withinLimits'] for p in report['points'])
        report['completed'] = True
        report['traceSha256'] = hashlib.sha256(trace.read_bytes()).hexdigest()
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(out / 'report.json')
    if args.require_qualified and not report['qualified']:
        raise SystemExit('Model fails published DC gain limits')


if __name__ == '__main__':
    main()
