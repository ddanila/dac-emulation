#!/usr/bin/env python3
"""Capture bounded allocator-dependence controls for output-history initialization."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import subprocess
import time
from compressed_output import capture
from eval_cache_benchmark import external_dependencies, verify_dependencies
from ngspice_runtime import identify, verify
from ttl7406_probe import sha
VARIANTS={'off':{'ROBOTRON_HISTORY_INIT':'off'},
          'dirty-one':{'ROBOTRON_HISTORY_INIT':'off','ROBOTRON_HISTORY_SEED':'one'},
          'init':{'ROBOTRON_HISTORY_INIT':'on'},
          'init-zero':{'ROBOTRON_HISTORY_INIT':'on','ROBOTRON_HISTORY_SEED':'zero'},
          'init-one':{'ROBOTRON_HISTORY_INIT':'on','ROBOTRON_HISTORY_SEED':'one'}}


def run(source,models,executable,out):
    source=source.resolve();models=models.resolve();out=out.resolve();runner=sha(Path(__file__))
    prior=json.loads((source/'run.json').read_text());build=json.loads((models/'build.json').read_text())
    for name,digest in build['outputs'].items():
        if sha(models/name)!=digest:raise ValueError('Changed candidate model')
    for name,digest in prior['inputs'].items():
        if sha(source/name)!=digest:raise ValueError('Changed source fixture')
    if '\n.tran 25n 20000n\n' not in (source/'io.cir').read_text():raise ValueError('Expected bounded observer fixture')
    runtime,env=identify(str(executable),str(models/'spinit'))
    for key in list(env):
        if key.startswith('ROBOTRON_'):del env[key]
    env.update(prior['environment']);out.mkdir(parents=True,exist_ok=False)
    def producer(mode):
        folder=out/mode;folder.mkdir()
        for name in prior['inputs']:shutil.copyfile(source/name,folder/name)
        deps=external_dependencies(folder,{'deck':'io.cir','inputs':['io.vvp','s600.hex']})
        environment=dict(env,**VARIANTS[mode]);start=time.monotonic()
        with capture(folder,['waveform.raw','ngspice.log']) as storage:
            with (folder/'ngspice.log').open('w') as log:
                process=subprocess.run([runtime['executable']['path'],'-n','-b','io.cir'],cwd=folder,
                                       env=environment,stdout=log,stderr=subprocess.STDOUT,timeout=600)
        verify(runtime);verify_dependencies(deps)
        inputs={n:sha(folder/n) for n in prior['inputs']}
        if inputs!=prior['inputs']:raise ValueError('Changed capture input')
        receipt={'runtime':runtime,'environment':{k:v for k,v in environment.items() if k.startswith('ROBOTRON_')},
                 'externalDependencies':deps,'sourceRunSha256':sha(source/'run.json'),'candidateBuildSha256':sha(models/'build.json'),
                 'runnerSha256':runner,'inputs':inputs,'exitCode':process.returncode,'elapsedSeconds':time.monotonic()-start,'storage':storage}
        (folder/'run.json').write_text(json.dumps(receipt,indent=2)+'\n');print(mode,receipt['elapsedSeconds'],process.returncode,flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(producer,VARIANTS))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','models','runtime','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.source,a.models,a.runtime,a.out)
