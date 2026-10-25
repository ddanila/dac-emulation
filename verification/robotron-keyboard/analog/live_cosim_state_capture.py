#!/usr/bin/env python3
"""Capture a 20-us live observer control, not full-board qualification.

The input deck must be the retained post-reset service fixture. Reset is moved
to 1 us explicitly for this observer test; full scenario acceptance is separate.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from compressed_output import capture
from eval_cache_benchmark import external_dependencies, verify_dependencies
from ngspice_runtime import identify, verify
from ttl7406_probe import sha


def run(source,models,executable,out,timeout):
    source=source.resolve();models=models.resolve();out=out.resolve()
    prior=json.loads((source/'run.json').read_text())
    build=json.loads((models/'build.json').read_text())
    for name,digest in build['outputs'].items():
        if sha(models/name)!=digest:raise ValueError('Changed observer model')
    original=(source/'io.cir').read_text()
    if sha(source/'io.cir')!=prior['deckSha256']:raise ValueError('Changed source deck')
    for name in ('io.vvp','s600.hex'):
        if sha(source/name)!=prior['inputs'][name]:raise ValueError('Changed HDL/ROM input')
    reset='1000000n 0 1000001n 5'
    if original.count(reset)!=1 or len(re.findall(r'^\.tran .*$',original,re.M))!=1:
        raise ValueError('Unexpected source stimulus')
    deck=re.sub(r'^\.tran .*$', '.tran 25n 20000n',original.replace(reset,'1000n 0 1001n 5'),flags=re.M)
    runtime,env=identify(str(executable),str(models/'spinit'))
    for key in list(env):
        if key.startswith('ROBOTRON_'):del env[key]
    env.update(prior['environment']);env.pop('ROBOTRON_ROLLBACK_AUDIT',None)
    out.mkdir(parents=True,exist_ok=False)
    for mode in ('off','observe','check','corrupt'):
        folder=out/mode;folder.mkdir();(folder/'io.cir').write_text(deck)
        for name in ('io.vvp','s600.hex'):shutil.copyfile(source/name,folder/name)
        deps=external_dependencies(folder,{'deck':'io.cir','inputs':['io.vvp','s600.hex']})
        env['ROBOTRON_LIVE_STATE']=mode;start=time.monotonic()
        with capture(folder,['waveform.raw','ngspice.log']) as storage:
            with (folder/'ngspice.log').open('w') as log:
                process=subprocess.run([runtime['executable']['path'],'-n','-b','io.cir'],cwd=folder,
                                       env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
        verify(runtime);verify_dependencies(deps)
        receipt={'runtime':runtime,'environment':{k:v for k,v in env.items() if k.startswith('ROBOTRON_')},
                 'externalDependencies':deps,'sourceRunSha256':sha(source/'run.json'),
                 'observerBuildSha256':sha(models/'build.json'),'runner':sha(Path(__file__)),
                 'inputs':{n:sha(folder/n) for n in ('io.cir','io.vvp','s600.hex')},
                 'exitCode':process.returncode,'elapsedSeconds':time.monotonic()-start,'storage':storage,
                 'scope':'20-us observer control, reset moved to 1 us; not full scenario qualification.'}
        (folder/'run.json').write_text(json.dumps(receipt,indent=2)+'\n')
        if process.returncode!=(2 if mode=='corrupt' else 0):raise ValueError('Unexpected producer exit')
        print(mode,receipt['elapsedSeconds'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','models','runtime','out'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--timeout',type=float,default=600);a=p.parse_args()
    run(a.source,a.models,a.runtime,a.out,a.timeout)
