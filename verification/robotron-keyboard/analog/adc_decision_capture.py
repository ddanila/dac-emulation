#!/usr/bin/env python3
"""Capture bounded ADC decision traces alongside input/output delivery controls."""
import argparse
import json
from pathlib import Path
import shutil
import time
from audit_log import complete
from bounded_log_process import run as producer
from compressed_output import capture
from eval_cache_benchmark import external_dependencies, verify_dependencies
from ngspice_runtime import verify
from stop_board_capture import runtime_environment
from ttl7406_probe import sha


def run(source, candidate, out):
    source=source.resolve();candidate=candidate.resolve();out=out.resolve()
    base=json.loads((source/'run.json').read_text())
    if not base['completed'] or base.get('error') or base['exitCode']!=0 or base['endSeconds']!=20e-6:
        raise ValueError('Need completed bounded original-runtime board control')
    if any(k.startswith('ROBOTRON_FORCE_') or k in ('ROBOTRON_ABSOLUTE_TICKS','ROBOTRON_DRAIN_TICK','ROBOTRON_ADC_CROSSINGS') for k in base['environment']):
        raise ValueError('Unexpected baseline option')
    deck=(source/'io.cir').read_text()
    if deck.count('.tran 25n 20000n')!=1 or deck.count('1000n 0 1001n 5')!=1:
        raise ValueError('Changed bounded fixture')
    old=[d for d in base['externalDependencies'] if Path(d['path']).name=='ivlng.vpi']
    if len(old)!=1 or deck.count(old[0]['path'])!=1:raise ValueError('Ambiguous VPI dependency')
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed candidate build')
    for n,h in base['inputs'].items():
        if sha(source/n)!=h:raise ValueError('Changed baseline input')
    base_env=runtime_environment(base);verify_dependencies(base['externalDependencies'])
    if shutil.disk_usage(out.parent).free<2*1024**3:raise ValueError('Need 2 GiB free')
    out.mkdir(exist_ok=False);(out/'baseline').mkdir()
    for n in (*base['inputs'],'run.json','ngspice.log.xz','waveform.raw.xz'):shutil.copy2(source/n,out/'baseline'/n)
    shutil.copy2(candidate/'build.json',out/'candidate-build.json')
    deck=deck.replace(old[0]['path'],str(candidate/'ivlng.vpi'))
    for mode in ('off','tick','on','retry'):
        folder=out/mode;folder.mkdir();(folder/'io.cir').write_text(deck)
        for n in base['inputs']:
            if n!='io.cir':shutil.copy2(source/n,folder/n)
        env=base_env.copy();env['ROBOTRON_ADC_TRACE']='1'
        if mode!='off':env['ROBOTRON_ABSOLUTE_TICKS']='1'
        if mode in ('on','retry'):env['ROBOTRON_DRAIN_TICK']='1'
        if mode=='retry':env.update(ROBOTRON_FORCE_NEWTON_REJECT='1',ROBOTRON_NEWTON_REJECT_START='0.000005')
        deps=external_dependencies(folder,{'deck':'io.cir','inputs':['io.vvp','s600.hex']})
        record={'completed':False,'qualified':False,'mode':mode,'endSeconds':20e-6,
                'runtime':base['runtime'],'runtimeEnvironment':{'SPICE_SCRIPTS':env['SPICE_SCRIPTS']},
                'environment':{k:v for k,v in env.items() if k.startswith('ROBOTRON_')},'externalDependencies':deps,
                'inputs':{n:sha(folder/n) for n in base['inputs']},'baselineReceiptSha256':sha(out/'baseline/run.json'),
                'candidateBuildSha256':sha(out/'candidate-build.json'),'producerSha256':sha(Path(__file__))}
        start=time.monotonic();(folder/'run.json').write_text(json.dumps(record,indent=2)+'\n')
        try:
            with capture(folder,['waveform.raw']) as storage:
                log=producer([base['runtime']['executable']['path'],'-n','-b','io.cir'],folder,env,folder/'ngspice.log.xz',900,
                             logical_limit=256*1024**2,compressed_limit=64*1024**2,min_free_bytes=512*1024**2)
            record.update(storage=storage,log=log,exitCode=log['exitCode'])
            verify(base['runtime']);verify_dependencies(deps)
            if any(sha(folder/n)!=h for n,h in record['inputs'].items()):raise ValueError('Changed capture input')
            if log['exitCode']!=0:raise ValueError('Producer failed')
            record['summary']=complete(folder/'ngspice.log');record['completed']=True
        except Exception as exc:
            record['error']=str(exc);raise
        finally:
            record['elapsedSeconds']=time.monotonic()-start
            (folder/'run.json').write_text(json.dumps(record,indent=2)+'\n')
        print(mode,'completed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','candidate','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.source,a.candidate,a.out)
