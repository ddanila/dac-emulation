#!/usr/bin/env python3
"""Validate candidate junction families against additional LS00 DC conditions."""
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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--ngspice', default='ngspice')
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    executable = Path(shutil.which(args.ngspice) or args.ngspice).resolve(strict=True)
    out = args.out.resolve();out.mkdir(parents=True, exist_ok=False)
    limits_path = HERE/'ls00_validation_limits.json'
    limits = json.loads(limits_path.read_text())
    shutil.copyfile(args.model, out/'model.cir')
    (out/'spinit').write_text('* Pure SPICE; explicit initialization.\n')
    report = {'completed': False, 'qualified': False, 'limits': limits,
              'engineSha256': sha(executable), 'sources': {p.name: sha(p) for p in
              [Path(__file__), limits_path, args.model, HERE/'ls00_transistor_probe.py', HERE/'failure_evidence.py']},
              'spinitSha256': sha(out/'spinit'), 'cases': []}
    try:
        for case in limits['cases']:
            name = case['name']
            lines = ['LS00 additional DC conditions', '.include model.cir',
                     '.options reltol=1e-8 vntol=1e-10 abstol=1e-14', f'.temp {limits["temperatureC"]}',
                     f'Vcc vp 0 {case["supply"]}', f'Va a 0 {case["a"]}', f'Vb b 0 {case["b"]}',
                     'Xgate a b y vp 0 LS00_TRANSISTOR_CANDIDATE']
            for gate in range(1, case.get('gates', 1)):
                lines.append(f'Xextra{gate} a b y{gate} vp 0 LS00_TRANSISTOR_CANDIDATE')
            lines.append('Vshort y 0 0' if case.get('shortOutput') else f'Iload y 0 {case.get("load", 0)}')
            signals = 'v(y) i(Vcc) i(Va) i(Vb)' + (' i(Vshort)' if case.get('shortOutput') else '')
            lines += ['.control', 'set numdgt=17', 'set wr_singlescale', 'set wr_vecnames', 'op',
                      f'wrdata {name}.txt {signals}', 'quit', '.endc', '.end']
            deck = out/(name+'.cir');deck.write_text('\n'.join(lines)+'\n')
            log = out/(name+'.log')
            with log.open('w') as stream:
                run = subprocess.run([str(executable), '-n', '-b', deck.name], cwd=out,
                    env=dict(os.environ, SPICE_SCRIPTS=str(out)), stdout=stream, stderr=subprocess.STDOUT, timeout=30)
            run.check_returncode()
            if solver_diagnostic(log.read_text()):raise ValueError('Solver diagnostics: '+name)
            trace = out/(name+'.txt');rows = trace.read_text().splitlines()
            if len(rows)!=2 or rows[0].split()[1:]!=signals.split():raise ValueError('Invalid DC columns: '+name)
            values = list(map(float, rows[1].split()))
            if len(values)!=len(signals.split())+1 or not all(map(math.isfinite,values)):raise ValueError('Invalid DC values: '+name)
            observed = dict(zip(['outputVolts','supplyAmps','inputAAmps','inputBAmps','shortAmps'], values[1:]))
            for key in ['supplyAmps','inputAAmps','inputBAmps']:observed[key] *= -1
            checks = [{**c, 'observed': observed[c['signal']],
                       'passed': c['minimum']<=observed[c['signal']]<=c['maximum']} for c in case['checks']]
            report['cases'].append({'name': name, 'observed': observed, 'checks': checks,
                                   'artifacts': {p.name: sha(p) for p in [deck, log, trace]}})
        if sha(executable)!=report['engineSha256']:raise ValueError('Engine changed')
        report['completed'] = True
        report['limitsPassed'] = all(c['passed'] for row in report['cases'] for c in row['checks'])
    finally:
        (out/'assessment.json').write_text(json.dumps(report, indent=2)+'\n')
    return 0 if report['limitsPassed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
