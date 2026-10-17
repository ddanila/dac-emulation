#!/usr/bin/env python3
"""Explore the reference sensing topology in ngspice; not device qualification."""
import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = Path(__file__).resolve().parents[1] / 'reference'


def node(name):
    return '0' if name == '/GND' else 'n_' + name.lstrip('/').replace('+', 'p')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', default='ngspice')
    parser.add_argument('--beta', type=float, default=100)
    parser.add_argument('--contact-ohms', type=float, default=100)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/sense')
    args = parser.parse_args()
    if not all(math.isfinite(x) and x > 0 for x in (args.beta, args.contact_ohms)):
        parser.error('beta and contact-ohms must be finite and positive')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    # Never leave a previous successful result behind after an aborted run.
    for name in ('report.json', 'sweep.txt'):
        (out / name).unlink(missing_ok=True)
    source = (REFERENCE / 'connectivity.json').read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    if digest != json.loads((REFERENCE / 'source.json').read_text())['sha256']:
        raise ValueError('Connectivity hash mismatch')
    components = json.loads(source)['components']
    lines = ['Robotron reference sensing slice; exploratory generic PNP model',
             'Vcc n_p5V 0 5', 'Vscan scan 0 0',
             f'.model PNP_EXPLORATORY PNP(IS=1e-14 BF={args.beta} VAF=100)']
    refs = []
    for ref in ('R1', 'R2'):
        c = components[ref]
        match = re.fullmatch(r'8x(\d+(?:k\d+)?)', c['type'])
        if not match or set(c['pins']) != {str(i) for i in range(1, 10)}:
            raise ValueError('Unsupported resistor network: ' + ref)
        value = match[1].replace('k', '.') + 'k' if 'k' in match[1] else match[1]
        for pin in range(2, 10):
            lines.append(f"{ref}_{pin} {node(c['pins']['1'])} {node(c['pins'][str(pin)])} {value}")
        refs.append(ref)
    for i in range(1, 9):
        ref = f'R9.{i}'
        c = components[ref]
        value = c['type'].replace('k', '.') + 'k'
        lines.append(f"{ref} {node(c['pins']['1'])} {node(c['pins']['2'])} {value}")
        refs.append(ref)
        ref = f'V4.{i}'
        c = components[ref]
        if c['type'] != 'SC308C' or set(c['pins']) != {'C', 'B', 'E'}:
            raise ValueError('Unsupported sensing transistor: ' + ref)
        lines.append(f"Q{ref} {' '.join(node(c['pins'][p]) for p in ('C', 'B', 'E'))} PNP_EXPLORATORY")
        refs.append(ref)
    for row in range(8):
        lines.append(f'Rcontact{row} scan n_ROW{row} {args.contact_ohms}')
    outputs = [f'v(n_SENSE{i})' for i in range(8)]
    lines += ['.control', 'set wr_singlescale', 'set wr_vecnames', 'dc Vscan 0 5 .01',
              'wrdata sweep.txt ' + ' '.join(outputs), 'quit', '.endc', '.end']
    deck = '\n'.join(lines) + '\n'
    (out / 'sense.cir').write_text(deck)
    result = subprocess.run([args.ngspice, '-b', 'sense.cir'], cwd=out,
                            capture_output=True, text=True, timeout=60)
    (out / 'ngspice.log').write_text(result.stdout + result.stderr)
    result.check_returncode()
    rows = [[float(x) for x in line.split()] for line in (out / 'sweep.txt').read_text().splitlines()[1:]]
    if not rows or any(len(r) != 9 or not all(map(math.isfinite, r)) for r in rows):
        raise ValueError('Incomplete or invalid analog sweep')
    if abs(rows[0][0]) > 1e-9 or abs(rows[-1][0] - 5) > 1e-9:
        raise ValueError('Sweep endpoints missing')
    report = {
        'scope': 'DC sensing-front-end feasibility probe, not complete board or SC308 qualification',
        'connectivitySha256': digest,
        'deckSha256': hashlib.sha256(deck.encode()).hexdigest(),
        'generatorSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'tool': subprocess.check_output([args.ngspice, '--version'], text=True).strip(),
        'includedReferences': refs,
        'assumptions': {'supplyVolts': 5, 'contactOhms': args.contact_ohms,
                        'PNP': {'IS': 1e-14, 'BF': args.beta, 'VAF': 100},
                        'deviceModel': 'exploratory generic PNP; not fitted to SC308 datasheet',
                        'boundary': 'All rows driven together through contact resistors; no column driver, latch input load, CPU, ROM, reset, oscillator or cable model'},
        'senseVoltsAtScanLow': rows[0][1:], 'senseVoltsAtScanHigh': rows[-1][1:],
        'outputs': outputs,
        'endpointPolarityPassed': all(v > 2 for v in rows[0][1:]) and all(v < .8 for v in rows[-1][1:]),
    }
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    if not report['endpointPolarityPassed']:
        raise ValueError('Exploratory model failed the chosen 0.8/2 V endpoint polarity check; inspect report and sweep')
    print(json.dumps({k: report[k] for k in ('scope', 'senseVoltsAtScanLow', 'senseVoltsAtScanHigh')}, indent=2))


if __name__ == '__main__':
    main()
