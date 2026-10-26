#!/usr/bin/env python3
"""Compare original, disabled and enabled tick conversion on the real bridge."""
import argparse
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def cases():
    for base in (10000,1071501280,1096019098):
        center=base*1e-12
        for label,target in [('below',math.nextafter(center,0)),('exact',center),
                             ('above',math.nextafter(center,math.inf)),
                             ('quarter',center+.25e-12),('threequarter',center+.75e-12)]:
            for path,prior in [('direct',0.),('staged',target-4.0900804e-12),('near',target-.25e-12)]:
                yield f'{base}-{label}-{path}',target,prior


def assess(root):
    receipt=json.loads((root/'run.json').read_text());results=[]
    for name,target,prior in cases():
        outputs={}
        for mode in ('baseline','off','on'):
            item=receipt['runs'][name+'/'+mode]
            if item['exitCode']!=0 or item['target']!=target.hex() or item['prior']!=prior.hex():
                raise ValueError('Failed or changed input case')
            log=root/item['log']
            if sha(log)!=item['sha256']:raise ValueError('Changed probe log')
            text=log.read_text()
            if 'Error:' in text or 'Invalid absolute' in text:raise ValueError('Runtime diagnostic')
            ticks=re.findall(r'^INPUT_TICK (\d+) 1$',text,re.M)
            if len(ticks)!=1:raise ValueError('Missing unique observed rising input')
            outputs[mode]={'tick':int(ticks[0]),'records':re.findall(r'^(?:INPUT_TICK|OUTPUT|RETURN|APPLY) .+$',text,re.M)}
        if outputs['baseline']!=outputs['off']:raise ValueError('Disabled candidate changed behavior')
        expected=int(Fraction(target)/Fraction(1e-12))
        if outputs['on']['tick']!=expected:raise ValueError('Absolute target contract failed')
        results.append({'case':name,'target':target.hex(),'prior':prior.hex(),'expectedTick':expected,
                        'baselineTick':outputs['baseline']['tick'],'candidateTick':outputs['on']['tick']})
    witnesses=[r for r in results if r['baselineTick']!=r['expectedTick']]
    if not witnesses:raise ValueError('No baseline conversion defect reproduced')
    return {'qualified':False,'controlsPassed':True,'disabledExactlyMatchesBaseline':True,
            'candidateMatchesExactRationalFloor':True,'cases':results,'baselineFailures':witnesses,
            'scope':'Direct real-shim Normal step/input/step contract; no analog circuit. Targets straddle binary64 and fractional HDL-tick boundaries with different preceding advances.',
            'notEstablished':['ADC threshold localization and full board convergence','Candidate rollback and full-window firmware controls','Other HDL runtimes, enormous tick counts and physical timing']}


def run(a):
    root=a.out.resolve();root.mkdir(exist_ok=False)
    board=json.loads(a.board_receipt.read_text())
    libs={Path(d['path']).name:d for d in board['externalDependencies'] if Path(d['path']).name in ('ivlng.so','ivlng.vpi','libvvp.so')}
    candidate=json.loads((a.candidate/'build.json').read_text())
    if sha(a.candidate/'ivlng.vpi')!=candidate['outputs']['ivlng.vpi']:raise ValueError('Changed candidate build')
    for d in libs.values():
        if sha(Path(d['path']))!=d['sha256']:raise ValueError('Changed baseline library')
    include=a.source/'src/include'
    commands=[['cc','-std=c11','-I'+str(include),str(HERE/'fixtures/input_tick_probe.c'),'-o',str(root/'probe')],
              [a.iverilog,'-g2012','-s','input_tick_probe','-o',str(root/'probe.vvp'),str(HERE/'fixtures/input_tick_probe.v')]]
    for command in commands:subprocess.run(command,check=True)
    modules=re.findall(r'^:vpi_module "([^"]+)";', (root/'probe.vvp').read_text(),re.M)
    dependencies={str(Path(p).resolve()):sha(Path(p)) for p in modules}
    dependencies.update({d['path']:d['sha256'] for d in libs.values()})
    dependencies[str((a.candidate/'ivlng.vpi').resolve())]=sha(a.candidate/'ivlng.vpi')
    receipt={'qualified':False,'commands':commands,'boardReceiptSha256':sha(a.board_receipt),
             'dependencies':dependencies,'sources':{str(p):sha(p) for p in (Path(__file__),HERE/'fixtures/input_tick_probe.c',HERE/'fixtures/input_tick_probe.v',include/'ngspice/cmtypes.h',include/'ngspice/cosim.h')},
             'probeSha256':sha(root/'probe'),'vvpSha256':sha(root/'probe.vvp'),'runs':{}}
    shutil.copy2(a.candidate/'build.json',root/'candidate-build.json')
    for name,target,prior in cases():
        for mode in ('baseline','off','on'):
            env={k:v for k,v in os.environ.items() if not k.startswith('ROBOTRON_')}
            if mode=='on':env['ROBOTRON_ABSOLUTE_TICKS']='1'
            vpi=libs['ivlng.vpi']['path'] if mode=='baseline' else str((a.candidate/'ivlng.vpi').resolve())
            command=[str(root/'probe'),libs['ivlng.so']['path'],libs['libvvp.so']['path'],vpi,str(root/'probe.vvp'),target.hex(),prior.hex()]
            path=root/(name+'-'+mode+'.log')
            with path.open('w') as log:
                proc=subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=10)
            if path.stat().st_size>1024**2:raise ValueError('Unexpected probe log volume')
            receipt['runs'][name+'/'+mode]={'target':target.hex(),'prior':prior.hex(),'exitCode':proc.returncode,'log':path.name,'sha256':sha(path),'environment':{'ROBOTRON_ABSOLUTE_TICKS':'1'} if mode=='on' else {},'command':command}
            (root/'run.json').write_text(json.dumps(receipt,indent=2)+'\n')
    for p,h in dependencies.items():
        if sha(Path(p))!=h:raise ValueError('Dependency changed during probe')
    (root/'assessment.json').write_text(json.dumps(assess(root),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('source','candidate','board-receipt','out'):p.add_argument('--'+n,type=Path)
    p.add_argument('--iverilog',default='iverilog');a=p.parse_args()
    if a.check:
        if assess(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Input-tick controls verified; board qualification remains open.')
    else:
        if not all((a.source,a.candidate,a.board_receipt,a.out)):p.error('Need source, candidate, board receipt and fresh output')
        run(a)
