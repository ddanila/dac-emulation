#!/usr/bin/env python3
"""Check strength triplets over the finite native constructor/resolution closure."""
import argparse,json,tempfile,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from strength_encoding_probe import review as encoding_review
HERE=Path(__file__).resolve().parent


def seed(bit,s0,s1):
    if bit==2 or s0==s1==0:return 0
    if bit==0:return s0*17
    if bit==1:return s1*17+136
    return s0+s1*16+128


def review(root):
    results={};reference=None
    with tempfile.TemporaryDirectory() as folder:
        copied=Path(folder)
        for p in root.iterdir():
            if p.is_file():shutil.copy2(p,copied/p.name)
        for mode in ('baseline','candidate'):
            lines=(root/(mode+'.stdout')).read_text().splitlines()
            switch=[l for l in lines if l.startswith('SW_')]
            (copied/(mode+'.stdout')).write_text('\n'.join(l for l in lines if not l.startswith('SW_'))+'\n')
            if reference is None:reference=switch
            elif reference!=switch:raise ValueError('Switch behavior changed')
            states={};pairs={};maps={};seen=set()
            for line in lines:
                row=line.split()
                if row[0]=='STRENGTH_STATE':states[int(row[1])]=tuple(map(int,row[2:]))
                if row[0]=='STRENGTH_RESOLVE':pairs[int(row[1]),int(row[2])]=int(row[3])
            for line in switch:
                row=line.split();a=list(map(int,row[1:]))
                if row[0]=='SW_MAP':
                    if len(a)!=9 or a[0] not in (0,1) or a[0] in maps:raise ValueError('Invalid switch map')
                    maps[a[0]]=a[1:]
                    if a[1:]!=([0,1,2,3,4,5,6,6] if a[0]==0 else [0,1,1,2,2,3,5,5]):raise ValueError('Changed pinned strength map')
                elif row[0]=='SW_RESULT':
                    if len(a)!=5:raise ValueError('Invalid switch result')
                    resistive,unknown,left,right,result=a;key=tuple(a[:4])
                    if resistive not in maps or unknown not in (0,1) or key in seen or any(v not in states for v in (left,right,result)):raise ValueError('Switch result outside closure')
                    seen.add(key);bit,s0,s1=states[right];mapping=maps[resistive]
                    transformed=seed(bit,mapping[s0],mapping[s1])
                    bit,s0,s1=states[transformed]
                    if unknown and bit==0:transformed=seed(3,s0,0)
                    elif unknown and bit==1:transformed=seed(3,0,s1)
                    if result!=pairs[left,transformed]:raise ValueError('Switch output differs from native resolution/constructor oracle')
                else:raise ValueError('Unknown switch record')
            if len(maps)!=2 or len(seen)!=4*len(states)**2:raise ValueError('Incomplete switch closure')
            results[mode]=len(seen)
        result=encoding_review(copied)
    result.update(sourceExtractedSwitchCases=results['baseline'],switchOutputsRemainInConstructorResolutionClosure=True)
    result['scope']='Pinned source-extracted resolve_ambiguous helper linked to original/candidate native scalar constructors and resolver. Both strength maps and enabled/unknown control states cover every pair in the constructor/resolution closure. Raw-byte/triplet collision remains; this is helper coverage, not native island scheduling or board qualification.'
    result['notEstablished']=['Other producers or arbitrary raw-byte states','Island branch dispatch, queues, concatenation caches and operational board integration','General rollback']
    return result


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/strength_switch.cc' if ext=='cc' else 'fixtures/strength_encoding.v'),out/('probe.'+ext))
    source=(candidate/'vvp/island_tran.cc').read_text()
    start=source.index('enum tran_state_t {');end=source.index('};',start)+2
    enum=source[start:end];start=source.index('inline vvp_vector8_t resolve_ambiguous(');end=source.index('static void push_value_through_branches',start)
    (out/'switch_fixture.h').write_text(enum+'\n'+source[start:end])
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'switch_fixture.h',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','candidate'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Native runtime changed')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('strength_switch_probe.py','strength_encoding_probe.py','fixtures/strength_switch.cc','fixtures/strength_encoding.v')}),indent=2)+'\n')
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
