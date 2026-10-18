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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--screen', type=Path, required=True, help='Complete extracted parameter-screen capture directory')
    p.add_argument('--ngspice', default='ngspice')
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    args.screen = args.screen.resolve();args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    screen_path = args.screen/'assessment.json';screen = json.loads(screen_path.read_text())
    if not screen['completed']:p.error('Incomplete parameter screen')
    report = {'completed': False, 'qualified': False, 'screenSha256': sha(screen_path),
              'sources': {p.name: sha(p) for p in [Path(__file__), HERE/'oscillator_probe.py']},
              'scope': 'Device-test survivors under the reference oscillator topology, fixed source component values and ideal supply ramp. No fitting to board frequency. Failure at coarse resolution is independently retried at finer resolution.',
              'candidates': []}
    try:
        for row in screen['candidates']:
            if not all(row.get(k) for k in ['additionalDcLimitsPassed','switchingLimitsPassed','switchingConverged']):continue
            source = args.screen/row['name'];model = source/'candidate.cir'
            for file, key in [('candidate.cir','modelSha256'), ('dc/assessment.json','dcReportSha256'),
                              ('validation/assessment.json','validationReportSha256'),('switching/report.json','switchingReportSha256')]:
                if sha(source/file)!=row[key]:raise ValueError('Changed candidate evidence: '+str(source/file))
            candidate = {'name': row['name'], 'modelSha256': sha(model), 'runs': []}
            report['candidates'].append(candidate)
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
