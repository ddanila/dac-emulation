#!/usr/bin/env python3
"""Capture combined non-bridge signal payload faults with exact restored native state."""
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
from port_payload_recovery_gate import require
from private_sync_family_board_review import function_symbols


def runtime_environment(base):
    runtime,env=identify(base['runtime']['executable']['path'],base['runtime']['spinit']['path'])
    if runtime!=base['runtime']:raise ValueError('Changed selected XSPICE runtime')
    for key in list(env):
        if key.startswith('ROBOTRON_'):del env[key]
    env.update(base['environment'])
    return env


def run(source,assessment,bridge,icarus,out,startup_only=False):
    source=source.resolve();assessment=assessment.resolve();bridge=bridge.resolve();icarus=icarus.resolve();out=out.resolve()
    prior=json.loads(assessment.read_text());require(prior);baseline=source/'off';base=json.loads((baseline/'run.json').read_text())
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
    modes=('callback-list-user-corrupt', 'callback-list-object-corrupt', 'callback-list-function-corrupt', 'callback-list-link-corrupt', 'scope-signal-signed-corrupt', 'scope-signal-range-corrupt', 'scope-signal-node-corrupt', 'scope-signal-name-corrupt', 'scope-signal-cache-corrupt', 'scope-signal-scope-corrupt')
    for mode in (modes if startup_only else ('off','observe',*modes)):
        negative=mode not in ('off','observe')
        folder=out/mode;folder.mkdir();(folder/'io.cir').write_text(deck)
        shutil.copyfile(baseline/'s600.hex',folder/'s600.hex');(folder/'io.vvp').write_text(vvp)
        env=base_env.copy();env.update(ROBOTRON_DISPLAY_MODULE=str(module),ROBOTRON_PRIVATE_DISPLAY=mode)
        deps=external_dependencies(folder,{'deck':'io.cir','inputs':['io.vvp','s600.hex']})
        record={'captureTimeoutSeconds':3300,'startupOnly':startup_only,'compiledThreadProfile':profile,'threadContractSourceSha256':contract_sha,'qualified':False,'completed':False,'mode':mode,'runtime':base['runtime'],
                'environment':{k:v for k,v in env.items() if k.startswith('ROBOTRON_')},
                'runtimeEnvironment':{'SPICE_SCRIPTS':env['SPICE_SCRIPTS']},'externalDependencies':deps,
                'inputs':{n:sha(folder/n) for n in ('io.cir','io.vvp','s600.hex')},
                'baselineReceiptSha256':sha(out/'baseline/run.json'),'baselineAssessmentSha256':sha(out/'baseline-assessment.json'),
                'bridgeBuildSha256':sha(bridge/'build.json'),'icarusBuildSha256':sha(icarus/'build.json'),'producerSha256':sha(Path(__file__)),
                'symbolReceiptSha256':sha(out/'symbols.json'),'endSeconds':base['endSeconds'],'expectedExitCode':2 if negative else 0}
        start=time.monotonic();(folder/'run.json').write_text(json.dumps(record,indent=2)+'\n')
        try:
            with capture(folder,['waveform.raw']) as storage:
                log=producer([base['runtime']['executable']['path'],'-n','-b','io.cir'],folder,env,folder/'ngspice.log.xz',3300,
                             logical_limit=72*1024**3,compressed_limit=256*1024**2,min_free_bytes=512*1024**2)
            record.update(storage=storage,log=log,exitCode=log['exitCode'])
            verify(base['runtime']);verify_dependencies(deps)
            if sha(Path(board_thread_contract.__file__))!=contract_sha:raise ValueError('Changed compiled thread contract')
            if any(sha(folder/n)!=h for n,h in record['inputs'].items()):raise ValueError('Changed capture inputs')
            if record['exitCode']!=record['expectedExitCode']:raise ValueError('Unexpected capture exit')
            if not negative:record['summary']=complete(folder/'ngspice.log')
            record['completed']=True
        except Exception as exc:record['error']=str(exc)
        record['elapsedSeconds']=time.monotonic()-start
        (folder/'run.json').write_text(json.dumps(record,indent=2)+'\n');print(mode,record['completed'],record.get('error',''),flush=True)
        if not record['completed']:raise ValueError(record['error'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','assessment','bridge','icarus','out'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--startup-only',action='store_true')
    a=p.parse_args();run(a.source,a.assessment,a.bridge,a.icarus,a.out,a.startup_only)
