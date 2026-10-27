#!/usr/bin/env python3
"""Verify native scope and static array-storage admission before dereference."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from array_probe import parse,validate
from array_compact_probe import expand
HERE=Path(__file__).resolve().parent


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={}
    continuation='CONTINUE 3 10 00000000000000000003 10000000000000000002'
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native array admission failed')
        lines=(root/(mode+'.stdout')).read_text().splitlines();i=0;events=[]
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                key=line.split()[1];start=i
                while i<len(lines) and lines[i]!='IMAGE_END':i+=1
                if i==len(lines) or mode!='enabled' or key in images:raise ValueError('Invalid array image')
                image=lines[start:i];i+=1
                if key.startswith('compact'):image=expand(image)
                images[key]=parse(image);validate(images[key])
            else:events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        expected=[]
        for r in (1,2):
            expected.append(f'ROUND {r}')
            if mode=='enabled':expected += [f'LIFETIME {r}']+[f'REFUSED {r} {f}' for f in range(9)]
            expected.append(f'RESTORED {r}')
        if events!=expected+[continuation,'finish']:raise ValueError('Changed array admission control/continuation')
    for r in (1,2):
        before=images.get(f'before{r}')
        if not before or before['tick']!=r*1000 or len(before['arrays'])!=2:raise ValueError('Missing array baseline')
        if images.get(f'compact{r}')!=before or images.get(f'restored{r}')!=before:raise ValueError('Array restoration/reconstruction differs')
        narrow,wide=sorted(before['arrays'],key=lambda a:a['width'])
        if narrow['width']!=4 or wide['width']!=80 or narrow['words']!=['1100','0101']:raise ValueError('Changed narrow array data')
        def bits(value):return ''.join(str((value>>i)&1) for i in range(80))
        expected=[bits(3),'3'*80 if r==1 else bits(int('10000000000000000002',16))]
        if wide['words']!=expected:raise ValueError('Wide write/initial storage differs')
    if set(images)!={f'{k}{r}' for k in ('before','compact','restored') for r in (1,2)}:raise ValueError('Unexpected array images')
    return dict(qualified=False,controlsPassed=True,rounds=2,zeroOutputRefusals=36,restoredFaults=18,ordinaryWideAllocationAndWritesPreserved=True,exactDenseCompactReconstruction=True,originalContinuationExactlyEqual=True,
        scope='Scope admission precedes traversal casts; exact static storage registry guards allocation identity, width/count, cell buffers and wide A/B pointers before observer reads. Nine faults per round refuse both dense and compact images with zero bytes and restore. Placement reconstruction and destruction update admission; subclasses and foreign storage refuse. Lazy word-cache pointers, read-port heads, broader lifecycle and operational board qualification remain open.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/array_admission.{ext}',out/f'probe.{ext}')
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
