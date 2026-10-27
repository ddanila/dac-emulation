#!/usr/bin/env python3
"""Native mux allocation growth after an immutable delta reference."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from mux_probe import parse,validate,changed,target
HERE=Path(__file__).resolve().parent
def oracle():
    return ['GROW_ALLOC 0 8','GROW_ALLOC 1 3','GROW_VALUE 1000 3 000',
            'GROW_ALLOC 2 80','GROW_VALUE 2000 80 '+'0'*80,
            'GROW_VALUE 3000 3 030','GROW_VALUE 3000 80 '+'0'*70+'21'+'0'*8,
            'GROW_VALUE 4000 3 111','GROW_VALUE 4000 80 '+'1'*80]


def dense_review(root):
    receipt=json.loads((root/'run.json').read_text());trajectory=None;count=None;faults={str(i):0 for i in range(5)};new_faults=set()
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed native growth control')
        lines=(root/(mode+'.stdout')).read_text().splitlines()
        ordinary=[l for l in lines if not l.startswith(('MXM_','VXM_'))]
        if ordinary[:-1]!=oracle() or not ordinary or '$finish called at 5000 (1ps)' not in ordinary[-1]:raise ValueError('Growth continuation differs from oracle')
        lines=[l for l in lines if l.startswith(('MXM_','VXM_'))];cursor=0;stage=0;shots=[];pointers={};bindings={};wrapper_bindings={}
        def consume(want):
            nonlocal cursor
            if cursor>=len(lines) or lines[cursor]!=want:raise ValueError('Expected '+want)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(lines) and not lines[cursor].startswith('VXM_END '):cursor+=1
            if cursor==len(lines):raise ValueError('Truncated growing mux state')
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
                for item in before['muxes']:
                    identity=tuple(item[k] for k in ('node','fun','event','aWidth','bWidth'))
                    if bindings.setdefault(item['id'],identity)!=identity:raise ValueError('Live mux binding changed')
                for event in before['events']:
                    if wrapper_bindings.setdefault(event['id'],event['event'])!=event['event']:raise ValueError('Live wrapper target changed')
                if [m['aWidth'] for m in before['muxes']] not in ([8],[8,3],[8,3,80]):raise ValueError('Unexpected allocation order')
                m=before['muxes'][0]
                if any(m['aWidth']!=m['bWidth'] for m in before['muxes']):raise ValueError('Unequal cache widths')
                if stage==0 and (before['tick'] or before['events'] or m['pending'] or m['ran'] or m['select']!=2 or m['a']!='2'*8 or m['b']!='2'*8):raise ValueError('Wrong initial state')
                if mode=='corrupt':
                    for field in range(5):
                        if target(before,field) is None:continue
                        consume(f'MXM_CHANGED {field}');changed(before,snapshot(),field)
                        consume('MXM_RESTORED')
                        if snapshot()!=before:raise ValueError('Growing mux fault not restored')
                        consume(f'MXM_FAULT {field} 1 1');faults[str(field)]+=1
                        if field==4:new_faults.add(before['muxes'][target(before,field)]['aWidth'])
                image=copy.deepcopy(before)
                for m in image['muxes']:
                    for key in ('node','fun','event','pending'):m[key]=canonical(m[key])
                for e in image['events']:e['event']=canonical(e['event'])
                shots.append(image)
            consume(f'MXM_DONE {stage}');stage+=1
        if stage!=14:raise ValueError('Missing growth observation')
        if count is None:count=stage
        elif count!=stage:raise ValueError('Observation count differs')
        if shots:
            sizes=[len(s['muxes']) for s in shots]
            if sizes!=sorted(sizes) or set(sizes)!={1,2,3}:raise ValueError('Missing native allocation growth')
            for size,width in [(2,3),(3,80)]:
                state=next(s for s in shots if len(s['muxes'])==size);m=state['muxes'][-1]
                if m['a']!='2'*width or m['b']!='2'*width or m['ran'] or m['pending'] or m['select']!=2:raise ValueError('New mux constructor not observed')
                active=[s for s in shots if len(s['muxes'])>=size and s['muxes'][size-1]['pending']]
                if not active:raise ValueError('New mux never queued')
                key=m['event']
                if not any(e['event']==key and e['region']=='executing' for s in shots for e in s['events']):raise ValueError('New mux never executing')
            last=shots[-1]
            if last['tick']!=5000 or last['events'] or any(m['pending'] for m in last['muxes']):raise ValueError('Wrappers did not drain')
            for m,width,a in zip(last['muxes'][1:],[3,80],['030','0'*70+'21'+'0'*8]):
                if (m['a'],m['b'],m['select'])!=(a,'1'*width,1):raise ValueError('New mux caches lost')
            if trajectory is None:trajectory=shots
            elif trajectory!=shots:raise ValueError('Growing mux trajectory changed')
    if not all(faults.values()) or new_faults!={3,80}:raise ValueError('Missing native growth fault control')
    return dict(qualified=False,controlsPassed=True,nativeAllocationGrowth=[1,2,3],newMuxPendingFaultWidths=sorted(new_faults),
        outputMatchesIndependentOracle=True,normalTrajectoryExactlyEqual=True,observationsPerRun=count,
        restoredFaults=sum(faults.values()),faultsByField=faults,
        scope='Native muxes allocated after the fixed delta reference, with constructor, queued, executing, drained and partial-write cache states; exact original-runtime continuation and restored faults.',
        notEstablished=['Board integration and operational allocation growth','Mux deletion, freed storage or general rollback'])


def review(root):
    import tempfile
    from mux_delta_probe import separate
    count=0
    with tempfile.TemporaryDirectory() as folder:
        copied=Path(folder)
        for p in root.iterdir():
            if p.is_file():shutil.copy2(p,copied/p.name)
        for p in copied.glob('*.stdout'):
            lines,n,_,_,_=separate(p.read_text().splitlines());count+=n
            p.write_text('\n'.join(lines)+'\n' if lines else '')
        result=dense_review(copied)
    if not count:raise ValueError('Missing growth reconstruction')
    result.update(denseAndDeltaExactlyEqual=True,matchedSnapshots=count)
    return result


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/mux_growth_probe.'+ext),out/('probe.'+ext))
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
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('mux_growth_probe.py','mux_probe.py','mux_delta_probe.py','fixtures/mux_growth_probe.cc','fixtures/mux_growth_probe.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed mux growth assessment')
        print('Native mux allocation growth and exact reconstruction verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need native runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
