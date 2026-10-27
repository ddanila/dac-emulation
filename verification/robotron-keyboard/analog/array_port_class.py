#!/usr/bin/env python3
"""Validate exact static read-port class admission with equivalent replacement controls."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from array_probe import parse,validate
from array_compact_probe import expand
HERE=Path(__file__).resolve().parent


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={}
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed native port class control')
        lines=(root/(mode+'.stdout')).read_text().splitlines();events=[];i=0
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                key=line.split()[1];start=i
                while i<len(lines) and lines[i]!='IMAGE_END':i+=1
                if i==len(lines) or mode!='enabled' or key in images:raise ValueError('Invalid image framing')
                rows=lines[start:i];i+=1
                if key.startswith(('compact','basecompact')):rows=expand(rows)
                images[key]=parse(rows);validate(images[key])
            else:events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        expected=[]
        for r in (1,2):
            if r==2:expected.append('INDEXED 5')
            expected.append(f'ROUND {r}')
            if mode=='enabled':expected.append(f'REFUSED {r}')
            expected.append(f'RESTORED {r}')
        if events!=expected+['CONTINUE 7 5 7','finish']:raise ValueError('Changed refusal or HDL continuation')
    for r in (1,2):
        before=images.get(f'before{r}');base=images.get(f'base{r}')
        if not before or not base or before['tick']!=r*1000 or len(before['arrays'])!=1 or len(before['ports'])!=1:raise ValueError('Missing native state')
        if before!=images.get(f'compact{r}') or before!=images.get(f'restored{r}') or base!=images.get(f'basecompact{r}'):raise ValueError('Incomplete restoration or reconstruction')
        expected=copy.deepcopy(before)
        if expected['ports'][0]['key']==base['ports'][0]['key']:raise ValueError('Missing real base-class replacement')
        expected['ports'][0]['key']=base['ports'][0]['key']
        if expected!=base:raise ValueError('Replacement changed other visible fields')
        row=before['arrays'][0]
        if bool(row['cache'])!=(r==2) or row['words']!=({1:['1100','0101'],2:['0011','1010']}[r]) or before['ports'][0]['address']!=r-1:raise ValueError('Missing writes, address or cache transition')
    if set(images)!={f'{k}{r}' for k in ('before','compact','base','basecompact','restored') for r in (1,2)}:raise ValueError('Unexpected images')
    return dict(qualified=False,controlsPassed=True,rounds=2,baseClassReplacements=2,zeroOutputSubclassRefusals=4,exactRestorations=4,originalContinuationExactlyEqual=True,
        scope='Exact static read-port class admission. Equivalent base-class replacements pass dense/compact inventories with only the native port address changed; derived replacements with extra state refuse before either header. Controls restore before execution, across HDL writes, read addresses and lazy cache allocation. Does not qualify arbitrary lifetime changes or full board operation.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/array_port_class.{ext}',out/f'probe.{ext}')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-ginterconnect','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'probe.vvp',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_PORT_PAYLOAD='on' if mode=='enabled' else 'off');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(exitCode=r.returncode,command=cmd,library=str(lib));r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Dependencies changed')
    (out/'build.json').write_text(json.dumps(build,indent=2)+'\n')
    (out/'run.json').write_text(json.dumps(dict(runs=runs,commands=commands,dependencies=pins),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.candidate,a.baseline,a.modules,a.out)
