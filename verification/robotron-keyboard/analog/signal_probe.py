#!/usr/bin/env python3
"""Validate initialized static signal storage independently of filtered output."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from net_probe import pointer
HERE=Path(__file__).resolve().parent


def parse(lines):
    a=lines[0].split()
    if len(a)!=3 or a[:2]!=['VSG_BEGIN','1']:raise ValueError('Invalid signal header')
    tick=int(a[2]);signals=[]
    for line in lines[1:-1]:
        a=line.split()
        if len(a)!=11 or a[0]!='VSG_SIGNAL':raise ValueError('Invalid signal record')
        n=dict(id=int(a[1]),node=pointer(a[2]),fun=pointer(a[3]),init=int(a[4]),active=int(a[5]),link=pointer(a[6]),width=int(a[7]),bits=a[8],maskWidth=int(a[9]),mask=a[10])
        if n['id']<=0 or n['node']<=0 or n['fun']<=0 or n['init'] not in (0,1) or n['active'] not in (0,1) or n['width']<=0 or n['maskWidth'] not in (0,n['width']):raise ValueError('Invalid signal fields')
        if len(n['bits'])!=n['width'] or set(n['bits'])-set('0123'):raise ValueError('Invalid signal bits')
        if (not n['maskWidth'] and n['mask']!='-') or (n['maskWidth'] and (len(n['mask'])!=n['maskWidth'] or set(n['mask'])-set('01'))):raise ValueError('Invalid assignment mask')
        if signals and signals[-1]['id']>=n['id']:raise ValueError('Unordered signal identity')
        signals.append(n)
    if tick<0 or not signals or lines[-1]!=f'VSG_END {len(signals)}' or any(len({s[k] for s in signals})!=len(signals) for k in ('node','fun')):raise ValueError('Incomplete or aliased signal inventory')
    return dict(tick=tick,signals=signals)


def target(state,field):
    for i,s in enumerate(state['signals']):
        if field in (0,1,4) or (field==2 and s['maskWidth']) or (field==3 and s['link']):return i
    return None


def changed(before,after,field):
    if field not in range(5):raise ValueError('Unknown signal fault')
    i=target(before,field)
    if i is None:raise ValueError('Missing signal fault target')
    expected=copy.deepcopy(before);s=expected['signals'][i]
    if field==0:s['init']^=1
    elif field==1:s['bits']=('0' if s['bits'][0]=='1' else '1')+s['bits'][1:]
    elif field==2:s['mask']=str(int(s['mask'][0])^1)+s['mask'][1:]
    elif field==3:s['link']=0
    else:s['active']^=1
    if expected!=after:raise ValueError('Wrong signal mutation or unrelated state changed')


def review(root):
    receipt=json.loads((root/'run.json').read_text());output=None;trajectory=None;faults={str(f):0 for f in range(5)};coverage=set()
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode']!=0 or (root/(mode+'.stderr')).read_text():raise ValueError('Failed signal control')
        lines=(root/(mode+'.stdout')).read_text().splitlines();ordinary=[l for l in lines if not l.startswith(('VSG_','SGM_'))]
        values=['xx','5a','12','34','c3','96','9a','5a','0b','xz','87','72']
        wide='0123456789abcdef0123';mixed='xz0123456789abcdefxz'
        want=[f'VALUE {i*1000} {v} '+('x'*20 if i==0 else wide if i<9 else mixed)+' xx' for i,v in enumerate(values)]
        if len(ordinary)!=13 or ordinary[:12]!=want or '$finish called at 11000 (1ps)' not in ordinary[-1]:raise ValueError('Wrong signal continuation: '+repr(ordinary))
        if output is None:output=ordinary
        elif output!=ordinary:raise ValueError('Signal observer changed output')
        lines=[l for l in lines if l.startswith(('VSG_','SGM_'))];cursor=0;shots=[];pointers={};normal=[]
        def consume(value):
            nonlocal cursor
            if cursor>=len(lines) or lines[cursor]!=value:raise ValueError('Expected '+value)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(lines) and not lines[cursor].startswith('VSG_END '):cursor+=1
            if cursor==len(lines):raise ValueError('Truncated signal inventory')
            cursor+=1;return parse(lines[start:cursor])
        def canonical(value):
            if value and value not in pointers:pointers[value]=len(pointers)+1
            return pointers[value] if value else 0
        if mode in ('enabled','corrupt'):
            consume('SGM_STARTUP');initial=snapshot();consume('SGM_STARTUP_REPEAT')
            if snapshot()!=initial or initial['tick']!=0 or not all(s['init']==1 and set(s['bits'])=={'3'} and not s['maskWidth'] and not s['link'] and not s['active'] for s in initial['signals']):raise ValueError('Wrong pre-execution signal initialization')
            consume('SGM_STARTUP_END');coverage.add('initializing')
        for stage in range(12):
            consume(f'SGM_API {stage} {int(mode!="baseline")}')
            if mode in ('enabled','corrupt'):
                consume('SGM_BEFORE');before=snapshot();consume('SGM_REPEAT')
                if before['tick']!=stage*1000 or snapshot()!=before:raise ValueError('Signal observer changed state/time')
                normal.append(before)
                for s in before['signals']:
                    if s['init']:coverage.add('initializing')
                    else:coverage.add('initialized')
                    if s['width']>64:coverage.add('wide')
                    if set(s['bits'])=={'3'}:coverage.add('unwritten-X')
                    if '2' in s['bits']:coverage.add('Z')
                    if s['maskWidth']:
                        coverage.add('partial-mask' if '0' in s['mask'] else 'full-mask')
                    if s['link']:coverage.add('assignment-link')
                if mode=='corrupt':
                    for field in range(5):
                        if target(before,field) is None:continue
                        consume(f'SGM_CHANGED {field}');changed(before,snapshot(),field)
                        consume('SGM_RESTORED')
                        if snapshot()!=before:raise ValueError('Signal fault not restored')
                        consume(f'SGM_FAULT {field} 1 1');faults[str(field)]+=1
                image=copy.deepcopy(before)
                for s in image['signals']:
                    for k in ('node','fun','link'):s[k]=canonical(s[k])
                shots.append(image)
            consume(f'SGM_DONE {stage}')
        if cursor!=len(lines):raise ValueError('Extra signal observations')
        if shots:
            assigned=[s for s in normal[2]['signals'] if s['maskWidth']]
            if len(assigned)!=1:raise ValueError('Ambiguous procedural assignment')
            identity=assigned[0]['id']
            states=[next(s for s in frame['signals'] if s['id']==identity) for frame in normal]
            if not states[2]['link'] or states[5]['link'] or states[5]['maskWidth'] or states[9]['maskWidth']:raise ValueError('Missing assignment unlink/deassign')
            if not states[4]['link'] or states[4]['link']==states[2]['link']:raise ValueError('Missing assignment-source relinking')
            coverage.add('assignment-relinked')
            if states[10]['bits']!='10100101':raise ValueError('Forced signal hides incorrect underlying storage')
            coverage.update(('deassigned','forced-unfiltered-value'))
            if trajectory is None:trajectory=shots
            elif trajectory!=shots:raise ValueError('Signal trajectory changed')
    required={'initializing','initialized','wide','unwritten-X','Z','partial-mask','full-mask','assignment-link','assignment-relinked','deassigned','forced-unfiltered-value'}
    if not required<=coverage or not all(faults.values()):raise ValueError('Missing signal state coverage')
    return dict(qualified=False,controlsPassed=True,simulationOutputExactlyEqual=True,normalSignalTrajectoryExactlyEqual=True,restoredFaults=sum(faults.values()),faultsByField=faults,coverage=sorted(coverage),
        scope='All allocated static four-state signal functors: unfiltered logical bits, assignment masks/source links and initialized flags. Faults restore actual native fields without propagation. Signal values are tested separately from forced visible output.',
        notEstablished=['Unsupported signal-family refusal qualification','Board bindings, operational integration and budgets','Callback contents, other functor payloads or general rollback'])


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('c','v'):shutil.copy2(HERE/('fixtures/signal_probe.'+ext),out/('probe.'+ext))
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled','corrupt'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_SIGNAL_PROBE='off' if mode in ('baseline','disabled') else 'on' if mode=='enabled' else 'corrupt');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Native runtime changed')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('signal_probe.py','fixtures/signal_probe.c','fixtures/signal_probe.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed graph assessment')
        print('Complete static signal controls and restored faults verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need native runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
