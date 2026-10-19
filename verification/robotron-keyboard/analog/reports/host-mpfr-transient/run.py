#!/usr/bin/env python3
"""Controlled transient replay with experimental MPFR real linear solving."""
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


TRACE_COLUMNS = {'trace.txt': 3, 'host-trace.txt': 7, 'driver-trace.txt': 2, 'boundary-trace.txt': 22}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
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
    patch = ANALOG/'engine-patches/ngspice-47-mpfr-linear.patch'
    if provenance['patchSha256'] != sha(patch) or provenance['executableSha256'] != sha(args.runtime):
        raise ValueError('Runtime build differs')
    kernel = ANALOG/'engine-patches/mpfr_linear_solver.h'
    if provenance['kernelSha256'] != sha(kernel):
        raise ValueError('Runtime kernel differs')
    for path, digest in provenance['libraries'].items():
        if sha(path) != digest:
            raise ValueError('Runtime library differs: '+path)
    runtime, env = identify(args.runtime, parent['ngspiceRuntime']['spinit']['path'])
    for field in ('spinit', 'codeModels'):
        if runtime[field] != parent['ngspiceRuntime'][field]:
            raise ValueError('Runtime initialization differs')
    env['ROBOTRON_MPFR_BITS'] = args.mode
    out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(source/'io.cir', out/'io.cir')
    shutil.copyfile(args.build_provenance, out/'build-provenance.json')
    report = {'qualified': False, 'completed': False, 'scope': __doc__, 'mode': args.mode,
              'sourceDirectory': str(source), 'sourceReportSha256': sha(source/'report.json'),
              'ngspiceRuntime': runtime, 'stopSeconds': parent['stopSeconds'],
              'runnerSha256': sha(__file__), 'patchSha256': sha(patch),
              'deckEqual': sha(source/'io.cir') == sha(out/'io.cir'),
              'boundary': 'Identical analog-only replay circuit and sampled diagnostic stimulus. Active modes solve each real Newton system in MPFR from the beginning, preserving binary64 stamping, diagonal Gmin loading and returned physical coordinates before Newton checks. Default circuit and nonlinear/temporal tolerances are unchanged. Not a coupled firmware run or physical qualification.'}
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
        if args.mode == 'off':
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
