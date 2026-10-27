#!/usr/bin/env python3
"""Check selected DL000 DC limits; passing is not complete gate calibration."""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', type=Path, default=HERE / 'ls_nand_nominal.cir')
    p.add_argument('--out', type=Path, default=HERE.parents[2] / 'build/keyboard-controller-analog/gate-dc')
    p.add_argument('--require-qualified', action='store_true')
    p.add_argument('--ngspice', default='ngspice')
    args = p.parse_args()
    limits = json.loads((HERE / 'gate_limits.json').read_text())
    args.out.mkdir(parents=True, exist_ok=True)
    executable = shutil.which(args.ngspice)
    if executable is None:
        p.error('ngspice executable not found')
    executable = Path(executable).resolve()
    runtime_sha = hashlib.sha256(executable.read_bytes()).hexdigest()
    (args.out / 'spinit').write_text('* Pure SPICE gate fixture; no external initialization.\n')
    environment = dict(os.environ, SPICE_SCRIPTS=str(args.out.resolve()))
    report = {'completed': False, 'qualified': False, 'scope': __doc__, 'limits': limits,
              'qualificationScope': 'Selected static points at 25 C only; no temperature, switching, supply-current or oscillator qualification',
              'executableSha256': runtime_sha,
              'spinitSha256': hashlib.sha256((args.out / 'spinit').read_bytes()).hexdigest(),
              'sources': {str(path.name): hashlib.sha256(path.read_bytes()).hexdigest() for path in
                          (Path(__file__), HERE / 'gate_limits.json', args.model)}, 'points': []}
    try:
        report['ngspice'] = subprocess.check_output([str(executable), '--version'], text=True).strip()
        for case in limits['points']:
            out = args.out / case['name']
            out.mkdir(exist_ok=True)
            (out / 'model.cir').write_bytes(args.model.read_bytes())
            (out / 'trace.txt').unlink(missing_ok=True)
            lines = ['DL000 static fixture', '.include model.cir', '.temp 25',
                     f'Vcc vp 0 {case["supplyVolts"]}', f'Va a 0 {case["aVolts"]}',
                     f'Vb b 0 {case["bVolts"]}', 'Xdut a b y vp 0 LS_NAND_NOMINAL']
            if case.get('shortOutput'):
                lines.append('Vshort y 0 0')
            else:
                lines.append(f'Iload y 0 {case.get("loadAmps", 0)}')
            signals = 'v(y) i(Va) i(Vb)' + (' i(Vshort)' if case.get('shortOutput') else '')
            lines += ['.control', 'set wr_singlescale', 'set wr_vecnames', 'op',
                      'wrdata trace.txt ' + signals, 'quit', '.endc', '.end']
            deck = '\n'.join(lines) + '\n'
            (out / 'gate.cir').write_text(deck)
            proc = subprocess.run([str(executable), '-n', '-b', 'gate.cir'], cwd=out,
                                  env=environment, capture_output=True, text=True, timeout=60)
            log = proc.stdout + proc.stderr
            (out / 'ngspice.log').write_text(log)
            proc.check_returncode()
            if re.search(r'warning|error|failed|singular', log, re.I):
                raise ValueError('Solver diagnostics: ' + case['name'])
            rows = [[float(v) for v in line.split()] for line in (out / 'trace.txt').read_text().splitlines()[1:]]
            if len(rows) != 1 or len(rows[0]) != (5 if case.get('shortOutput') else 4) or not all(map(math.isfinite, rows[0])):
                raise ValueError('Invalid static trace: ' + case['name'])
            values = dict(zip(('outputVolts','inputAAmps','inputBAmps','shortAmps'), rows[0][1:]))
            checks = []
            for condition in case['checks']:
                value = abs(values[condition['signal']]) if condition.get('absolute') else values[condition['signal']]
                checks.append({**condition, 'observed': value,
                               'withinLimits': condition.get('minimum', -math.inf) <= value <= condition.get('maximum', math.inf)})
            report['points'].append({'name': case['name'], 'values': values, 'checks': checks,
                                     'deckSha256': hashlib.sha256(deck.encode()).hexdigest(),
                                     'traceSha256': hashlib.sha256((out / 'trace.txt').read_bytes()).hexdigest()})
        if hashlib.sha256(executable.read_bytes()).hexdigest() != runtime_sha:
            raise ValueError('Simulator changed during gate fixture')
        report['completed'] = True
        report['qualified'] = all(c['withinLimits'] for point in report['points'] for c in point['checks'])
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(args.out / 'report.json')
    if args.require_qualified and not report['qualified']:
        raise SystemExit('Model fails selected DL000 static limits')


if __name__ == '__main__':
    main()
