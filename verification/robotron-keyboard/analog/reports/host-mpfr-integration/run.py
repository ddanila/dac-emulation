#!/usr/bin/env python3
"""Controlled replay of MPFR integration arithmetic, with separately selected linear precision."""
import argparse
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys

ANALOG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ANALOG))
from analog_driver_replay import sha
from failure_evidence import solver_diagnostic
from ngspice_runtime import identify, verify
from integration_method_replay import prepare, refine_step


TRACE_COLUMNS = {'trace.txt': 3, 'host-trace.txt': 7, 'driver-trace.txt': 2, 'boundary-trace.txt': 22}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--step-divisor', type=int, choices=(1,2,4), default=1)
    parser.add_argument('--integration', choices=('original', 'gear', 'trap1'), default='original')
    parser.add_argument('--integration-arithmetic', choices=('off', '256'), required=True)
    parser.add_argument('--mode', choices=('off', '256', '512'), required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--build-provenance', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    source, out = args.source.resolve(), args.out.resolve()
    parent = json.loads((source/'report.json').read_text())
    if not parent.get('solverDiagnostic') or parent.get('completed') is not False:
        raise ValueError('Expected the failed analog-only reference-node replay')
    for name,digest in parent['artifacts'].items():
        if sha(source/name) != digest:
            raise ValueError('Source artifact differs: '+name)
    provenance = json.loads(args.build_provenance.read_text())
    patch = ANALOG/'engine-patches/ngspice-47-mpfr-integration.patch'
    header = ANALOG/'engine-patches/mpfr_integration.h'
    base = provenance['baseProvenance']
    if (provenance['patchSha256'] != sha(patch) or provenance['headerSha256'] != sha(header)
            or provenance['executableSha256'] != sha(args.runtime)):
        raise ValueError('Integration runtime build differs')
    if (base['patchSha256'] != sha(ANALOG/'engine-patches/ngspice-47-mpfr-linear.patch')
            or base['kernelSha256'] != sha(ANALOG/'engine-patches/mpfr_linear_solver.h')):
        raise ValueError('Linear runtime sources differ')
    for path, digest in base['libraries'].items():
        if sha(path) != digest:
            raise ValueError('Runtime library differs: '+path)
    runtime, env = identify(args.runtime, parent['ngspiceRuntime']['spinit']['path'])
    for field in ('spinit', 'codeModels'):
        if runtime[field] != parent['ngspiceRuntime'][field]:
            raise ValueError('Runtime initialization differs')
    env['ROBOTRON_MPFR_BITS'] = args.mode
    env['ROBOTRON_MPFR_INTEGRATION'] = args.integration_arithmetic
    out.mkdir(parents=True, exist_ok=False)
    deck, integration = prepare((source/'io.cir').read_text(), args.integration)
    deck, timestep = refine_step(deck, args.step_divisor)
    (out/'io.cir').write_text(deck)
    shutil.copyfile(args.build_provenance, out/'build-provenance.json')
    report = {'qualified': False, 'completed': False, 'scope': __doc__, 'mode': args.mode,
              'integrationArithmetic': args.integration_arithmetic,
              'integrationTransformerSha256': sha(ANALOG/'integration_method_replay.py'),
              'integration': integration, 'timestep': timestep, 'sourceDirectory': str(source), 'sourceReportSha256': sha(source/'report.json'),
              'ngspiceRuntime': runtime, 'stopSeconds': parent['stopSeconds'],
              'runnerSha256': sha(__file__), 'patchSha256': sha(patch),
              'deckEqual': sha(source/'io.cir') == sha(out/'io.cir'),
              'boundary': 'NIintegrate companion history, derivative and diagonal arithmetic use MPFR256 when enabled. Stored state histories, integration coefficients, nonlinear device evaluation, truncation and other stamping remain binary64. Real linear precision is selected separately. Circuit physics and acceptance tolerances are unchanged. Recorded stimulus replay is not coupled firmware qualification.'}

    try:
        verify(runtime)
        with (out/'ngspice.log').open('w') as log:
            process = subprocess.run([str(args.runtime.resolve()), '-n', '-b', 'io.cir'],
                                     cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=14400)
        verify(runtime)
        text = (out/'ngspice.log').read_text()
        observed = re.findall(r'^MPFR_DIAGNOSTIC bits=(-?\d+)$', text, re.M)
        if observed != ['0' if args.mode == 'off' else args.mode]:
            raise ValueError('Effective mode not confirmed')
        notices = text.count('MPFR_INTEGRATION enabled bits=256 states=binary64')
        if notices != (1 if args.integration_arithmetic == '256' else 0):
            raise ValueError('Integration arithmetic mode not confirmed')
        if args.integration != 'original':
            expected_method, expected_order = ('GEAR', '2') if args.integration == 'gear' else ('TRAPEZOIDAL', '1')
            if (re.findall(r'^Integration Method = (\w+)$', text, re.M) != [expected_method] or
                    re.findall(r'^MaxOrder = (\d+)$', text, re.M) != [expected_order]):
                raise ValueError('Effective integration method/order not confirmed')
            report['effectiveIntegrationVerified'] = True
        prefixes = ('TRUNC_AUDIT ', 'TRANSITION_AUDIT ', 'NODE_AUDIT ', 'INDUCTOR_AUDIT ', 'LINEAR_AUDIT ')
        messages = '\n'.join(line for line in text.splitlines() if not line.startswith(prefixes))
        report['solverDiagnostic'] = solver_diagnostic(messages)
        report['precisionGuardDiagnostics'] = [line for line in text.splitlines() if line.startswith('MPFR_DIAGNOSTIC rejected')]
        report['exitCode'] = process.returncode
        report['waveforms'] = {}
        for name, columns in TRACE_COLUMNS.items():
            previous, count = None, 0
            with (out/name).open() as stream:
                header = next(stream).split()
                if len(header) != columns:
                    raise ValueError('Unexpected waveform header: '+name)
                for line in stream:
                    row = list(map(float,line.split()))
                    if len(row) != columns or not all(map(math.isfinite,row)) or (previous is not None and row[0] < previous):
                        raise ValueError('Invalid waveform: '+name)
                    if previous is None and row[0] != 0:
                        raise ValueError('Missing time zero: '+name)
                    previous, count = row[0], count+1
            if not count:
                raise ValueError('Empty waveform: '+name)
            report['waveforms'][name] = {'rows': count, 'lastSampleSeconds': previous,
                                         'sourceIdentical': sha(out/name) == parent['artifacts'][name]}
        report['completed'] = (process.returncode == 0 and not report['solverDiagnostic'] and
                               not report['precisionGuardDiagnostics'] and
                               all(abs(v['lastSampleSeconds']-parent['stopSeconds']) < 1e-15
                                   for v in report['waveforms'].values()))
        if args.mode == 'off' and args.integration_arithmetic == 'off' and args.integration == 'original' and args.step_divisor == 1:
            report['reproducedControl'] = (report['solverDiagnostic'] == parent['solverDiagnostic'] and
                                            all(v['sourceIdentical'] for v in report['waveforms'].values()))
            if not report['reproducedControl']:
                raise ValueError('Disabled runtime control does not reproduce source')
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report['artifacts'] = {name: sha(out/name) for name in
                               ('io.cir', 'build-provenance.json', 'ngspice.log', *TRACE_COLUMNS) if (out/name).exists()}
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(out/'report.json')


if __name__ == '__main__':
    main()
