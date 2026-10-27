#!/usr/bin/env python3
"""Exercise native array-cache owner destruction and same-address reconstruction."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def review(root):
    receipt=json.loads((root/'run.json').read_text());owners={}
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native cache lifecycle failed')
        events=[]
        for line in (root/(mode+'.stdout')).read_text().splitlines():
            if line.startswith('OWNER '):
                a=line.split()
                if len(a)!=6 or mode!='enabled':raise ValueError('Invalid cache owner record')
                r,cycle=int(a[1]),int(a[2]);key=(r,cycle)
                if key in owners or cycle not in (0,1) or r not in (1,2) or int(a[5])!=2+cycle:raise ValueError('Invalid owner cycle')
                owners[key]=(int(a[3],16),int(a[4],16))
                if min(owners[key])<=0:raise ValueError('Invalid owner/cache pointer')
                events.append(f'OWNER {r} {cycle}')
            else:events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        expected=[]
        for r in (1,2):
            expected.append(f'ROUND {r}')
            if mode=='enabled':expected += [f'OWNER {r} 0',f'REFUSED {r} 0 3',f'STALE {r}',f'OWNER {r} 1',f'REFUSED {r} 1 3']
            expected.append(f'RESTORED {r}')
        if events!=expected+['CONTINUE 1','finish']:raise ValueError('Missing lifecycle refusal or changed continuation')
    if set(owners)!={(r,c) for r in (1,2) for c in (0,1)}:raise ValueError('Missing owner construction')
    for r in (1,2):
        if owners[r,0][0]!=owners[r,1][0] or owners[r,0][1]==owners[r,1][1]:raise ValueError('Missing same-address owner or distinct live cache')
    return dict(qualified=False,controlsPassed=True,rounds=2,ownerConstructions=4,sameAddressReconstructions=2,staleCacheRefusals=2,otherRefusals=12,originalContinuationExactlyEqual=True,
        scope='Test-owned concrete adapters use native __vpiArrayBase constructor, lazy allocator and destructor at the same address. New owners start unallocated; retained old cache pointers, foreign buffers, wrong lengths and cross-owner cache aliases refuse. Native cache parent/word links initialize correctly. This isolates base cache-owner lifecycle; it does not qualify deletion/reuse of scope-registered __vpiArray memories, aliases or operational board behavior.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/array_cache_lifecycle.{ext}',out/f'probe.{ext}')
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
