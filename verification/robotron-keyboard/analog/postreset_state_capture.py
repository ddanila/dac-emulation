#!/usr/bin/env python3
"""Capture full post-reset state controls with bounded compressed logs."""
import argparse
import json
from pathlib import Path
import shutil
import time
from bounded_log_process import run as producer
from circuit_output_review import runtime_summary
from compressed_output import capture
from eval_cache_benchmark import external_dependencies, verify_dependencies
from ngspice_runtime import identify, verify
from postreset_startup_capture import validate_source
from ttl7406_probe import sha

VARIANTS = {
    'off': {'ROBOTRON_HISTORY_STATE': 'off'},
    'check': {'ROBOTRON_HISTORY_STATE': 'check'},
    'immediate': {'ROBOTRON_HISTORY_STATE': 'corrupt', 'ROBOTRON_HISTORY_CORRUPT_AFTER': '0'},
    'delayed': {'ROBOTRON_HISTORY_STATE': 'corrupt', 'ROBOTRON_HISTORY_CORRUPT_AFTER': '0.0011'},
}
for environment in VARIANTS.values():
    environment.update(ROBOTRON_HISTORY_INIT='on', ROBOTRON_STAGED_OUTPUT='on')


def run(a):
    source, models, out = a.source.resolve(), a.models.resolve(), a.out.resolve()
    prior, inputs = validate_source(source)
    build = json.loads((models / 'build.json').read_text())
    for name, digest in build['outputs'].items():
        if sha(models / name) != digest: raise ValueError('Changed candidate model')
    runtime, env = identify(str(a.runtime), str(models / 'spinit'))
    if runtime['executable'] != prior['runtime']['executable']:
        raise ValueError('Changed executable from post-reset baseline')
    deps = external_dependencies(source, {'deck': 'io.cir', 'inputs': ['io.vvp', 's600.hex']})
    if deps != prior['externalDependencies']: raise ValueError('Changed fixture dependencies')
    if shutil.disk_usage(out.parent).free < a.compressed_log_bytes + 2*prior['storage']['waveform.raw']['bytes'] + 512*1024**2:
        raise ValueError('Insufficient capture capacity')
    for key in list(env):
        if key.startswith('ROBOTRON_'): del env[key]
    env.update(prior['environment']); env.update(VARIANTS[a.mode])
    out.mkdir(exist_ok=False)
    for name in inputs: shutil.copyfile(source / name, out / name)
    shutil.copyfile(models / 'build.json', out / 'build.json')
    expected_exit = 2 if a.mode in ('immediate', 'delayed') else 0
    result = {'qualified': False, 'completed': False, 'mode': a.mode, 'runtime': runtime,
              'inputs': inputs, 'externalDependencies': deps,
              'environment': {k:v for k,v in env.items() if k.startswith('ROBOTRON_')},
              'expectedExitCode': expected_exit, 'sourceRunSha256': sha(source/'run.json'),
              'candidateBuildSha256': sha(models/'build.json'),
              'sources': {n:sha(Path(__file__).with_name(n)) for n in
                          ('postreset_state_capture.py','bounded_log_process.py','postreset_startup_capture.py','compressed_output.py')},
              'limits': {'logicalLogBytes': a.logical_log_bytes, 'compressedLogBytes': a.compressed_log_bytes,
                         'timeoutSeconds': a.timeout, 'freeSpaceReserveBytes': 512*1024**2},
              'scope': 'Unchanged 1.16-ms post-reset fixture. Negative controls intentionally abort; not full repeat, startup or supply recovery.'}
    start = time.monotonic(); (out/'run.json').write_text(json.dumps(result,indent=2)+'\n')
    try:
        with capture(out, ['waveform.raw']) as storage:
            log = producer([runtime['executable']['path'],'-n','-b','io.cir'],out,env,out/'ngspice.log.xz',a.timeout,
                logical_limit=a.logical_log_bytes,compressed_limit=a.compressed_log_bytes,min_free_bytes=512*1024**2)
        result.update(storage=storage, log=log, exitCode=log['exitCode'])
        verify(runtime); verify_dependencies(deps)
        for name, digest in inputs.items():
            if sha(out/name)!=digest: raise ValueError('Input changed during capture')
        if log['exitCode'] != expected_exit: raise ValueError('Unexpected producer exit')
        if expected_exit == 0:
            summary = runtime_summary(out/'ngspice.log')
            result['logSummary'] = summary
            if summary['count'] is None or summary['diagnostic'] or summary['sorry']:
                raise ValueError('Missing positive completion or solver failure')
        # Detailed state, fault timing, endpoint and waveform validation is a
        # separate review; expected process termination cannot qualify the board.
        result['completed'] = True
    except Exception as exc:
        result['error'] = str(exc); raise
    finally:
        result['elapsedSeconds'] = time.monotonic()-start
        (out/'run.json').write_text(json.dumps(result,indent=2)+'\n')
    print(out/'run.json',flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source','models','runtime','out'): p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--mode',choices=VARIANTS,required=True)
    p.add_argument('--timeout',type=float,default=14400)
    p.add_argument('--logical-log-bytes',type=int,default=64*1024**3)
    p.add_argument('--compressed-log-bytes',type=int,default=2*1024**3)
    run(p.parse_args())
