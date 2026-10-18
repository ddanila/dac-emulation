#!/usr/bin/env python3
"""Screen explicit high-current rolloff or sink-resistance assumptions against device holdouts."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from ls00_transistor_probe import sha

HERE = Path(__file__).resolve().parent


def candidate(source, scope, ikf, parameter='IKF'):
    if parameter not in {'IKF', 'RB', 'RC', 'RE'} or ikf <= 0:
        raise ValueError('Unsupported or nonpositive device parameter')
    match = re.search(r'(?im)^\.model LS00_NPN_ASSUMED NPN\(([^)]*)\)', source)
    if not match or re.search(r'\b'+parameter+r'\s*=', match[1], re.I):
        raise ValueError('Review base NPN model before assigning '+parameter)
    if scope == 'all':
        return source[:match.end()-1] + f' {parameter}={ikf:g}' + source[match.end()-1:]
    if scope != 'sink':
        raise ValueError('Unknown rolloff scope')
    old = 'Xsink y sinkbase g LS00_SCHOTTKY_NPN_ASSUMED'
    if source.count(old) != 1:
        raise ValueError('Review sink topology before substitution')
    return source.replace(old, 'Xsink y sinkbase g LS00_SINK_NPN_CANDIDATE') + (
        f'\n* Exploratory sink-only {parameter}; not measured process data.\n'
        '.subckt LS00_SINK_NPN_CANDIDATE c b e\n'
        'Qcore c b e LS00_SINK_ASSUMED\n'
        'Dantisat b c LS00_SCHOTTKY_ASSUMED\n.ends\n'
        f'.model LS00_SINK_ASSUMED NPN({match[1]} {parameter}={ikf:g})\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--ngspice', default='ngspice')
    p.add_argument('--parameter', choices=['IKF','RB','RC','RE'], default='IKF',
                   help='IKF: original all/sink rolloff grid; RB/RC/RE: sink-only resistance sensitivity')
    args = p.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = args.model.read_text()
    probes = [('dc', 'ls00_transistor_probe.py', 'assessment.json'),
              ('validation', 'ls00_validation_probe.py', 'assessment.json'),
              ('iv', 'ls00_iv_probe.py', 'assessment.json'),
              ('switching', 'gate_switching_probe.py', 'report.json')]
    sources = [Path(__file__), args.model, HERE/'ls00_transistor_probe.py',
               HERE/'failure_evidence.py', HERE/'ls00_validation_limits.json', HERE/'gate_switching_limits.json']
    sources += [HERE / script for _, script, _ in probes]
    report = {'completed': False, 'qualified': False,
              'scope': 'Exploratory forward-beta rolloff sensitivity at fixed BF and Schottky parameters. IKF is varied for all NPNs or the output sink alone. Values are hypotheses, not fitted or measured process bounds. No oscillator target or board-default change.',
              'grid': {'scope': ['all', 'sink'], 'ikfAmps': [.0001, .001, .01, .1]},
              'sources': {p.name: sha(p) for p in sources}, 'candidates': []}
    if args.parameter != 'IKF':
        report['scope'] = ('Exploratory sink-only '+args.parameter+' sensitivity with all other junction parameters fixed. '
                           'Decade-spaced resistance values are hypotheses, not measured or fitted process ranges. '
                           'The external Schottky clamp remains unchanged; internal clamp geometry is unqualified. '
                           'No oscillator target or board-default change.')
        report['grid'] = {'scope': ['sink'], 'ohms': [10,100,1000] if args.parameter=='RB' else [.1,1,10]}
        report['parameterReference'] = {'url': 'https://ngspice.sourceforge.io/docs/ngspice-manual.pdf',
            'section': 'BJT models (NPN/PNP)', 'scope': 'Parameter definitions only; not device values or calibration.'}
    report['parameter'] = args.parameter
    try:
        for scope in report['grid']['scope']:
            for ikf in report['grid']['ikfAmps' if args.parameter=='IKF' else 'ohms']:
                name = f'{scope}-{args.parameter.lower()}-{ikf:g}'
                folder = out/name
                folder.mkdir()
                model = folder/'candidate.cir'
                model.write_text(candidate(source, scope, ikf, args.parameter))
                item = {'name': name, 'scope': scope, ('ikfAmps' if args.parameter=='IKF' else 'resistanceOhms'): ikf,
                        'modelSha256': sha(model), 'probes': {}}
                report['candidates'].append(item)
                results = {}
                for label, script, filename in probes:
                    with (folder/(label+'-run.log')).open('w') as log:
                        run = subprocess.run([sys.executable, str(HERE/script), '--model', str(model),
                            '--ngspice', args.ngspice, '--out', str(folder/label)],
                            stdout=log, stderr=subprocess.STDOUT, timeout=600)
                    receipt = folder/label/filename
                    result = json.loads(receipt.read_text())
                    if not result.get('completed') or run.returncode not in (0, 1):
                        raise ValueError('Incomplete probe: '+name+'/'+label)
                    results[label] = result
                    item['probes'][label] = {'exitCode': run.returncode, 'reportSha256': sha(receipt)}
                item.update(dcOutputLimitsPassed=results['dc']['outputLimitsPassed'],
                    additionalDcLimitsPassed=results['validation']['limitsPassed'],
                    switchingConverged=results['switching']['numericallyConverged'],
                    switchingLimitsPassed=results['switching']['withinDelayLimits'],
                    dcReportSha256=item['probes']['dc']['reportSha256'],
                    validationReportSha256=item['probes']['validation']['reportSha256'],
                    switchingReportSha256=item['probes']['switching']['reportSha256'])
                item['deviceChecksPassed'] = (results['dc']['outputLimitsPassed'] and
                    results['validation']['limitsPassed'] and results['switching']['numericallyConverged'] and
                    results['switching']['withinDelayLimits'])
                item['lowOutputAt2VSourceAmps'] = next(point['outputSourceAmps'] for c in results['iv']['cases']
                    if c['name']=='low-threshold' for point in c['selectedPoints']
                    if abs(point['outputVolts'] - 2) < 1e-10)
                item['failedAdditionalDcConditions'] = [c['name'] for c in results['validation']['cases']
                                                        if not all(t['passed'] for t in c['checks'])]
                (out/'assessment.json').write_text(json.dumps(report, indent=2)+'\n')
        report['completed'] = True
    finally:
        (out/'assessment.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
