#!/usr/bin/env python3
"""Check strength triplets over the finite native constructor/resolution closure."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def seed(bit,s0,s1):
    if bit==2 or s0==s1==0:return 0
    if bit==0:return s0*17
    if bit==1:return s1*17+136
    return s0+s1*16+128


def review(root):
    receipt=json.loads((root/'run.json').read_text());reference=None;result=None
    for mode in ('baseline','candidate'):
        lines=(root/(mode+'.stdout')).read_text().splitlines()
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text() or not lines or '$finish called at 1000 (1ps)' not in lines[-1]:raise ValueError('Failed native strength control')
        if reference is None:reference=lines
        elif lines!=reference:raise ValueError('Native strength behavior changed')
        seeds={};states={};pairs={};collisions={};done=None;phase=0
        for line in lines[:-1]:
            words=line.split();tag=words[0];a=list(map(int,words[1:]))
            if tag=='STRENGTH_SEED' and phase==0 and len(a)==4:
                key=tuple(a[:3])
                if key in seeds or a[0] not in range(4) or any(v not in range(8) for v in a[1:3]) or a[3]!=seed(*key):raise ValueError('Invalid constructor seed')
                seeds[key]=a[3]
            elif tag=='STRENGTH_STATE' and phase<=1 and len(a)==4:
                phase=1
                raw,bit,s0,s1=a
                if raw not in range(256) or raw in states or bit not in range(4) or s0 not in range(8) or s1 not in range(8):raise ValueError('Invalid native scalar')
                if (s0,s1)!=(raw&7,(raw>>4)&7):raise ValueError('Wrong native strength fields')
                expected=2 if not(raw&119) else 0 if raw&136==0 else 1 if raw&136==136 else 3
                if bit!=expected:raise ValueError('Wrong native logic value')
                states[raw]=(bit,s0,s1)
            elif tag=='STRENGTH_RESOLVE' and phase<=2 and len(a)==3:
                phase=2;key=tuple(a[:2])
                if key in pairs or any(v not in states for v in a):raise ValueError('Resolution outside observed closure')
                pairs[key]=a[2]
            elif tag=='STRENGTH_COLLISION' and phase<=3 and len(a)==4:
                phase=3;key=tuple(a[:2])
                if key in collisions or not(a[0]<a[1]) or a[0] not in states or a[1] not in states or states[a[0]]!=states[a[1]] or a[2:]!=[0,0]:raise ValueError('Invalid native equality counterexample')
                collisions[key]=a[2:]
            elif tag=='STRENGTH_DONE' and phase in (2,3) and len(a)==1:phase=4;done=a[0]
            else:raise ValueError('Unknown or out-of-order strength row')
        if len(seeds)!=256 or done!=len(states) or len(pairs)!=len(states)**2:raise ValueError('Incomplete finite strength control')
        closure=set(seeds.values())
        if not closure<=states.keys():raise ValueError('Missing constructor state')
        while True:
            new=closure|{pairs[a,b] for a in closure for b in closure}
            if new==closure:break
            closure=new
        if closure!=states.keys():raise ValueError('Unreachable extra state')
        expected={(a,b) for a in states for b in states if a<b and states[a]==states[b]}
        if set(collisions)!=expected:raise ValueError('Missing collision/equality evidence')
        if not expected:raise ValueError('Expected native encoding counterexample absent')
        result=dict(qualified=False,controlsPassed=True,originalAndCandidateExactlyEqual=True,
                    reachableScalarStates=len(states),constructorInputs=len(seeds),resolutionPairs=len(pairs),
                    tripletsInjectiveOnConstructorResolutionClosure=False,encodingLossDetected=True,
                    collisions=[dict(rawBytes=list(key),triplet=list(states[key[0]]),scalarEqual=False,vectorEqual=False) for key in sorted(collisions)],
                    scope='Native scalar constructor and binary resolve closure. Distinct reachable raw bytes can share a logical-value/strength0/strength1 triplet while native scalar and vector equality distinguish them. Triplets are insufficient for exact cache-state evidence. All pairwise native resolution results remain in the enumerated closure.',
                    notEstablished=['States created by switch-strength reduction, raw-byte mutation or other producers','Concatenation payload/wrapper coverage, board reachability and general rollback'])
    return result


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/strength_encoding.'+ext),out/('probe.'+ext))
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','candidate'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Native runtime changed')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('strength_encoding_probe.py','fixtures/strength_encoding.cc','fixtures/strength_encoding.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
