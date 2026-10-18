#!/usr/bin/env python3
"""Measure nominal NAND switching in the TI totem-pole load fixture."""
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


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def crossing(rows, column, rising, start, end):
    """Return the unique 1.5 V crossing bracket in a specified stimulus window."""
    found = []
    for left, right in zip(rows, rows[1:]):
        if left[0] < start or right[0] > end:
            continue
        a, b = left[column], right[column]
        crosses = (a < 1.5 <= b) if rising else (a > 1.5 >= b)
        if crosses:
            found.append((left[0], right[0]))
    if len(found) != 1:
        raise ValueError(f'Expected one crossing, found {len(found)}')
    return found[0]


def delays(rows, maximum_delays=None):
    maximum_delays = maximum_delays or {"tPHL": 15, "tPLH": 15}
    if len(rows) < 2 or any(len(r) != 3 or not all(map(math.isfinite, r)) for r in rows):
        raise ValueError('Invalid waveform rows')
    if any(b[0] <= a[0] for a, b in zip(rows, rows[1:])):
        raise ValueError('Non-increasing waveform time')
    if rows[0][0] != 0 or rows[-1][0] < 800e-9:
        raise ValueError('Incomplete waveform')
    result = {}
    for name, rise, lo, hi in [('tPHL', True, 190e-9, 300e-9), ('tPLH', False, 590e-9, 700e-9)]:
        source = crossing(rows, 1, rise, lo, hi)
        target = crossing(rows, 2, not rise, lo, hi)
        lower, upper = (target[0]-source[1])*1e9, (target[1]-source[0])*1e9
        result[name] = {'minimumNs': lower, 'maximumNs': upper,
                        'withinDelayLimit': 0 <= lower and upper <= maximum_delays[name]}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, default=HERE/'ls_nand_pullup.cir')
    parser.add_argument('--ngspice', default='ngspice')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--require-limits', action='store_true',
                        help='Fail unless both timestep convergence and delay limits pass; not device qualification')
    args = parser.parse_args()
    executable = shutil.which(args.ngspice)
    if not executable:
        parser.error('ngspice executable not found')
    executable = Path(executable).resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    model = args.model.read_bytes()
    limits_path = HERE/'gate_switching_limits.json'
    report = {'completed': False, 'qualified': False,
              'scope': 'Exploratory switching check; generic fixture diodes are not verified 1N3064 equivalents. No DL000, startup, supply-current or specimen calibration.',
              'limits': json.loads(limits_path.read_text()),
              'sources': {p.name: sha(p) for p in [Path(__file__), limits_path, args.model, HERE/'failure_evidence.py']},
              'executableSha256': sha(executable), 'cases': []}
    (args.out/'spinit').write_text('* Pure SPICE switching fixture.\n')
    env = dict(os.environ, SPICE_SCRIPTS=str(args.out.resolve()))
    report['spinitSha256'] = sha(args.out/'spinit')
    try:
        for pin in ['a', 'b']:
            for edge in [1, 7]:
                case = {'pin': pin, 'inputEdgeNs': edge, 'runs': []}
                for step in [0.1, 0.05]:
                    out = args.out/f'{pin}-{edge}ns-{step}ns'
                    out.mkdir()
                    (out/'model.cir').write_bytes(model)
                    other = 'b' if pin == 'a' else 'a'
                    deck = f'''NAND switching fixture (nominal load diodes)
.include model.cir
.temp 25
Vcc vp 0 5
Vinput generator 0 PULSE(0 3 200n {edge}n {edge}n {400-edge}n 1u)
Rsource generator {pin} 50
Vother {other} 0 3
Xdut a b y vp 0 LS_NAND_NOMINAL
Rload vp load 2k
Dload load y FIXTURE_DIODE
D1 load d1 FIXTURE_DIODE
D2 d1 d2 FIXTURE_DIODE
D3 d2 0 FIXTURE_DIODE
.model FIXTURE_DIODE D(IS=1e-14 N=1 RS=1 CJO=0 TT=0)
Cload y 0 15p
.control
set numdgt=17
set wr_singlescale
set wr_vecnames
tran {step}n 800n 0 {step}n
wrdata trace.txt v({pin}) v(y)
quit
.endc
.end
'''
                    (out/'probe.cir').write_text(deck)
                    run = subprocess.run([str(executable), '-n', '-b', 'probe.cir'], cwd=out, env=env,
                                         capture_output=True, text=True, timeout=60)
                    log = run.stdout+run.stderr
                    (out/'ngspice.log').write_text(log)
                    run.check_returncode()
                    if solver_diagnostic(log):
                        raise ValueError('Solver diagnostics: '+str(out))
                    rows = [[float(v) for v in line.split()] for line in (out/'trace.txt').read_text().splitlines()[1:]]
                    case['runs'].append({'stepNs': step, 'delays': delays(rows, report['limits']['maximumDelayNs']),
                        'artifacts': {p.name: sha(p) for p in sorted(out.iterdir())}})
                case['maximumBracketEndpointDifferenceNs'] = max(abs(case['runs'][0]['delays'][name][key]-case['runs'][1]['delays'][name][key])
                    for name in ['tPHL', 'tPLH'] for key in ['minimumNs', 'maximumNs'])
                case['converged'] = case['maximumBracketEndpointDifferenceNs'] <= report['limits']['refinementBudgetNs']
                report['cases'].append(case)
        if sha(executable) != report['executableSha256']:
            raise ValueError('Simulator changed during run')
        report['completed'] = True
        report['numericallyConverged'] = all(c['converged'] for c in report['cases'])
        report['withinDelayLimits'] = all(d['withinDelayLimit'] for c in report['cases'] for r in c['runs'] for d in r['delays'].values())
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(args.out/'report.json')
    if args.require_limits and not (report['numericallyConverged'] and report['withinDelayLimits']):
        raise SystemExit('Switching regression failed: inspect report.json for convergence and delay limits')


if __name__ == '__main__':
    main()
