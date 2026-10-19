#!/usr/bin/env python3
"""Reproduce a failed analog-only capture with the logging-only audit runtime."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ANALOG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ANALOG))
from analog_driver_replay import sha
from failure_evidence import solver_diagnostic
from ngspice_runtime import identify, verify


def summarize(log):
    trials = []
    for line in log.splitlines():
        if line.startswith('TRUNC_AUDIT solver '):
            fields = dict(item.split('=', 1) for item in line.split()[2:])
            trials.append({'timeSeconds': float.fromhex(fields['time']),
                           'deltaSeconds': float.fromhex(fields['delta']),
                           'newtonResult': int(fields['result']), 'order': int(fields['order']),
                           'nodes': {}, 'inductors': [], 'truncation': None})
        elif trials and line.startswith('NODE_AUDIT '):
            fields = dict(item.split('=', 1) for item in line.split()[1:])
            trials[-1]['nodes'][fields['name']] = {
                key: float.fromhex(fields[key]) for key in ('rhs', 'oldrhs')}
        elif trials and line.startswith('INDUCTOR_AUDIT '):
            fields = dict(item.split('=', 1) for item in line.split()[1:])
            trials[-1]['inductors'].append({key: value if key == 'name' else
                int(value) if key in ('state', 'order') else float.fromhex(value)
                for key, value in fields.items()})
        elif trials and line.startswith('TRUNC_AUDIT step '):
            fields = dict(item.split('=', 1) for item in line.split()[2:])
            trials[-1]['truncation'] = {key: int(value) if key in ('result', 'order', 'newtrunc')
                                      else float.fromhex(value) for key, value in fields.items()}
    if not trials:
        raise ValueError('No audited solver trials')
    return {'trialCount': len(trials),
            'newtonFailureCount': sum(trial['newtonResult'] != 0 for trial in trials),
            'lastTrials': trials[-3:],
            'boundary': 'Internal trial states, including rejected and nonconverged states; not physical measurements or accepted waveform samples.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--build-provenance', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    source, out = args.source.resolve(), args.out.resolve()
    parent = json.loads((source/'report.json').read_text())
    if parent.get('completed') is not False or not parent.get('solverDiagnostic'):
        raise ValueError('Expected a completed failed diagnostic capture')
    for name, digest in parent['artifacts'].items():
        if sha(source/name) != digest:
            raise ValueError('Source artifact differs: '+name)
    provenance = json.loads(args.build_provenance.read_text())
    patch = ANALOG/'engine-patches/ngspice-47-linear-state-audit.patch'
    if provenance['executableSha256'] != sha(args.runtime) or provenance['patchSha256'] != sha(patch):
        raise ValueError('Audit runtime provenance differs')
    runtime, env = identify(args.runtime, parent['ngspiceRuntime']['spinit']['path'])
    for field in ('spinit', 'codeModels'):
        if runtime[field] != parent['ngspiceRuntime'][field]:
            raise ValueError('Initialization or code models differ')
    out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(source/'io.cir', out/'io.cir')
    shutil.copyfile(args.build_provenance, out/'build-provenance.json')
    report = {'qualified': False, 'reproducedEvidence': False,
              'scope': __doc__, 'sourceDirectory': str(source),
              'sourceReportSha256': sha(source/'report.json'),
              'runnerSha256': sha(__file__), 'ngspiceRuntime': runtime,
              'patchSha256': sha(patch), 'deckEqual': sha(out/'io.cir') == sha(source/'io.cir')}
    try:
        verify(runtime)
        with (out/'ngspice.log').open('w') as log:
            process = subprocess.run([str(args.runtime.resolve()), '-n', '-b', 'io.cir'],
                                     cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
        verify(runtime)
        log_text = (out/'ngspice.log').read_text()
        (out/'state-review.json').write_text(json.dumps(summarize(log_text), indent=2)+'\n')
        report['exitCode'] = process.returncode
        audit_prefixes = ('TRUNC_AUDIT ', 'TRANSITION_AUDIT ', 'NODE_AUDIT ', 'INDUCTOR_AUDIT ', 'LINEAR_AUDIT ')
        # The generic failure scanner treats the audit label 'error' as an error.
        # Filter only our explicit instrumentation records, retaining all simulator messages.
        diagnostic_lines = [line for line in log_text.splitlines()
                            if not line.startswith(audit_prefixes)]
        report['solverDiagnostic'] = solver_diagnostic('\n'.join(diagnostic_lines))
        report['filteredInstrumentationLines'] = len(log_text.splitlines()) - len(diagnostic_lines)
        report['diagnosticEqual'] = report['solverDiagnostic'] == parent['solverDiagnostic']
        report['waveformsEqual'] = {name: sha(out/name) == parent['artifacts'][name] for name in
                                   ('trace.txt', 'host-trace.txt', 'driver-trace.txt', 'boundary-trace.txt')}
        report['nodeAuditRecords'] = sum(line.startswith('NODE_AUDIT ') for line in log_text.splitlines())
        report['inductorAuditRecords'] = sum(line.startswith('INDUCTOR_AUDIT ') for line in log_text.splitlines())
        report['reproducedEvidence'] = (report['deckEqual'] and report['diagnosticEqual'] and
                                       all(report['waveformsEqual'].values()) and report['nodeAuditRecords'] > 0)
        if not report['reproducedEvidence']:
            raise ValueError('Audit did not reproduce the original capture')
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report['artifacts'] = {name: sha(out/name) for name in
                               ('io.cir', 'ngspice.log', 'build-provenance.json', 'state-review.json', 'trace.txt',
                                'host-trace.txt', 'driver-trace.txt', 'boundary-trace.txt') if (out/name).exists()}
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(out/'report.json')


if __name__ == '__main__':
    main()
