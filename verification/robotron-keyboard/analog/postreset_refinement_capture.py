#!/usr/bin/env python3
"""Retain finer post-reset captures, changing only the completed control's step."""
import argparse
import json
import math
from pathlib import Path
import re
import shutil
import time
from bounded_log_process import run as producer
from compressed_output import capture
from eval_cache_benchmark import external_dependencies, verify_dependencies
from ngspice_runtime import identify, verify
from postreset_startup_capture import validate_source
from postreset_startup_review import inspect_log, validate_receipt
from ttl7406_probe import sha

STEPS = (12.5, 6.25)
SOURCES = ('postreset_refinement_capture.py', 'bounded_log_process.py', 'compressed_output.py',
           'postreset_startup_capture.py', 'postreset_startup_review.py')
ORIGINAL_TRAN = '\n.tran 25n 1.16e+06n\n'


def refined_deck(deck, step):
    if step not in STEPS or deck.count(ORIGINAL_TRAN) != 1 or len(re.findall(r'^\s*\.tran\b',deck,re.M|re.I)) != 1:
        raise ValueError('Need a prescribed halving of the complete 25-ns post-reset fixture')
    if deck.count('1000000n 0 1000001n 5') != 1:
        raise ValueError('Changed reset stimulus')
    return deck.replace(ORIGINAL_TRAN, f'\n.tran {step:g}n 1.16e+06n\n')


def validate_control(source, coarse, models, executable):
    prior, original_inputs = validate_source(source)
    control = json.loads((coarse/'run.json').read_text())
    build = json.loads((models/'build.json').read_text())
    for name,digest in build['outputs'].items():
        if sha(models/name) != digest: raise ValueError('Changed candidate model')
    runtime, env = identify(str(executable),str(models/'spinit'))
    validate_receipt(control,prior,original_inputs,'combined',runtime,sha(models/'build.json'),sha(source/'run.json'))
    if runtime['executable'] != prior['runtime']['executable']:
        raise ValueError('Changed post-reset executable')
    for name,digest in original_inputs.items():
        if sha(coarse/name) != digest: raise ValueError('Changed completed control input')
    deps = external_dependencies(coarse,{'deck':'io.cir','inputs':['io.vvp','s600.hex']})
    if deps != control['externalDependencies']: raise ValueError('Changed control dependencies')
    for key in list(env):
        if key.startswith('ROBOTRON_'): del env[key]
    env.update(control['environment'])
    return control, original_inputs, runtime, env, deps


def run(a):
    if not math.isfinite(a.timeout) or a.timeout<=0: raise ValueError('Need positive finite timeout')
    for value in (a.logical_log_bytes,a.compressed_log_bytes):
        if type(value) is not int or value<=0: raise ValueError('Need positive log caps')
    source,coarse,models,out = (p.resolve() for p in (a.source,a.coarse,a.models,a.out))
    control,original_inputs,runtime,env,deps = validate_control(source,coarse,models,a.runtime)
    deck = refined_deck((coarse/'io.cir').read_text(),a.step_ns)
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
            'environment':control['environment'],'externalDependencies':deps,
            'sourceRunSha256':sha(source/'run.json'),'coarseRunSha256':sha(coarse/'run.json'),
            'candidateBuildSha256':sha(models/'build.json'),
            'sources':{n:sha(Path(__file__).with_name(n)) for n in SOURCES},
            'limits':{'timeoutSeconds':a.timeout,'logicalLogBytes':a.logical_log_bytes,
                      'compressedLogBytes':a.compressed_log_bytes,'freeSpaceReserveBytes':reserve},
            'requiredFreeBytes':required,
            'scope':'Complete 1.16-ms post-reset window; only the 25-ns transient step changes. Reference external clock/reset, not full repeat, startup or brownout.'}
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
    p.add_argument('--step-ns',type=float,choices=STEPS,required=True)
    p.add_argument('--timeout',type=float,default=28800)
    p.add_argument('--logical-log-bytes',type=int,default=4*1024**3)
    p.add_argument('--compressed-log-bytes',type=int,default=512*1024**2)
    run(p.parse_args())
