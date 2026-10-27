#!/usr/bin/env python3
"""Verify native scope and static array-storage admission before dereference."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from array_probe import parse,validate
from array_compact_probe import expand
HERE=Path(__file__).resolve().parent


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={}
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native array cache control failed')
        lines=(root/(mode+'.stdout')).read_text().splitlines();i=0;events=[]
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                key=line.split()[1];start=i
                while i<len(lines) and lines[i]!='IMAGE_END':i+=1
                if i==len(lines) or mode!='enabled' or key in images:raise ValueError('Invalid cache image')
                image=lines[start:i];i+=1
                if key.startswith('compact'):image=expand(image)
                images[key]=parse(image);validate(images[key])
            else:events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        expected=[]
        for r in (1,2):
            expected.append(f'ROUND {r}')
            if mode=='enabled':expected += [f'REFUSED {r} {f}' for f in range(4)]
            expected.append(f'RESTORED {r}')
        if events!=expected+['CONTINUE 3 10','finish']:raise ValueError('Changed cache refusal or continuation')
    for r in (1,2):
        before=images.get(f'before{r}');ready=images.get(f'ready{r}')
        if not before or not ready or before['tick']!=r*1000 or len(before['arrays'])!=1:raise ValueError('Missing cache baseline')
        if images.get(f'compact{r}')!=ready or images.get(f'restored{r}')!=ready:raise ValueError('Cache reconstruction/restoration differs')
        row=before['arrays'][0];after=ready['arrays'][0]
        if bool(row['cache'])!=(r==2) or not after['cache'] or row['words']!=['1100','0101']:raise ValueError('Missing lazy allocation or changed data')
        expected=copy.deepcopy(before)
        for k in ('cache','cacheParent','cacheWords'):expected['arrays'][0][k]=after[k]
        if expected!=ready or (r==2 and before!=ready):raise ValueError('Cache creation changed unrelated state')
    if set(images)!={f'{k}{r}' for k in ('before','ready','compact','restored') for r in (1,2)}:raise ValueError('Unexpected cache image')
    return dict(qualified=False,controlsPassed=True,rounds=2,zeroOutputRefusals=16,restoredFaults=8,lazyAllocationPreserved=True,observerDoesNotAllocateCache=True,exactDenseCompactReconstruction=True,originalContinuationExactlyEqual=True,
        scope='Registered word-cache allocation and length checked before reading cached entries. Foreign/shifted/missing cache bases and foreign read-port heads refuse both dense and compact output before headers, then restore exactly. Explicit VPI indexing creates the cache once; observing it does not allocate. Existing raw cache-parent/word links remain observable. Cache-owner lifecycle, aliases/subclasses and operational integration remain unqualified.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/array_cache_admission.{ext}',out/f'probe.{ext}')
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
