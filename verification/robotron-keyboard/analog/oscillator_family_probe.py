#!/usr/bin/env python3
"""Apply the unchanged oscillator gates to every surviving junction candidate."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidates(screen_path, screen):
    """Admit only complete, model-matched device evidence; never trust summary flags alone."""
    if screen.get('completed') is not True:
        raise ValueError('Incomplete parameter screen')
    admitted, rejected, names = [], [], set()
    gates = ['dcOutputLimitsPassed', 'additionalDcLimitsPassed',
             'switchingLimitsPassed', 'switchingConverged']
    for row in screen['candidates']:
        name = row['name']
        if name in names or Path(name).name != name or name in ('.', '..'):
            raise ValueError('Invalid or duplicate candidate name: ' + name)
        names.add(name)
        failed = [key for key in gates if row.get(key) is not True]
        if failed:
            rejected.append({'name': name, 'failedOrMissingChecks': failed})
            continue
        source = screen_path / name
        reports = {}
        for file, key in [('candidate.cir', 'modelSha256'), ('dc/assessment.json', 'dcReportSha256'),
                          ('validation/assessment.json', 'validationReportSha256'),
                          ('switching/report.json', 'switchingReportSha256')]:
            if sha(source/file) != row[key]:
                raise ValueError('Changed candidate evidence: ' + str(source/file))
            if file.endswith('.json'):
                reports[file.split('/')[0]] = json.loads((source/file).read_text())
        dc, validation, switch = (reports[key] for key in ['dc', 'validation', 'switching'])
        for label, report in reports.items():
            if report.get('completed') is not True:
                raise ValueError('Incomplete candidate evidence: ' + name + '/' + label)
        for identity in [dc.get('modelSha256'), validation.get('sources', {}).get('candidate.cir'),
                         switch.get('sources', {}).get('candidate.cir')]:
            if identity != row['modelSha256']:
                raise ValueError('Candidate model differs from device evidence: ' + name)
        if not all(value is True for value in [dc.get('outputLimitsPassed'), validation.get('limitsPassed'),
                                               switch.get('withinDelayLimits'), switch.get('numericallyConverged')]):
            raise ValueError('Candidate summary contradicts device evidence: ' + name)
        if ('switchingExitCode' in row and row['switchingExitCode'] != 0) or any(
                row.get('probes', {}).get(label, {}).get('exitCode', 0) != 0
                for label in ['dc', 'validation', 'switching']):
            raise ValueError('Candidate device probe failed: ' + name)
        admitted.append({'name': name, 'modelSha256': row['modelSha256'],
                         'deviceReports': {key: row[key] for key in
                                           ['dcReportSha256', 'validationReportSha256', 'switchingReportSha256']}})
    return admitted, rejected


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--screen', type=Path, required=True, help='Complete extracted parameter-screen capture directory')
    p.add_argument('--ngspice', default='ngspice')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--validate-screen-only', action='store_true', help='Verify device admission without running oscillators')
    args = p.parse_args()
    args.screen = args.screen.resolve();args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    screen_path = args.screen/'assessment.json';screen = json.loads(screen_path.read_text())
    report = {'completed': False, 'qualified': False, 'screenSha256': sha(screen_path),
              'mode': 'device-admission-only' if args.validate_screen_only else 'oscillator-screen',
              'sources': {p.name: sha(p) for p in [Path(__file__), HERE/'oscillator_probe.py']},
              'scope': 'Device-test survivors under the reference oscillator topology, fixed source component values and ideal supply ramp. No fitting to board frequency. Failure at coarse resolution is independently retried at finer resolution.',
              'candidates': []}
    try:
        admitted, report['rejectedCandidates'] = candidates(args.screen, screen)
        for row in admitted:
            model = args.screen/row['name']/'candidate.cir'
            candidate = dict(row, runs=[])
            report['candidates'].append(candidate)
            if args.validate_screen_only:
                continue
            for coarse, fine in [(2, 1), (1, .5)]:
                out = args.out/row['name']/f'{coarse}ns';out.parent.mkdir(exist_ok=True)
                log = out.with_suffix('.log')
                with log.open('w') as stream:
                    run = subprocess.run([sys.executable,str(HERE/'oscillator_probe.py'),'--gate-model',str(model),
                        '--ngspice',args.ngspice,'--steps-ns',str(coarse),str(fine),'--require-phase','--out',str(out)],
                        stdout=stream,stderr=subprocess.STDOUT,timeout=420)
                result_path = out/'report.json';result = json.loads(result_path.read_text())
                candidate['runs'].append({'coarseStepNs': coarse, 'fineStepNs': fine,
                    'passed': result['passed'], 'phaseQualified': result['phaseQualified'],
                    'exitCode': run.returncode, 'error': result.get('error'),
                    'reportSha256': sha(result_path), 'artifacts': {str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}})
            (args.out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
        report['completed'] = True
    finally:
        (args.out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
    print(args.out/'assessment.json')


if __name__ == '__main__':
    main()
