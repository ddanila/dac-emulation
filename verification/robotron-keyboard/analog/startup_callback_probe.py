#!/usr/bin/env python3
"""Validate startup callback lifetimes and restored faults on the real runtime."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def review(root):
    expected=['CALLBACK 0 0 C','CALLBACK 0 0 A']
    output=None;faults=observations=0
    for mode in ('baseline','disabled','enabled','corrupt'):
        if (root/(mode+'.stderr')).read_text():raise ValueError('Simulator diagnostic')
        lines=(root/(mode+'.stdout')).read_text().splitlines()
        actual=[l for l in lines if not l.startswith('VS_')]
        if output is None:output=actual
        if output!=actual or [l for l in actual if l.startswith('CALLBACK ')]!=expected:
            raise ValueError('Changed callback timing, ordering or cancellation')
        sequence=[('API '+l.split()[1]) if l.startswith('VS_API ') else l for l in lines if l.startswith(('VS_API ','CALLBACK '))]
        if sequence!=['API 0','API 1',expected[0],'API 2',expected[1],'API 3','API 4']:
            raise ValueError('Observation moved outside callback continuation')
        stages=[];identities=None
        for line in lines:
            if line.startswith('VS_API '):
                if line.split()!=['VS_API',str(len(stages)),str(int(mode!='baseline'))]:raise ValueError('Wrong API/stage')
                stages.append({'links':[],'faults':[]})
            elif line.startswith('VS_LINK '):
                a=list(map(int,line.split()[1:]))
                if not stages or len(a)!=3 or a[:2]!=[len(stages)-1,len(stages[-1]['links'])]:raise ValueError('Wrong identity order')
                stages[-1]['links'].append(a[2])
            elif line.startswith('VS_FAULT '):
                a=list(map(int,line.split()[1:]))
                if not stages or len(a)!=5 or a[0]!=len(stages)-1 or a[3:]!=[1,1]:raise ValueError('Undetected or unrestored fault')
                stages[-1]['faults'].append(a[1:3])
            elif line.startswith('VS_'):raise ValueError('Unknown observer record')
        if len(stages)!=5:raise ValueError('Missing registration, cancellation, execution or destruction observation')
        for index,stage in enumerate(stages):
            if mode in ('baseline','disabled'):
                if stage['links'] or stage['faults']:raise ValueError('Disabled observer emitted state')
                continue
            if index==0:
                identities=stage['links']
                if len(identities)!=3 or min(identities)<1 or len(set(identities))!=3:raise ValueError('Missing distinct lifetimes')
            alive=((0,1,2),(0,2),(0,2),(0,),())[index]
            wanted=[identity if i in alive else 0 for i,identity in enumerate(identities)]
            if stage['links']!=wanted:raise ValueError('Wrong pending/active/canceled/destroyed lifetime')
            required=[[i,f] for i in alive for f in range(4)] if mode=='corrupt' else []
            if stage['faults']!=required:raise ValueError('Missing relationship fault')
            observations+=len(stage['links']);faults+=len(required)
    return {'completed':True,'qualified':False,'timestampedCallbackOutputExactlyEqual':True,
            'callbackIdentityObservations':observations,'restoredFaults':faults,
            'fields':['user_data','function','time pointer','next pointer'],
            'scope':'Startup callbacks before dispatch and while active outside the pending list; non-head cancellation, post-return destruction, unknown handles and mismatched identities. Original, disabled, observed and restored-fault continuation agrees.',
            'notEstablished':['Paused board integration and startup/recovery rejection controls','Other simulator callback families','Stack, freed-storage equivalence or general rollback']}


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('c','v'):shutil.copy2(HERE/f'fixtures/startup_callback_probe.{ext}',out/f'probe.{ext}')
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')]]
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands.append(['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')])
    for cmd in commands:subprocess.run(cmd,check=True)
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]
    pins={str(p):sha(p) for p in paths};runs={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on'),('corrupt',candidate/'vvp/libvvp.so','corrupt')]:
        env=dict(os.environ,K7658_START_PROBE=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp']
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        runs[name]={'command':cmd,'exitCode':r.returncode,'library':str(lib),'mode':mode};r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during controls')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('startup_callback_probe.py','fixtures/startup_callback_probe.c','fixtures/startup_callback_probe.v')}},indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Startup callback controls verified; board and general rollback coverage remain open.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need all runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
