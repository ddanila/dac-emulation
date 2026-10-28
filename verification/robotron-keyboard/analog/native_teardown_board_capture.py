#!/usr/bin/env python3
"""Capture full board recovery and native teardown with an ASAN runtime."""
import argparse,json,shutil,subprocess,time
from pathlib import Path
from ttl7406_probe import sha
from ngspice_runtime import identify,verify
from eval_cache_benchmark import external_dependencies,verify_dependencies
from bounded_log_process import run as producer
from compressed_output import capture
from fast_audit_log import complete
from board_thread_contract import compiled_contract
import board_thread_contract
from private_sync_family_board_review import function_symbols


def runtime_environment(base):
    runtime,env=identify(base['runtime']['executable']['path'],base['runtime']['spinit']['path'])
    if runtime!=base['runtime']:raise ValueError('Changed selected XSPICE runtime')
    for key in list(env):
        if key.startswith('ROBOTRON_'):del env[key]
    env.update(base['environment'])
    sanitizer=Path(subprocess.check_output(['c++','-print-file-name=libclang_rt.asan_osx_dynamic.dylib'],text=True).strip()).resolve(strict=True)
    env.update(DYLD_INSERT_LIBRARIES=str(sanitizer),ASAN_OPTIONS='halt_on_error=1:abort_on_error=0:detect_leaks=0',ROBOTRON_TEARDOWN_TRACE='1')
    return env


def run(source,assessment,bridge,icarus,out):
    source=source.resolve();assessment=assessment.resolve();bridge=bridge.resolve();icarus=icarus.resolve();out=out.resolve()
    prior=json.loads(assessment.read_text());baseline=source/'off';base=json.loads((baseline/'run.json').read_text())
    profile=compiled_contract((baseline/'io.vvp').read_text());contract_sha=sha(Path(board_thread_contract.__file__))
    if not prior.get('controlsPassed') or prior['receipts']['off']!=sha(baseline/'run.json') or not base['completed'] or base.get('error'):
        raise ValueError('Need completed, reviewed callback-list-board controls')
    build=json.loads((bridge/'build.json').read_text())
    for name,h in build['outputs'].items():
        if sha(bridge/name)!=h:raise ValueError('Changed bridge build')
    icarus_build=json.loads((icarus/'build.json').read_text())
    for name,h in icarus_build['outputs'].items():
        if sha(icarus/name)!=h:raise ValueError('Changed Icarus build')
    if shutil.disk_usage(out.parent).free<4*1024**3:raise ValueError('Need 4 GiB free')
    base_env=runtime_environment(base);verify_dependencies(base['externalDependencies'])
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
    shutil.copyfile(icarus/'build.json',out/'icarus-build.json')
    identities={}
    for module in (bridge/'ivlng.vpi',icarus/'vpi/system.vpi'):
        text=subprocess.check_output(['nm','-an',str(module)],text=True)
        (out/(module.name+'.nm')).write_text(text)
        identities[module.name]={'path':str(module),'sha256':sha(module),'symbols':function_symbols(text)}
    (out/'symbols.json').write_text(json.dumps(identities,indent=2)+'\n')
    deck=(baseline/'io.cir').read_text()
    for name in ('ivlng.so','ivlng.vpi'):
        old=dep(name)
        if deck.count(old)!=1:raise ValueError('Changed bridge placement')
        deck=deck.replace(old,str(bridge/name))
    old=dep('libvvp.so')
    if deck.count(old)!=1:raise ValueError('Changed libvvp placement')
    deck=deck.replace(old,str(icarus/'vvp/libvvp.so'))
    original_vvp=(baseline/'io.vvp').read_text();module=icarus/'vpi/system.vpi'
    marker=':vpi_module "'+dep('system.vpi')+'";'
    if original_vvp.count(marker)!=1:raise ValueError('Changed system module placement')
    vvp=original_vvp.replace(marker,':vpi_module "'+str(module)+'";')
    modes=['parameter-lifecycle-'+kind for kind in ('binary','real','string')]
    for mode in modes:
        negative=mode not in ('off','observe')
        folder=out/mode;folder.mkdir();(folder/'io.cir').write_text(deck)
        shutil.copyfile(baseline/'s600.hex',folder/'s600.hex');(folder/'io.vvp').write_text(vvp)
        env=base_env.copy();env.update(ROBOTRON_DISPLAY_MODULE=str(module),ROBOTRON_PRIVATE_DISPLAY=mode,ROBOTRON_PARAMETER_CLASS='none')
        deps=external_dependencies(folder,{'deck':'io.cir','inputs':['io.vvp','s600.hex']})
        sanitizer=Path(env['DYLD_INSERT_LIBRARIES']);deps.append(dict(path=str(sanitizer),sha256=sha(sanitizer)))
        record={'captureTimeoutSeconds':3300,'selectedBoundaries':True,'compiledThreadProfile':profile,'threadContractSourceSha256':contract_sha,'qualified':False,'completed':False,'mode':mode,'runtime':base['runtime'],
                'environment':{k:v for k,v in env.items() if k.startswith('ROBOTRON_')},
                'runtimeEnvironment':{k:env[k] for k in ('SPICE_SCRIPTS','ASAN_OPTIONS','DYLD_INSERT_LIBRARIES')},'externalDependencies':deps,
                'inputs':{n:sha(folder/n) for n in ('io.cir','io.vvp','s600.hex')},
                'baselineReceiptSha256':sha(out/'baseline/run.json'),'baselineAssessmentSha256':sha(out/'baseline-assessment.json'),
                'bridgeBuildSha256':sha(bridge/'build.json'),'icarusBuildSha256':sha(icarus/'build.json'),'producerSha256':sha(Path(__file__)),
                'symbolReceiptSha256':sha(out/'symbols.json'),'endSeconds':base['endSeconds'],'expectedExitCode':0}
        start=time.monotonic();(folder/'run.json').write_text(json.dumps(record,indent=2)+'\n')
        try:
            with capture(folder,['waveform.raw']) as storage:
                log=producer([base['runtime']['executable']['path'],'-n','-b','io.cir'],folder,env,folder/'ngspice.log.xz',3300,
                             logical_limit=4*1024**3,compressed_limit=256*1024**2,min_free_bytes=512*1024**2)
            record.update(storage=storage,log=log,exitCode=log['exitCode'])
            verify(base['runtime']);verify_dependencies(deps)
            if sha(Path(board_thread_contract.__file__))!=contract_sha:raise ValueError('Changed compiled thread contract')
            if any(sha(folder/n)!=h for n,h in record['inputs'].items()):raise ValueError('Changed capture inputs')
            if record['exitCode']!=record['expectedExitCode']:raise ValueError('Unexpected capture exit')
            record['summary']=complete(folder/'ngspice.log')
            record['completed']=True
        except Exception as exc:record['error']=str(exc)
        record['elapsedSeconds']=time.monotonic()-start
        (folder/'run.json').write_text(json.dumps(record,indent=2)+'\n');print(mode,record['completed'],record.get('error',''),flush=True)
        if not record['completed']:raise ValueError(record['error'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','assessment','bridge','icarus','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.source,a.assessment,a.bridge,a.icarus,a.out)
