#!/usr/bin/env python3
"""Screen an explicit generic-junction family; never select a board default."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate(source, beta, diode_is):
    # Exact substitutions deliberately reject changes to the baseline template.
    old = 'NPN(IS=1e-16 BF=100 BR=1 VAF=100'
    diode = 'D(IS=1e-8 N=1 RS=10 CJO=0.2p)'
    if source.count(old) != 1 or source.count(diode) != 1:
        raise ValueError('Candidate template changed; review parameter mapping')
    source = source.replace(old, f'NPN(IS=1e-16 BF={beta:g} BR=1 VAF=100')
    source = source.replace(diode, f'D(IS={diode_is:g} N=1 RS=10 CJO=0.2p)')
    source = source.replace('* No parameter was fitted to the board clock or to force a qualification pass.',
                            '* Generic-junction parameter screen against device limits; no board-clock target.')
    return source + ('\n* Interface adapter only; same transistor circuit.\n'
                     '.subckt LS_NAND_NOMINAL a b y vp g\n'
                     'Xgate a b y vp g LS00_TRANSISTOR_CANDIDATE\n'
                     '.ends LS_NAND_NOMINAL\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', default='ngspice')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    baseline = HERE/'ls00_transistor_candidate.cir'
    report = {'completed': False, 'qualified': False,
              'scope': 'Exploratory discrete parameter family, not a physical process range or continuous robustness proof. No board-frequency target, startup qualification or DL000 equivalence.',
              'selection': 'All candidates receive DC screening. Output-limit survivors receive additional DC and switching checks; no winner is installed.',
              'assumptions': 'Shared generic Schottky junction parameters and NPN forward beta vary; topology, resistor values and other junction parameters remain fixed. Switching fixture diodes remain unqualified.',
              'grid': {'npnForwardBeta': [50, 100, 200], 'schottkySaturationAmps': [1e-12, 1e-11, 1e-10, 1e-9, 1e-8]},
              'sources': {p.name: sha(p) for p in [Path(__file__), baseline, HERE/'ls00_transistor_probe.py', HERE/'gate_switching_probe.py', HERE/'gate_switching_limits.json', HERE/'ls00_validation_probe.py', HERE/'ls00_validation_limits.json']},
              'candidates': []}
    try:
        for beta, diode_is in itertools.product(report['grid']['npnForwardBeta'], report['grid']['schottkySaturationAmps']):
            name = f'bf-{beta}-is-{diode_is:g}'
            out = args.out/name;out.mkdir()
            model = out/'candidate.cir'
            model.write_text(candidate(baseline.read_text(), beta, diode_is))
            record = {'name': name, 'npnForwardBeta': beta, 'schottkySaturationAmps': diode_is,
                      'modelSha256': sha(model)}
            report['candidates'].append(record)
            with (out/'dc-run.log').open('w') as log:
                run = subprocess.run([sys.executable, str(HERE/'ls00_transistor_probe.py'), '--model', str(model),
                    '--ngspice', args.ngspice, '--out', str(out/'dc')], stdout=log, stderr=subprocess.STDOUT, timeout=120)
            dc_path = out/'dc/assessment.json';dc = json.loads(dc_path.read_text())
            if not dc['completed'] or run.returncode not in (0, 1):
                raise ValueError('DC probe did not complete: '+name)
            record.update(dcOutputLimitsPassed=dc['outputLimitsPassed'], dcReportSha256=sha(dc_path),
                          minimumHighVolts=min(c['outputVolts'] for c in dc['cases'] if c['outputHigh']),
                          maximumLowVolts=max(c['outputVolts'] for c in dc['cases'] if not c['outputHigh']))
            if dc['outputLimitsPassed']:
                with (out/'validation-run.log').open('w') as log:
                    run = subprocess.run([sys.executable, str(HERE/'ls00_validation_probe.py'), '--model', str(model),
                        '--ngspice', args.ngspice, '--out', str(out/'validation')], stdout=log, stderr=subprocess.STDOUT, timeout=120)
                validation_path = out/'validation/assessment.json';validation = json.loads(validation_path.read_text())
                if not validation['completed'] or run.returncode not in (0, 1):
                    raise ValueError('Additional DC validation did not complete: '+name)
                record.update(additionalDcLimitsPassed=validation['limitsPassed'], validationReportSha256=sha(validation_path))
                with (out/'switching-run.log').open('w') as log:
                    run = subprocess.run([sys.executable, str(HERE/'gate_switching_probe.py'), '--model', str(model),
                        '--ngspice', args.ngspice, '--out', str(out/'switching')], stdout=log, stderr=subprocess.STDOUT, timeout=600)
                switch_path = out/'switching/report.json';switch = json.loads(switch_path.read_text())
                record.update(switchingCompleted=switch['completed'], switchingReportSha256=sha(switch_path),
                              switchingConverged=switch.get('numericallyConverged', False),
                              switchingLimitsPassed=switch.get('withinDelayLimits', False), switchingExitCode=run.returncode)
                # An incomplete numerical run is retained, never counted as passing.
            (args.out/'assessment.json').write_text(json.dumps(report, indent=2)+'\n')
        report['completed'] = True
    finally:
        (args.out/'assessment.json').write_text(json.dumps(report, indent=2)+'\n')
    print(args.out/'assessment.json')


if __name__ == '__main__':
    main()
