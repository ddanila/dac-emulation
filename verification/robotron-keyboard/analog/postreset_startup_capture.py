#!/usr/bin/env python3
"""Run combined startup fixes against the unchanged retained post-reset fixture."""
import argparse
import json
import lzma
import math
from pathlib import Path
import resource
import shutil
import subprocess
import time
from audit_log import complete
from compressed_output import capture
from eval_cache_benchmark import external_dependencies, verify_dependencies
from ngspice_runtime import identify, verify
from ttl7406_probe import sha

MODES = {
    'off': {'ROBOTRON_HISTORY_INIT': 'off', 'ROBOTRON_STAGED_OUTPUT': 'off'},
    'combined': {'ROBOTRON_HISTORY_INIT': 'on', 'ROBOTRON_STAGED_OUTPUT': 'on'},
    'retry': {'ROBOTRON_HISTORY_INIT': 'on', 'ROBOTRON_STAGED_OUTPUT': 'on',
              'ROBOTRON_FORCE_NEWTON_REJECT': '1', 'ROBOTRON_NEWTON_REJECT_START': '0.0011'},
}


def validate_source(source):
    prior = json.loads((source / 'run.json').read_text())
    if prior.get('error') or prior.get('exitCode') != 0 or prior.get('timedOut') or prior.get('solverDiagnostic'):
        raise ValueError('Need completed post-reset control')
    inputs = dict(prior['inputs'], **{'io.cir': prior['deckSha256']})
    for name, digest in inputs.items():
        if sha(source / name) != digest:
            raise ValueError('Changed source input: ' + name)
    deck = (source / 'io.cir').read_text()
    if '\n.tran 25n 1.16e+06n\n' not in deck or deck.count('1000000n 0 1000001n 5') != 1:
        raise ValueError('Need unchanged 1.16-ms fixture with reset at 1 ms')
    if any(k.startswith('ROBOTRON_FORCE_') or k == 'ROBOTRON_NEWTON_REJECT_START' for k in prior['environment']):
        raise ValueError('Source must be unfaulted')
    return prior, inputs


def run(source, models, executable, out, mode, timeout=14400, log_bytes=1024**3):
    if not math.isfinite(timeout) or timeout <= 0 or type(log_bytes) is not int or log_bytes <= 0:
        raise ValueError('Need positive finite timeout and positive integer log cap')
    source, models, out = source.resolve(), models.resolve(), out.resolve()
    prior, inputs = validate_source(source)
    build = json.loads((models / 'build.json').read_text())
    for name, digest in build['outputs'].items():
        if sha(models / name) != digest:
            raise ValueError('Changed candidate model')
    runtime, env = identify(str(executable), str(models / 'spinit'))
    if runtime['executable'] != prior['runtime']['executable']:
        raise ValueError('Need same executable as disabled baseline')
    deps = external_dependencies(source, {'deck': 'io.cir', 'inputs': ['io.vvp', 's600.hex']})
    if deps != prior['externalDependencies']:
        raise ValueError('Changed fixture dependencies')
    for key in list(env):
        if key.startswith('ROBOTRON_'):
            del env[key]
    env.update(prior['environment'])
    env.update(MODES[mode])
    env['ROBOTRON_HISTORY_STATE'] = 'off'
    # Budget one complete capture plus an in-progress log and compression output.
    required = prior['storage']['waveform.raw']['bytes'] + 2 * log_bytes + 512 * 1024**2
    if shutil.disk_usage(out.parent).free < required:
        raise ValueError('Insufficient capture capacity')
    out.mkdir(exist_ok=False)
    for name in inputs:
        shutil.copyfile(source / name, out / name)
    result = {'qualified': False, 'completed': False, 'mode': mode, 'runtime': runtime,
              'inputs': inputs, 'externalDependencies': deps,
              'environment': {k: v for k, v in env.items() if k.startswith('ROBOTRON_')},
              'sourceRunSha256': sha(source / 'run.json'), 'candidateBuildSha256': sha(models / 'build.json'),
              'runnerSha256': sha(Path(__file__)), 'timeoutSeconds': timeout,
              'logLimitBytes': log_bytes, 'requiredFreeBytes': required,
              'scope': 'Unchanged 1.16-ms post-reset service fixture; external clock/reset, not full repeat or brownout.'}
    start = time.monotonic()
    (out / 'run.json').write_text(json.dumps(result, indent=2) + '\n')
    def cap_files():
        resource.setrlimit(resource.RLIMIT_FSIZE, (log_bytes, log_bytes))
    try:
        with capture(out, ['waveform.raw']) as storage:
            with (out / 'ngspice.log').open('wb') as log:
                process = subprocess.run([runtime['executable']['path'], '-n', '-b', 'io.cir'],
                    cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT,
                    timeout=timeout, preexec_fn=cap_files)
            result['exitCode'] = process.returncode
        result['storage'] = storage
        verify(runtime)
        verify_dependencies(deps)
        for name, digest in inputs.items():
            if sha(out / name) != digest:
                raise ValueError('Input changed during capture')
        if process.returncode:
            raise ValueError('Producer failed (file-size signal can indicate log cap)')
        summary = complete(out / 'ngspice.log')
        result['logSummary'] = summary
        if not summary['latchesMatch'] or len(summary['faults']) != (1 if mode == 'retry' else 0):
            raise ValueError('Unexpected bus continuation or retry count')
        result['completed'] = True
    except Exception as exc:
        result['error'] = str(exc)
        result['timedOut'] = isinstance(exc, subprocess.TimeoutExpired)
        raise
    finally:
        result['elapsedSeconds'] = time.monotonic() - start
        # Keep a bounded raw log even on failure; publish compressed copy only on success.
        log = out / 'ngspice.log'
        if result['completed']:
            result['logSha256'] = sha(log)
            with log.open('rb') as src, lzma.open(out / 'ngspice.log.xz', 'wb', preset=1) as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
            log.unlink()
        (out / 'run.json').write_text(json.dumps(result, indent=2) + '\n')
    print(out / 'run.json', flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'models', 'runtime', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--mode', choices=MODES, required=True)
    p.add_argument('--timeout', type=float, default=14400)
    p.add_argument('--log-bytes', type=int, default=1024**3)
    a = p.parse_args()
    run(a.source, a.models, a.runtime, a.out, a.mode, a.timeout, a.log_bytes)
