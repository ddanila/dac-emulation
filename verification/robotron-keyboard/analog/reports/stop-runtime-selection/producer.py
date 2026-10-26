#!/usr/bin/env python3
"""Capture stop-handle controls using a qualified display observer baseline."""
import argparse,json,os,shutil,subprocess,time
from pathlib import Path
from ttl7406_probe import sha
from ngspice_runtime import verify
from eval_cache_benchmark import external_dependencies,verify_dependencies
from bounded_log_process import run as producer
from compressed_output import capture
from audit_log import complete
from private_sync_family_board_review import function_symbols


def run(source,assessment,bridge,out):
    source=source.resolve();assessment=assessment.resolve();bridge=bridge.resolve();out=out.resolve()
    prior=json.loads(assessment.read_text());baseline=source/'off';base=json.loads((baseline/'run.json').read_text())
    if not prior.get('controlsPassed') or prior['receipts']['off']!=sha(baseline/'run.json') or not base['completed'] or base.get('error'):
        raise ValueError('Need completed, reviewed display-board controls')
    build=json.loads((bridge/'build.json').read_text())
    for name,h in build['outputs'].items():
        if sha(bridge/name)!=h:raise ValueError('Changed bridge build')
    if shutil.disk_usage(out.parent).free<4*1024**3:raise ValueError('Need 4 GiB free')
    verify(base['runtime']);verify_dependencies(base['externalDependencies'])
    def dep(name):
        matches=[d['path'] for d in base['externalDependencies'] if Path(d['path']).name==name]
        if len(matches)!=1:raise ValueError('Ambiguous runtime dependency')
        return matches[0]
    for name,h in base['inputs'].items():
        if sha(baseline/name)!=h:raise ValueError('Changed baseline input')
    out.mkdir(exist_ok=False);(out/'baseline').mkdir()
    for name in ('io.cir','io.vvp','s600.hex','run.json','waveform.raw.xz','ngspice.log.xz'):
        shutil.copyfile(baseline/name,out/'baseline'/name)
    shutil.copyfile(assessment,out/'baseline-assessment.json')
    shutil.copyfile(bridge/'build.json',out/'bridge-build.json')
    identities={}
    for module in (bridge/'ivlng.vpi',Path(dep('system.vpi'))):
        text=subprocess.check_output(['nm','-an',str(module)],text=True)
        (out/(module.name+'.nm')).write_text(text)
        identities[module.name]={'path':str(module),'sha256':sha(module),'symbols':function_symbols(text)}
    (out/'symbols.json').write_text(json.dumps(identities,indent=2)+'\n')
    deck=(baseline/'io.cir').read_text()
    for name in ('ivlng.so','ivlng.vpi'):
        old=dep(name)
        if deck.count(old)!=1:raise ValueError('Changed bridge placement')
        deck=deck.replace(old,str(bridge/name))
    for mode in ('off','observe','corrupt'):
        folder=out/mode;folder.mkdir();(folder/'io.cir').write_text(deck)
        for name in ('io.vvp','s600.hex'):shutil.copyfile(baseline/name,folder/name)
        env=dict(os.environ)
        for key in list(env):
            if key.startswith('ROBOTRON_'):del env[key]
        env.update(base['environment']);env['ROBOTRON_PRIVATE_DISPLAY']='stop-corrupt' if mode=='corrupt' else mode
        deps=external_dependencies(folder,{'deck':'io.cir','inputs':['io.vvp','s600.hex']})
        record={'qualified':False,'completed':False,'mode':mode,'runtime':base['runtime'],
                'environment':{k:v for k,v in env.items() if k.startswith('ROBOTRON_')},'externalDependencies':deps,
                'inputs':{n:sha(folder/n) for n in ('io.cir','io.vvp','s600.hex')},
                'baselineReceiptSha256':sha(out/'baseline/run.json'),'baselineAssessmentSha256':sha(out/'baseline-assessment.json'),
                'bridgeBuildSha256':sha(bridge/'build.json'),'producerSha256':sha(Path(__file__)),
                'symbolReceiptSha256':sha(out/'symbols.json'),'endSeconds':base['endSeconds'],'expectedExitCode':2 if mode=='corrupt' else 0}
        start=time.monotonic();(folder/'run.json').write_text(json.dumps(record,indent=2)+'\n')
        try:
            with capture(folder,['waveform.raw']) as storage:
                log=producer([base['runtime']['executable']['path'],'-n','-b','io.cir'],folder,env,folder/'ngspice.log.xz',900,
                             logical_limit=512*1024**2,compressed_limit=128*1024**2,min_free_bytes=512*1024**2)
            record.update(storage=storage,log=log,exitCode=log['exitCode'])
            verify(base['runtime']);verify_dependencies(deps)
            if any(sha(folder/n)!=h for n,h in record['inputs'].items()):raise ValueError('Changed capture inputs')
            if record['exitCode']!=record['expectedExitCode']:raise ValueError('Unexpected capture exit')
            if mode!='corrupt':record['summary']=complete(folder/'ngspice.log')
            record['completed']=True
        except Exception as exc:record['error']=str(exc)
        record['elapsedSeconds']=time.monotonic()-start
        (folder/'run.json').write_text(json.dumps(record,indent=2)+'\n');print(mode,record['completed'],record.get('error',''),flush=True)
        if not record['completed']:raise ValueError(record['error'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','assessment','bridge','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.source,a.assessment,a.bridge,a.out)
