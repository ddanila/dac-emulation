#!/usr/bin/env python3
"""Capture a disabled control and a single forced Newton retry, without changing the circuit."""
import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import time
from compressed_output import capture
from eval_cache_benchmark import external_dependencies, verify_dependencies
from audit_log import scan
from ngspice_runtime import identify, verify
from ttl7406_probe import sha


def run(control, build, out, timeout, fault_start=None):
    if fault_start is not None and (isinstance(fault_start, bool) or not math.isfinite(fault_start) or fault_start < 0):
        raise ValueError("Retry start must be finite and nonnegative")
    if fault_start is not None:
        fault_start = float(fault_start)
    prior = json.loads((control/'run.json').read_text())
    if prior.get('error') or prior['exitCode'] != 0 or prior['timedOut'] or prior['solverDiagnostic']:
        raise ValueError('Need a complete bridge timing control')
    provenance = json.loads(build.read_text())
    if provenance['parentRuntimeSha256'] != prior['runtime']['executable']['sha256']:
        raise ValueError('Wrong parent runtime')
    runtime, env = identify(provenance['runtime']['path'], prior['runtime']['spinit']['path'])
    if runtime['executable']['sha256'] != provenance['runtime']['sha256']:
        raise ValueError('Changed diagnostic executable')
    for key in ('spinit', 'codeModels'):
        if runtime[key] != prior['runtime'][key]:
            raise ValueError('Changed runtime dependencies')
    here = Path(__file__).resolve().parent
    for name, key in (('ngspice-47-rollback-fault.patch', 'patchSha256'), ('rollback_fault.h', 'headerSha256')):
        if sha(here/'engine-patches'/name) != provenance[key]:
            raise ValueError('Changed fault injection source')
    deps = external_dependencies(control, {'deck':'io.cir', 'inputs':['io.vvp','s600.hex']})
    if deps != prior['externalDependencies']:
        raise ValueError('Changed live dependencies')
    for key in list(env):
        if key.startswith('ROBOTRON_'):
            del env[key]
    env.update(prior['environment'])
    if env.get('ROBOTRON_ROLLBACK_AUDIT') != '1' or any(k in env for k in ('ROBOTRON_FORCE_NEWTON_REJECT', 'ROBOTRON_NEWTON_REJECT_START')):
        raise ValueError('Need an unfaulted dispatch audit control')
    for name, expected in dict(prior['inputs'], **{'io.cir':prior['deckSha256']}).items():
        if sha(control/name) != expected:
            raise ValueError('Changed control input')
    out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, out/'capture-generator.py')
    shutil.copyfile(build, out/'build.json')
    for mode in ('off', 'on'):
        directory = out/mode
        directory.mkdir()
        for name in ('io.cir', 'io.vvp', 's600.hex', 'bridge.json'):
            shutil.copyfile(control/name, directory/name)
        env.pop('ROBOTRON_FORCE_NEWTON_REJECT', None)
        env.pop('ROBOTRON_NEWTON_REJECT_START', None)
        if mode == 'on':
            env['ROBOTRON_FORCE_NEWTON_REJECT'] = '1'
            if fault_start is not None:
                env['ROBOTRON_NEWTON_REJECT_START'] = repr(fault_start)
        result = {'runtime':runtime, 'externalDependencies':deps,
                  'environment':{k:v for k,v in env.items() if k.startswith('ROBOTRON_')},
                  'inputs':prior['inputs'], 'deckSha256':prior['deckSha256'],
                  'controlRunSha256':sha(control/'run.json'), 'buildSha256':sha(build),
                  'mode':mode, 'exitCode':None, 'timedOut':False, 'qualified':False}
        if fault_start is not None:
            result['faultStartSeconds'] = fault_start
        start = time.monotonic()
        try:
            with capture(directory, ['waveform.raw', 'ngspice.log']) as storage:
                with (directory/'ngspice.log').open('w') as log:
                    process = subprocess.run([runtime['executable']['path'], '-n', '-b', 'io.cir'],
                        cwd=directory, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
                result['exitCode'] = process.returncode
                if process.returncode:
                    raise ValueError('Newton retry producer failed')
            result['storage'] = storage
            verify(runtime)
            verify_dependencies(deps)
            summary = scan(directory/'ngspice.log')
            result['solverDiagnostic'] = summary['diagnostic']
            if summary['diagnostic'] or summary['sorry']:
                raise ValueError('Solver/HDL diagnostic')
            count = len(summary['faults'])
            if count != (1 if mode == 'on' else 0):
                raise ValueError('Unexpected number of injected retries')
        except Exception as exc:
            result['error'] = str(exc)
            result['timedOut'] = isinstance(exc, subprocess.TimeoutExpired)
            raise
        finally:
            result['elapsedSeconds'] = time.monotonic()-start
            (directory/'run.json').write_text(json.dumps(result, indent=2)+'\n')
            print(directory/'run.json', flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('control', 'build', 'out'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--timeout', type=float, default=3600)
    p.add_argument("--fault-start", type=float, help="First eligible retry time in seconds")
    a = p.parse_args()
    run(a.control, a.build, a.out, a.timeout, a.fault_start)
