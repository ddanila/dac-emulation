#!/usr/bin/env python3
"""Exercise exact parameter registration admission through native factory subclasses."""
import argparse,json,os,platform,shutil,subprocess,copy
from pathlib import Path
from ttl7406_probe import sha
from parameter_payload import parse
HERE=Path(__file__).resolve().parent
FAMILIES=('none','binary','string','real')


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={}
    for family in FAMILIES:
        for mode in ('baseline','disabled','enabled'):
            key=family+'-'+mode;r=receipt['runs'][key]
            if r['exitCode'] or r['family']!=family or r['observer']!=mode or (root/(key+'.stderr')).read_text():raise ValueError('Failed native parameter class control')
            lines=(root/(key+'.stdout')).read_text().splitlines();events=[];i=0
            while i<len(lines):
                line=lines[i];i+=1
                if line.startswith('IMAGE '):
                    round_id=int(line.split()[1]);start=i
                    while i<len(lines) and lines[i]!='IMAGE_END':i+=1
                    if i==len(lines) or family!='none' or mode!='enabled' or round_id in images:raise ValueError('Invalid parameter class image')
                    images[round_id]=parse(lines[start:i]);i+=1
                else:events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
            expected=[]
            for n in (1,2):
                expected.extend([f'ROUND {n}','VALUES 3 123456789abcdef01234 1.5 24 412042'])
                if mode!='baseline':expected.append(f'CLASS {family} '+str(2 if family=='binary' else 0 if family=='none' else 1))
                if mode=='enabled' and family!='none':expected.append(f'REFUSED {n} {family}')
            if events!=expected+['CONTINUE 3 123456789abcdef01234 1.5','finish']:raise ValueError('Missing class/refusal or changed VPI/HDL continuation')
    if set(images)!={1,2}:raise ValueError('Missing supported parameter controls')
    first=images[1];second=images[2]
    if first['tick']!=1000 or second['tick']!=2000 or sorted(p['kind'] for p in first['rows'])!=['binary','binary','real','string']:raise ValueError('Wrong supported parameter population')
    expected=copy.deepcopy(first);expected['tick']=2000
    if expected!=second:raise ValueError('Supported parameter state changed')
    return dict(qualified=False,controlsPassed=True,unsupportedFamilies=['binarySubclass','stringSubclass','realSubclass'],zeroOutputRefusals=6,supportedParameterCount=4,originalVpiAndHdlContinuationExactlyEqual=True,
        scope='Native factory subclasses are rejected before class-specific registration reads. Independent scope ownership retains the unsupported objects, causing whole inventory refusal before output. Two rounds per family preserve base VPI values and original/disabled/enabled HDL continuation. Exact supported classes retain full payload inventory. Does not qualify parameter deletion/reuse or operational board integration.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/parameter_class.{ext}',out/f'probe.{ext}')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-ginterconnect','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'probe.vvp',*modules.glob('*.vpi')]};runs={}
    for family in ('none','binary','string','real'):
        for mode in ('baseline','disabled','enabled'):
            lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
            env=dict(os.environ,ROBOTRON_PARAMETER_CLASS=family,K7658_PORT_PAYLOAD='on' if mode=='enabled' else 'off');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
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
