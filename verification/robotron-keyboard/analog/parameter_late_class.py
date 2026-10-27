#!/usr/bin/env python3
"""Reject late unsupported parameter subclasses before inventory output."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from parameter_payload import parse
HERE=Path(__file__).resolve().parent
FAMILIES=('binary','real','string')


def review(root):
    receipt=json.loads((root/'run.json').read_text());initial={}
    if set(receipt['runs'])!={f+'-'+m for f in FAMILIES for m in ('baseline','disabled','enabled')}:raise ValueError('Missing late class comparisons')
    for kind,family in enumerate(FAMILIES):
        for mode in ('baseline','disabled','enabled'):
            key=family+'-'+mode;r=receipt['runs'][key]
            if r['exitCode'] or r['family']!=family or r['observer']!=mode or (root/(key+'.stderr')).read_text():raise ValueError('Native late class failed')
            lines=(root/(key+'.stdout')).read_text().splitlines();i=0;events=[]
            while i<len(lines):
                line=lines[i];i+=1
                if line.startswith('IMAGE '):
                    start=i
                    while i<len(lines) and lines[i]!='IMAGE_END':i+=1
                    if i==len(lines) or line!='IMAGE initial' or mode!='enabled' or family in initial:raise ValueError('Invalid initial class image')
                    initial[family]=parse(lines[start:i]);i+=1
                else:events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
            expected=[]
            for n in (1,2):
                expected.append(f'ROUND {n}')
                if mode!='baseline':
                    if n==1:expected.append(f'ADDED {kind}')
                    expected.append(f'VALUE {n} {kind} UNCHANGED')
                    if mode=='enabled':expected.append(f'REFUSED {n}')
            if events!=expected+['CONTINUE 3 123456789abcdef01234 1.5','finish']:raise ValueError('Missing late refusal or changed continuation')
    if set(initial)!=set(FAMILIES):raise ValueError('Missing initial inventories')
    for state in initial.values():
        if state['tick']!=1000 or sorted(p['kind'] for p in state['rows'])!=['binary','binary','real','string']:raise ValueError('Wrong initial admitted population')
    return dict(qualified=False,controlsPassed=True,lateUnsupportedFamilies=list(FAMILIES),zeroOutputRefusals=6,initialSupportedParameters=4,originalHdlContinuationExactlyEqual=True,
        scope='Native hidden-state subclasses are allocated after a successful full inventory through normal scope attachment. Exact class registration rejects each; both immediate and later inventories refuse with negative status and zero output. Base VPI values remain readable, further diagnostic allocation refuses, and original/disabled/enabled HDL continuation matches. Destruction/reuse, compact refusal transport and operational board integration remain unqualified.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/parameter_late_class.{ext}',out/f'probe.{ext}')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-ginterconnect','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'probe.vvp',*modules.glob('*.vpi')]};runs={}
    for family in ('binary','real','string'):
        for mode in ('baseline','disabled','enabled'):
            lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
            env=dict(os.environ,ROBOTRON_PARAMETER_CLASS='none',K7658_PARAMETER_KIND=str(('binary','real','string').index(family)),K7658_PORT_PAYLOAD='on' if mode=='enabled' else 'off');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
            cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
            (out/(family+'-'+mode+'.stdout')).write_text(r.stdout);(out/(family+'-'+mode+'.stderr')).write_text(r.stderr);runs[family+'-'+mode]=dict(exitCode=r.returncode,command=cmd,library=str(lib),family=family,observer=mode);r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Dependencies changed')
    (out/'build.json').write_text(json.dumps(build,indent=2)+'\n')
    (out/'run.json').write_text(json.dumps(dict(runs=runs,commands=commands,dependencies=pins),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.candidate,a.baseline,a.modules,a.out)
