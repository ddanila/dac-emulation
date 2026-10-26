#!/usr/bin/env python3
"""Test DC bus alternatives and retain nominal-fixture failures as controls."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from bus_endpoint_candidates import MODES, branch, parameters, resistance
from failure_evidence import solver_diagnostic
from ttl7406_probe import sha

HERE = Path(__file__).resolve().parent


def run(out, executable):
    engine = Path(shutil.which(executable) or executable).resolve()
    limits = json.loads((HERE / 'bus_limits.json').read_text())
    contract = json.loads((HERE / 'bus_device_contract.json').read_text())
    out = out.resolve(); out.mkdir(parents=True, exist_ok=False)
    (out / 'spinit').write_text('* DC endpoint-only candidates; no code models.\n')
    report = {'completed': False, 'qualified': False, 'deviceAdmitted': False, 'cases': [],
              'runtime': {'path': str(engine), 'sha256': sha(engine)},
              'sources': {n: sha(HERE / n) for n in ('bus_endpoint_candidates.py', 'bus_endpoint_probe.py',
                          'bus_limits.json', 'bus_device_contract.json', 'failure_evidence.py', 'ttl7406_probe.py')},
              'scope': 'Rated-supply DC, enabled outputs. Published full-load endpoints and assumed linear interpolation at half/no load. No firmware tuning.',
              'acceptance': 'Full specified load must meet VOH/VOL at every tested rated supply; half/no-load points check implementation only, not independent device data.',
              'solverComparisonAllowanceVolts': 1e-8,
              'notEstablished': ['Physical output I/V or supply law', 'Switching and release dynamics',
                  'Reverse operation and leakage', 'Startup or brownout', 'U556 equivalence to Intel 2716',
                  'Temperature dependence', 'Coupled numerical convergence'],
              'decision': 'Retain both alternatives as DC-only candidates. Neither is a production replacement or admitted device model.'}
    try:
        for name, conditions in contract['devices'].items():
            profile = limits['profiles'][name]
            lo, hi, rlow, high = parameters(profile, conditions)
            for mode in ('nominal-control', *MODES):
                for supply in (lo, 5, hi):
                    for fraction in (0, .5, 1):
                        folder = out / f'{name}-{mode}-{supply:g}-{fraction:g}'; folder.mkdir()
                        rhigh = ((5-high['minimumVolts'])/high['sourceMagnitudeAmps'] if mode == 'nominal-control'
                                 else resistance(profile, conditions, mode, supply))
                        high_branch = (f'Rhigh vcc high {rhigh:.17g}' if mode == 'nominal-control'
                                       else branch(profile, conditions, mode))
                        deck = '\n'.join(['DC output endpoint probe', f'Vcc vcc 0 {supply:.17g}', high_branch,
                            f'Rlow low 0 {rlow:.17g}',
                            f'Ihigh high 0 {fraction*high["sourceMagnitudeAmps"]:.17g}',
                            f'Ilow 0 low {fraction*profile["outputLow"]["sinkAmps"]:.17g}',
                            '.control', 'set numdgt=17', 'set wr_singlescale', 'set wr_vecnames',
                            'op', 'wrdata trace.txt v(high) v(low)', 'quit', '.endc', '.end', ''])
                        (folder / 'probe.cir').write_text(deck)
                        proc = subprocess.run([str(engine), '-n', '-b', 'probe.cir'], cwd=folder,
                            env=dict(os.environ, SPICE_SCRIPTS=str(out)), capture_output=True, text=True, timeout=30)
                        log = proc.stdout + proc.stderr; (folder / 'ngspice.log').write_text(log)
                        proc.check_returncode()
                        if solver_diagnostic(log): raise ValueError('DC solver diagnostic')
                        rows = (folder / 'trace.txt').read_text().splitlines()
                        if len(rows) != 2 or rows[0].split() != ['vcc', 'v(high)', 'v(low)']:
                            raise ValueError('Unexpected DC output layout')
                        measured = list(map(float, rows[1].split()))
                        expected = [supply, supply-fraction*high['sourceMagnitudeAmps']*rhigh,
                                    fraction*profile['outputLow']['maximumVolts']]
                        if len(measured) != 3 or not all(math.isfinite(v) for v in measured) or any(abs(a-b)>1e-8 for a,b in zip(measured, expected)):
                            raise ValueError('Candidate implementation disagrees with analytic constraint')
                        passed = measured[1] >= high['minimumVolts']-1e-8 and measured[2] <= profile['outputLow']['maximumVolts']+1e-8
                        if mode != 'nominal-control' and not passed:
                            raise ValueError('Candidate violates output guarantee')
                        report['cases'].append({'profile': name, 'mode': mode, 'supplyVolts': supply,
                            'ratedLoadFraction': fraction, 'highOhms': rhigh, 'loadedHighVolts': measured[1],
                            'loadedLowVolts': measured[2], 'endpointPassed': passed,
                            'publishedTestPoint': fraction == 1, 'directory': folder.name,
                            'files': {n: sha(folder / n) for n in ('probe.cir', 'trace.txt', 'ngspice.log')}})
        failures = [c for c in report['cases'] if not c['endpointPassed']]
        if len(failures) != len(contract['devices']) or any(c['mode'] != 'nominal-control' or c['ratedLoadFraction'] != 1 for c in failures):
            raise ValueError('Missing expected nominal minimum-supply failure controls')
        if sha(engine) != report['runtime']['sha256']: raise ValueError('Runtime changed')
        report['completed'] = True
    except Exception as exc:
        report['error'] = str(exc); raise
    finally:
        (out / 'assessment.json').write_text(json.dumps(report, indent=2) + '\n')
    print(out / 'assessment.json')


def verify(out):
    report = json.loads((out / 'assessment.json').read_text())
    if report.get('completed') is not True or report.get('qualified') is not False or report.get('deviceAdmitted') is not False or report.get('error'):
        raise ValueError('Invalid candidate assessment status')
    for name, digest in report['sources'].items():
        if sha(HERE / name) != digest: raise ValueError('Stale candidate source: ' + name)
    limits = json.loads((HERE / 'bus_limits.json').read_text())
    contract = json.loads((HERE / 'bus_device_contract.json').read_text())
    expected = {(name, mode, supply, fraction)
                for name, conditions in contract['devices'].items()
                for mode in ('nominal-control', *MODES)
                for supply in (conditions['supplyRangeVolts'][0], 5, conditions['supplyRangeVolts'][1])
                for fraction in (0, .5, 1)}
    seen = set()
    for case in report['cases']:
        key = (case['profile'], case['mode'], case['supplyVolts'], case['ratedLoadFraction'])
        if key not in expected or key in seen: raise ValueError('Unexpected or repeated DC case')
        seen.add(key)
        name, mode, supply, fraction = key
        profile = limits['profiles'][name]; high = profile['outputHigh']
        rhigh = ((5-high['minimumVolts'])/high['sourceMagnitudeAmps'] if mode == 'nominal-control'
                 else resistance(profile, contract['devices'][name], mode, supply))
        voltage = supply-fraction*high['sourceMagnitudeAmps']*rhigh
        low = fraction*profile['outputLow']['maximumVolts']
        folder = out / case['directory']
        if folder.parent != out or set(case['files']) != {'probe.cir', 'trace.txt', 'ngspice.log'}:
            raise ValueError('Unexpected retained artifacts')
        for name, digest in case['files'].items():
            if sha(folder / name) != digest: raise ValueError('Changed retained DC evidence')
        rows = (folder / 'trace.txt').read_text().splitlines()
        if len(rows) != 2 or rows[0].split() != ['vcc', 'v(high)', 'v(low)']:
            raise ValueError('Invalid retained DC trace')
        values = list(map(float, rows[1].split()))
        if len(values) != 3 or not all(math.isfinite(v) for v in values) or any(abs(a-b)>1e-8 for a,b in zip(values, [supply, voltage, low])):
            raise ValueError('Retained DC values fail analytic check')
        passed = values[1] >= high['minimumVolts']-1e-8 and values[2] <= profile['outputLow']['maximumVolts']+1e-8
        if case['endpointPassed'] != passed or case['loadedHighVolts'] != values[1] or case['loadedLowVolts'] != values[2] or case['highOhms'] != rhigh or case['publishedTestPoint'] != (fraction == 1):
            raise ValueError('Assessment differs from retained DC evidence')
        if mode != 'nominal-control' and not passed: raise ValueError('Candidate fails endpoint')
    if seen != expected: raise ValueError('Missing DC cases')
    print('Retained DC candidate constraints verified; device admission remains open.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--ngspice', default='ngspice')
    p.add_argument('--verify', action='store_true')
    a = p.parse_args()
    if a.verify: verify(a.out)
    else: run(a.out, a.ngspice)
