#!/usr/bin/env python3
"""Capture full-window ADC crossing controls against the combined-fix baseline."""
import argparse
import json
import math
from pathlib import Path
import shutil
import time
from bounded_log_process import run as producer
from compressed_output import capture
from eval_cache_benchmark import verify_dependencies
from ngspice_runtime import verify
from postreset_startup_review import inspect_log
from ttl7406_probe import sha

from postreset_refinement_capture import validate_control, refined_deck

STEPS = (25, 12.5, 6.25)
SOURCES = ('postreset_adc_capture.py', 'postreset_refinement_capture.py',
           'bounded_log_process.py', 'compressed_output.py',
           'postreset_startup_capture.py', 'postreset_startup_review.py')


def experiment(deck, environment, step, crossing):
    if step not in STEPS or crossing not in ('off', 'on'):
        raise ValueError('Need prescribed timestep and ADC mode')
    if 'ROBOTRON_ADC_CROSSINGS' in environment:
        raise ValueError('Baseline must use its original default ADC behavior')
    # Validate the same complete reset/window contract even at the coarse step.
    refined_deck(deck, 12.5)
    result = deck if step == 25 else refined_deck(deck, step)
    env = dict(environment)
    if crossing == 'on': env['ROBOTRON_ADC_CROSSINGS'] = '1'
    return result, env


def run(a):
    if not math.isfinite(a.timeout) or a.timeout<=0: raise ValueError('Need positive finite timeout')
    for value in (a.logical_log_bytes,a.compressed_log_bytes):
        if type(value) is not int or value<=0: raise ValueError('Need positive log caps')
    source,coarse,models,out = (p.resolve() for p in (a.source,a.coarse,a.models,a.out))
    control,original_inputs,runtime,env,deps = validate_control(source,coarse,models,a.runtime)
    deck, experiment_env = experiment((coarse/'io.cir').read_text(),control['environment'],a.step_ns,a.adc_crossings)
    env.update(experiment_env)
    reserve=512*1024**2
    required=3*control['storage']['waveform.raw']['bytes']+a.compressed_log_bytes+reserve
    if shutil.disk_usage(out.parent).free<required: raise ValueError('Insufficient capture capacity')
    out.mkdir(exist_ok=False)
    for name in original_inputs:
        if name!='io.cir': shutil.copyfile(coarse/name,out/name)
    (out/'io.cir').write_text(deck);shutil.copyfile(models/'build.json',out/'build.json')
    inputs={name:sha(out/name) for name in original_inputs}
    result={'completed':False,'qualified':False,'stepNs':a.step_ns,'endSeconds':.00116,
            'runtime':runtime,'inputs':inputs,'originalInputs':original_inputs,
            'environment':experiment_env,'adcCrossings':a.adc_crossings,'externalDependencies':deps,
            'sourceRunSha256':sha(source/'run.json'),'coarseRunSha256':sha(coarse/'run.json'),
            'candidateBuildSha256':sha(models/'build.json'),
            'sources':{n:sha(Path(__file__).with_name(n)) for n in SOURCES},
            'limits':{'timeoutSeconds':a.timeout,'logicalLogBytes':a.logical_log_bytes,
                      'compressedLogBytes':a.compressed_log_bytes,'freeSpaceReserveBytes':reserve},
            'requiredFreeBytes':required,
            'scope':'Complete 1.16-ms post-reset window; only transient step and opt-in ADC crossing localization may change. Reference external clock/reset, not full repeat, startup or brownout.'}
    start=time.monotonic();(out/'run.json').write_text(json.dumps(result,indent=2)+'\n')
    try:
        with capture(out,['waveform.raw']) as storage:
            log=producer([runtime['executable']['path'],'-n','-b','io.cir'],out,env,out/'ngspice.log.xz',a.timeout,
                         logical_limit=a.logical_log_bytes,compressed_limit=a.compressed_log_bytes,min_free_bytes=reserve)
        result.update(storage=storage,log=log,exitCode=log['exitCode'])
        verify(runtime);verify_dependencies(deps)
        if any(sha(out/name)!=digest for name,digest in inputs.items()): raise ValueError('Changed capture input')
        if sha(models/'build.json')!=result['candidateBuildSha256']: raise ValueError('Changed model build')
        if log['exitCode']!=0: raise ValueError('Producer failed')
        result['logSummary']=inspect_log(out/'ngspice.log','combined')
        result['completed']=True
    except Exception as exc:
        result['error']=str(exc);raise
    finally:
        result['elapsedSeconds']=time.monotonic()-start
        (out/'run.json').write_text(json.dumps(result,indent=2)+'\n')
    print(out/'run.json',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','coarse','models','runtime','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--adc-crossings',choices=('off','on'),required=True)
    p.add_argument('--step-ns',type=float,choices=STEPS,required=True)
    p.add_argument('--timeout',type=float,default=28800)
    p.add_argument('--logical-log-bytes',type=int,default=4*1024**3)
    p.add_argument('--compressed-log-bytes',type=int,default=512*1024**2)
    run(p.parse_args())
