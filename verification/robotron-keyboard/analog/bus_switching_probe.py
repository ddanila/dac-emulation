#!/usr/bin/env python3
"""Screen DC-only I8282 drivers against the published loaded rise/fall test."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from bus_endpoint_candidates import MODES, parameters, resistance
from failure_evidence import solver_diagnostic
from ttl7406_probe import sha

HERE = Path(__file__).resolve().parent
SOURCES = ('bus_switching_probe.py', 'bus_switching_limits.json',
           'bus_endpoint_candidates.py', 'bus_limits.json', 'bus_device_contract.json',
           'failure_evidence.py', 'ttl7406_probe.py')
ALLOWANCE = 1e-11  # SPICE measurement/step error, not an expanded device limit.


def duration(drive, ohms, load, start, end):
    values = (drive, ohms, load['biasVolts'], load['resistanceOhms'],
              load['capacitanceFarads'], start, end)
    if not all(math.isfinite(x) for x in values) or min(ohms, load['resistanceOhms'], load['capacitanceFarads']) <= 0:
        raise ValueError('Invalid RC conditions')
    conductance = 1/ohms + 1/load['resistanceOhms']
    final = (drive/ohms + load['biasVolts']/load['resistanceOhms'])/conductance
    if not ((final > end > start) or (final < end < start)):
        raise ValueError('Output cannot cross the required thresholds')
    return load['capacitanceFarads']/conductance * math.log((final-start)/(final-end))


def cases():
    limits = json.loads((HERE/'bus_switching_limits.json').read_text())
    profile = json.loads((HERE/'bus_limits.json').read_text())['profiles']['I8282']
    contract = json.loads((HERE/'bus_device_contract.json').read_text())['devices']['I8282']
    low, high, rlow, _ = parameters(profile, contract)
    if limits['supplyRangeVolts'] != [low, high]: raise ValueError('Inconsistent rated supply')
    for mode in MODES:
        for supply in (low, 5, high):
            for edge in ('rise', 'fall'):
                ohms = resistance(profile, contract, mode, supply) if edge == 'rise' else rlow
                drive = supply if edge == 'rise' else 0
                spec = limits[edge]; load = limits['switchingLoad']
                seconds = duration(drive, ohms, load, spec['fromVolts'], spec['toVolts'])
                yield {'mode': mode, 'supplyVolts': supply, 'edge': edge,
                       'driveVolts': drive, 'ohms': ohms, 'analyticSeconds': seconds,
                       'maximumSeconds': spec['maximumSeconds'],
                       'withinPublishedLimit': seconds <= spec['maximumSeconds']}, load, spec


def run(out, executable):
    out = out.resolve(); out.mkdir(parents=True, exist_ok=False)
    engine = Path(shutil.which(executable) or executable).resolve()
    (out/'spinit').write_text('* Isolated linear switching-load screen.\n')
    report = {'completed': False, 'qualified': False, 'deviceAdmitted': False,
              'scope': 'I8282 enabled-output transitions under its published switching load. Instantaneous full drive and no added output capacitance give these resistor models their fastest response.',
              'decision': 'Reject both DC-only I8282 candidates as complete switching drivers. This does not reject the CPU/ROM candidates or identify a physical replacement.',
              'runtime': {'path': str(engine), 'sha256': sha(engine)},
              'sources': {n: sha(HERE/n) for n in SOURCES}, 'cases': []}
    for case, load, spec in cases():
        name = f'{case["mode"]}-{case["supplyVolts"]:g}-{case["edge"]}'
        folder = out/name; folder.mkdir()
        direction = 'RISE' if case['edge'] == 'rise' else 'FALL'
        initial = 0 if direction == 'RISE' else case['supplyVolts']
        deck = '\n'.join(['I8282 published switching-load screen',
            f'Vdrive drive 0 {case["driveVolts"]:.17g}', f'Rdrive drive out {case["ohms"]:.17g}',
            f'Vload bias 0 {load["biasVolts"]:.17g}', f'Rload bias out {load["resistanceOhms"]:.17g}',
            f'Cload out 0 {load["capacitanceFarads"]:.17g} IC={initial:.17g}',
            '.options reltol=1e-8 abstol=1e-12', '.control', 'tran 0.05n 200n 0 0.05n uic',
            f'meas tran edge_time TRIG v(out) VAL={spec["fromVolts"]} {direction}=1 TARG v(out) VAL={spec["toVolts"]} {direction}=1',
            'quit', '.endc', '.end', ''])
        (folder/'probe.cir').write_text(deck)
        proc = subprocess.run([str(engine), '-n', '-b', 'probe.cir'], cwd=folder,
            env=dict(os.environ, SPICE_SCRIPTS=str(out)), capture_output=True, text=True, timeout=30)
        log = proc.stdout+proc.stderr; (folder/'ngspice.log').write_text(log)
        proc.check_returncode()
        measured = measurement(log)
        if abs(measured-case['analyticSeconds']) > ALLOWANCE: raise ValueError('SPICE disagrees with RC solution')
        case.update(measuredSeconds=measured, directory=name,
                    files={n: sha(folder/n) for n in ('probe.cir', 'ngspice.log')})
        report['cases'].append(case)
    if sha(engine) != report['runtime']['sha256']: raise ValueError('Runtime changed')
    report['completed'] = True
    (out/'assessment.json').write_text(json.dumps(report, indent=2)+'\n')
    verify(out)


def measurement(log):
    if solver_diagnostic(log): raise ValueError('Solver failure')
    matches = re.findall(r'^edge_time\s*=\s*(\S+)', log, re.MULTILINE)
    if len(matches) != 1: raise ValueError('Missing/duplicate switching measurement')
    value = float(matches[0])
    if not math.isfinite(value) or value <= 0: raise ValueError('Invalid switching measurement')
    return value


def verify(out):
    report = json.loads((out/'assessment.json').read_text())
    if report.get('completed') is not True or report.get('qualified') is not False or report.get('deviceAdmitted') is not False:
        raise ValueError('Invalid assessment status')
    if report['sources'] != {n: sha(HERE/n) for n in SOURCES}: raise ValueError('Stale sources')
    expected = list(cases())
    if len(report['cases']) != len(expected): raise ValueError('Missing or duplicate cases')
    for actual, (case, _, _) in zip(report['cases'], expected):
        if any(actual.get(k) != v for k,v in case.items()): raise ValueError('Changed case or analytic result')
        folder = out/actual['directory']
        if folder.parent != out or set(actual['files']) != {'probe.cir','ngspice.log'}: raise ValueError('Invalid artifacts')
        if any(sha(folder/n) != h for n,h in actual['files'].items()): raise ValueError('Changed evidence')
        measured = measurement((folder/'ngspice.log').read_text())
        if measured != actual['measuredSeconds'] or abs(measured-case['analyticSeconds']) > ALLOWANCE:
            raise ValueError('Invalid retained measurement')
        if (measured <= case['maximumSeconds']) != case['withinPublishedLimit']:
            raise ValueError('Ambiguous threshold result')
    print('I8282 switching constraints checked; device admission remains open.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--ngspice', default='ngspice')
    p.add_argument('--verify', action='store_true')
    a = p.parse_args()
    if a.verify: verify(a.out)
    else: run(a.out, a.ngspice)
