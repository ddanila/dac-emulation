#!/usr/bin/env python3
"""Direct native partial-vector dispatch with an independent four-state oracle."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from mux_probe import parse,validate,changed,target
HERE=Path(__file__).resolve().parent
CALLS=[(2,0,'0'),(1,70,'2301'),(2,0,'1'),(0,0,'1010'),(2,0,'3'),
       (1,0,'1010'),(2,0,'2'),(0,70,'2301'),(2,0,'0'),(0,70,'2301')]


def oracle():
    a=list('0'*80);b=list('1'*80);select='0';result=[]
    # Only these stimuli change the selected result. Equal/hidden writes and
    # X-to-Z selection produce no native output callback.
    emitted={1,3,5,6,8,9}
    for phase,(port,base,bits) in enumerate(CALLS,1):
        if port==2:select=bits
        else:(a if port==0 else b)[base:base+len(bits)]=bits
        result.append(f'PARTIAL_CALL {phase} {port} {base} {bits}')
        if phase in emitted:
            out=a if select=='0' else b if select=='1' else [x if x==y else '3' for x,y in zip(a,b)]
            result.append(f'PARTIAL_VALUE {phase*1000} '+''.join(out))
    return result


def review(root):
    receipt=json.loads((root/'run.json').read_text());trajectory=None;count=None;faults={str(i):0 for i in range(5)}
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed native partial control')
        lines=(root/(mode+'.stdout')).read_text().splitlines()
        ordinary=[l for l in lines if not l.startswith(('MXM_','VXM_'))]
        if ordinary[:-1]!=oracle() or not ordinary or '$finish called at 11000 (1ps)' not in ordinary[-1]:raise ValueError('Partial dispatch/continuation differs from oracle')
        lines=[l for l in lines if l.startswith(('MXM_','VXM_'))];cursor=0;stage=0;shots=[];pointers={}
        def consume(want):
            nonlocal cursor
            if cursor>=len(lines) or lines[cursor]!=want:raise ValueError('Expected '+want)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(lines) and not lines[cursor].startswith('VXM_END '):cursor+=1
            if cursor==len(lines):raise ValueError('Truncated partial mux state')
            cursor+=1;return parse(lines[start:cursor])
        def canonical(p):
            if p and p not in pointers:pointers[p]=len(pointers)+1
            return pointers[p] if p else 0
        while cursor<len(lines):
            consume(f'MXM_API {stage} {int(mode!="baseline")}')
            if mode in ('enabled','corrupt'):
                consume('MXM_BEFORE');before=snapshot();consume('MXM_REPEAT')
                if snapshot()!=before:raise ValueError('Observer changed mux state')
                validate(before)
                if len(before['muxes'])!=1:raise ValueError('Unexpected fixture mux')
                m=before['muxes'][0]
                if m['aWidth']!=80 or m['bWidth']!=80:raise ValueError('Lost wide vector')
                if stage==0 and (before['tick'] or before['events'] or m['pending'] or m['ran'] or m['select']!=2 or m['a']!='2'*80 or m['b']!='2'*80):raise ValueError('Wrong initial state')
                if mode=='corrupt':
                    for field in range(5):
                        if target(before,field) is None:continue
                        consume(f'MXM_CHANGED {field}');changed(before,snapshot(),field)
                        consume('MXM_RESTORED')
                        if snapshot()!=before:raise ValueError('Partial mux fault not restored')
                        consume(f'MXM_FAULT {field} 1 1');faults[str(field)]+=1
                image=copy.deepcopy(before)
                for m in image['muxes']:
                    for key in ('node','fun','event','pending'):m[key]=canonical(m[key])
                for e in image['events']:e['event']=canonical(e['event'])
                shots.append(image)
            consume(f'MXM_DONE {stage}');stage+=1
        if stage!=18:raise ValueError('Missing partial dispatch observation')
        if count is None:count=stage
        elif count!=stage:raise ValueError('Observation count differs')
        if shots:
            # Verify caches after every direct stimulus, including silent writes.
            a=list('0'*80);b=list('1'*80);sel=0
            for phase,(port,base,bits) in enumerate(CALLS,1):
                if port==2:sel=int(bits) if bits in ('0','1') else 2
                else:(a if port==0 else b)[base:base+len(bits)]=bits
                states=[s for s in shots if s['tick']==phase*1000]
                if not states:raise ValueError('Missing partial input state')
                for state in states:
                    m=state['muxes'][0]
                    if (m['a'],m['b'],m['select'])!=(''.join(a),''.join(b),sel):raise ValueError('Wrong partial cache update')
            if not any(e['region']=='executing' for s in shots for e in s['events']):raise ValueError('Missing executing wrapper')
            if trajectory is None:trajectory=shots
            elif trajectory!=shots:raise ValueError('Partial mux trajectory changed')
    if not all(faults.values()):raise ValueError('Missing native fault control')
    return dict(qualified=False,controlsPassed=True,directPartialPorts=[0,1,2],vectorWidth=80,
        outputMatchesIndependentOracle=True,normalTrajectoryExactlyEqual=True,observationsPerRun=count,
        restoredFaults=sum(faults.values()),faultsByField=faults,
        scope='Direct native recv_vec4_pv calls in original and observed runtimes; selected/unselected and unchanged partial writes, high-word X/Z data, 0/1/X/Z selection, queued/executing wrappers and exact restored faults.',
        notEstablished=['Board integration and operational budgets','Other logic families or general rollback'])


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/mux_partial_probe.'+ext),out/('probe.'+ext))
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled','corrupt'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_MUX_PROBE='off' if mode in ('baseline','disabled') else 'on' if mode=='enabled' else 'corrupt');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Native runtime changed')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('mux_partial_probe.py','mux_probe.py','fixtures/mux_partial_probe.cc','fixtures/mux_partial_probe.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed partial mux assessment')
        print('Direct native partial mux controls verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need native runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
