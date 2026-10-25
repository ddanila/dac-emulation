#!/usr/bin/env python3
"""Capture bridge request/actual-time logging against a complete dispatch control."""
import argparse
import json
import re
from pathlib import Path
import shutil
import subprocess
import time
from compressed_output import capture
from eval_cache_benchmark import external_dependencies, verify_dependencies
from audit_log import scan
from ngspice_runtime import identify, verify
from ttl7406_probe import sha


def substitute_vpi(deck, old, new):
    token='"'+old+'"'
    lines=[line for line in deck.splitlines() if token in line]
    if deck.count(token)!=1 or not re.fullmatch(r'\+\s+lib_args=\["[^"]+"\s+'+re.escape(token)+r'\]',lines[0]):
        raise ValueError('Expected one VPI path in the bridge lib_args')
    return deck.replace(token,'"'+new+'"')


def run(control, base_bridge, audit_bridge, out, timeout):
    prior=json.loads((control/'run.json').read_text())
    if prior['exitCode']!=0 or prior['timedOut'] or prior.get('error') or prior['solverDiagnostic']:
        raise ValueError('Need a complete dispatch control')
    base=json.loads(base_bridge.read_text());audit=json.loads(audit_bridge.read_text())
    if audit['audit']['baseBridgeSha256']!=sha(base_bridge):
        raise ValueError('Audit bridge has different parent')
    for name,item in audit['libraries'].items():
        if sha(Path(item['path']))!=item['sha256']:raise ValueError('Changed bridge library')
        if name!='vpi' and item!=base['libraries'][name]:raise ValueError('Changed non-VPI bridge dependency')
    if sha(audit_bridge.parent/'vpi.c')!=audit['audit']['sourceSha256']:
        raise ValueError('Changed audit source')
    runtime,env=identify(prior['runtime']['executable']['path'],prior['runtime']['spinit']['path'])
    if runtime!=prior['runtime']:raise ValueError('Changed runtime')
    for key in list(env):
        if key.startswith('ROBOTRON_'):del env[key]
    env.update(prior['environment'])
    if env.get('ROBOTRON_ROLLBACK_AUDIT')!='1':raise ValueError('Need enabled dispatch audit control')
    deck=(control/'io.cir').read_text()
    if sha(control/'io.cir')!=prior['deckSha256'] or 'run waveform.raw' not in deck:
        raise ValueError('Changed direct-output control')
    old=base['libraries']['vpi']['path'];new=audit['libraries']['vpi']['path']
    changed_deck=substitute_vpi(deck,old,new)
    if sha(control/'io.vvp')!=prior['inputs']['io.vvp'] or sha(control/'s600.hex')!=prior['inputs']['s600.hex']:
        raise ValueError('Changed baseline inputs')
    out.mkdir(parents=True,exist_ok=False)
    (out/'io.cir').write_text(changed_deck)
    shutil.copyfile(control/'io.vvp',out/'io.vvp')
    shutil.copyfile(control/'s600.hex',out/'s600.hex')
    shutil.copyfile(__file__,out/'capture-generator.py')
    shutil.copyfile(audit_bridge,out/'bridge.json')
    deps=external_dependencies(out,{'deck':'io.cir','inputs':['io.vvp','s600.hex']})
    expected=[audit['libraries']['vpi'] if d==base['libraries']['vpi'] else d for d in prior['externalDependencies']]
    if sorted(deps,key=lambda d:d['path'])!=sorted(expected,key=lambda d:d['path']):
        raise ValueError('Unintended external dependency change')
    result={'runtime':runtime,'externalDependencies':deps,'environment':prior['environment'],
            'deckSha256':sha(out/'io.cir'),'inputs':{n:sha(out/n) for n in ('io.vvp','s600.hex')},
            'controlRunSha256':sha(control/'run.json'),'bridgeReceiptSha256':sha(audit_bridge),
            'baseBridgeReceiptSha256':sha(base_bridge),'exitCode':None,'timedOut':False,'qualified':False}
    start=time.monotonic()
    try:
        with capture(out,['waveform.raw','ngspice.log']) as storage:
            with (out/'ngspice.log').open('w') as log:
                process=subprocess.run([runtime['executable']['path'],'-n','-b','io.cir'],cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
            result['exitCode']=process.returncode
            if process.returncode:raise ValueError('Bridge audit producer failed')
        result['storage']=storage
        verify(runtime);verify_dependencies(deps)
        summary=scan(out/'ngspice.log');result['solverDiagnostic']=summary['diagnostic']
        if summary['diagnostic'] or summary['sorry']:raise ValueError('Solver/HDL diagnostic')
        if not summary['advances']:raise ValueError('No bridge time records')
    except Exception as exc:
        result['error']=str(exc);result['timedOut']=isinstance(exc,subprocess.TimeoutExpired)
        raise
    finally:
        result['elapsedSeconds']=time.monotonic()-start
        (out/'run.json').write_text(json.dumps(result,indent=2)+'\n')
        print(out/'run.json',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('control','base-bridge','audit-bridge','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--timeout',type=float,default=3600);a=p.parse_args()
    run(a.control,a.base_bridge,a.audit_bridge,a.out,a.timeout)
