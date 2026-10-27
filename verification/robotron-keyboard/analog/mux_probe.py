#!/usr/bin/env python3
"""Validate allocated mux caches and queued/executing wrapper associations."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from net_probe import pointer
HERE=Path(__file__).resolve().parent

def parse(lines):
    a=lines[0].split()
    if len(a)!=3 or a[:2]!=['VXM_BEGIN','1']:raise ValueError('Invalid mux header')
    tick=int(a[2]);muxes=[];events=[]
    for line in lines[1:-1]:
        a=line.split()
        if a[0]=='VXM_MUX':
            if len(a)!=12 or events:raise ValueError('Invalid mux record')
            m=dict(id=int(a[1]),node=pointer(a[2]),fun=pointer(a[3]),event=pointer(a[4]),pending=pointer(a[5]),select=int(a[6]),ran=int(a[7]),aWidth=int(a[8]),a=a[9],bWidth=int(a[10]),b=a[11])
            if min(m[k] for k in ('id','node','fun','event'))<=0 or m['select'] not in (0,1,2) or m['ran'] not in (0,1) or (muxes and muxes[-1]['id']>=m['id']):raise ValueError('Invalid mux identity/state')
            for key in ('a','b'):
                width=m[key+'Width']
                if width<=0 or len(m[key])!=width or set(m[key])-set('0123'):raise ValueError('Invalid mux vector')
            muxes.append(m)
        elif a[0]=='VXM_EVENT':
            if len(a)!=7:raise ValueError('Invalid mux wrapper')
            e=dict(slot=int(a[1]),region=a[2],ordinal=int(a[3]),id=int(a[4]),event=pointer(a[5]),delete=int(a[6]))
            allowed={'init':-1,'final':-1,'executing':-2}
            if e['region'] in allowed:
                if e['slot']!=allowed[e['region']]:raise ValueError('Wrong wrapper region/slot')
            elif e['region'] not in ('start','active','inactive','nbassign','rwsync','rosync','del_thr') or e['slot']<0:raise ValueError('Unknown wrapper region')
            if e['ordinal']<0 or e['id']<=0 or e['event']<=0 or e['delete'] not in (0,1):raise ValueError('Invalid wrapper fields')
            events.append(e)
        else:raise ValueError('Unknown mux record')
    if tick<0 or not muxes or lines[-1]!=f'VXM_END {len(muxes)} {len(events)}':raise ValueError('Incomplete mux inventory')
    for key in ('node','fun','event'):
        if len({m[key] for m in muxes})!=len(muxes):raise ValueError('Aliased mux identity')
    if len({e['id'] for e in events})!=len(events):raise ValueError('Aliased wrapper identity')
    return dict(tick=tick,muxes=muxes,events=events)


def validate(state):
    keys={m['event'] for m in state['muxes']}
    if any(e['event'] not in keys or e['delete'] for e in state['events']):raise ValueError('Foreign/owned mux wrapper')
    for m in state['muxes']:
        queued=[e for e in state['events'] if e['event']==m['event'] and e['region']!='executing']
        if (m['pending'] not in (0,m['node'])) or len(queued)!=int(bool(m['pending'])):raise ValueError('Mux pending destination/queue mismatch')


def target(state,field):
    for i,m in enumerate(state['muxes']):
        if field in (0,1,2,3) or (field==4 and m['pending']):return i
    return None


def changed(before,after,field):
    if field not in range(5):raise ValueError('Unknown mux fault')
    i=target(before,field)
    if i is None:raise ValueError('Missing mux fault target')
    expected=copy.deepcopy(before);m=expected['muxes'][i]
    if field in (0,1):
        key='a' if field==0 else 'b';m[key]=('0' if m[key][0]=='1' else '1')+m[key][1:]
    elif field==2:m['select']=1 if m['select']==0 else 0
    elif field==3:m['ran']^=1
    else:m['pending']=0
    if expected!=after:raise ValueError('Wrong mux fault or unrelated state changed')


def review(root):
    receipt=json.loads((root/'run.json').read_text());output=None;trajectory=None;stages_expected=None;faults={str(f):0 for f in range(5)};coverage=set()
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode']!=0 or (root/(mode+'.stderr')).read_text():raise ValueError('Failed mux control')
        lines=(root/(mode+'.stdout')).read_text().splitlines();ordinary=[l for l in lines if not l.startswith(('VXM_','MXM_'))]
        wide='0123456789abcdef0123';blend='x'+'X'*14+'f'
        values=[('12',wide),('12',wide),('c3','ffffffffffffffff0123'),('XX',blend+'0123'),('X3',blend+'01zz'),('13','0123456789abcdef01zz'),('13','0123456789abcdef01zz')]
        if len(ordinary)!=8 or ordinary[:7]!=[f'VALUE {(i+1)*1000} {v} {w}' for i,(v,w) in enumerate(values)] or '$finish called at 7000 (1ps)' not in ordinary[-1]:raise ValueError('Wrong mux continuation')
        if output is None:output=ordinary
        elif output!=ordinary:raise ValueError('Mux observer changed output')
        lines=[l for l in lines if l.startswith(('VXM_','MXM_'))];cursor=0;stage=0;shots=[];pointers={};normal=[];wrapper_bindings={}
        def consume(value):
            nonlocal cursor
            if cursor>=len(lines) or lines[cursor]!=value:raise ValueError('Expected '+value)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(lines) and not lines[cursor].startswith('VXM_END '):cursor+=1
            if cursor==len(lines):raise ValueError('Truncated mux inventory')
            cursor+=1;return parse(lines[start:cursor])
        def canonical(value):
            if value and value not in pointers:pointers[value]=len(pointers)+1
            return pointers[value] if value else 0
        while cursor<len(lines):
            consume(f'MXM_API {stage} {int(mode!="baseline")}')
            if mode in ('enabled','corrupt'):
                consume('MXM_BEFORE');before=snapshot();consume('MXM_REPEAT')
                if snapshot()!=before:raise ValueError('Mux observer changed state')
                validate(before);normal.append(before)
                if stage==0:
                    if before['tick'] or before['events'] or any(m['ran'] or m['select']!=2 or m['pending'] or set(m['a']+m['b'])!={'2'} for m in before['muxes']):raise ValueError('Wrong mux constructor state')
                    coverage.add('constructor')
                for m in before['muxes']:
                    coverage.add('selected-'+str(m['select']))
                    if m['aWidth']>64:coverage.add('wide')
                    if m['pending']:coverage.add('queued')
                    else:coverage.add('idle')
                    if m['ran']:coverage.add('has-run')
                for e in before['events']:
                    if e['region']=='executing':coverage.add('executing')
                    old=wrapper_bindings.setdefault(e['id'],e['event'])
                    if old!=e['event']:raise ValueError('Wrapper lifetime changed target')
                if mode=='corrupt':
                    for field in range(5):
                        if target(before,field) is None:continue
                        consume(f'MXM_CHANGED {field}');changed(before,snapshot(),field)
                        consume('MXM_RESTORED')
                        if snapshot()!=before:raise ValueError('Mux fault not restored')
                        consume(f'MXM_FAULT {field} 1 1');faults[str(field)]+=1
                image=copy.deepcopy(before)
                for m in image['muxes']:
                    for k in ('node','fun','event','pending'):m[k]=canonical(m[k])
                for e in image['events']:e['event']=canonical(e['event'])
                shots.append(image)
            consume(f'MXM_DONE {stage}');stage+=1
        if stages_expected is None:stages_expected=stage
        elif stage!=stages_expected:raise ValueError('Changed callback/observation count')
        if shots:
            def bits(n,width=8):return ''.join(str((n>>i)&1) for i in range(width))
            hidden=[m for s in normal if s['tick']==1000 for m in s['muxes'] if m['aWidth']==8 and m['select']==0 and m['a']==bits(0x12) and m['b']==bits(0xc3) and not m['pending']]
            if not hidden:raise ValueError('Unselected input cache update not observed')
            coverage.add('unselected-cache')
            if not any(m['aWidth']==8 and m['a']==bits(0x13) for s in normal for m in s['muxes']):raise ValueError('Partial input update missing')
            coverage.add('partial-input')
            if trajectory is None:trajectory=shots
            elif trajectory!=shots:raise ValueError('Mux normal state trajectory changed')
    required={'constructor','selected-0','selected-1','selected-2','wide','queued','idle','has-run','executing','unselected-cache','partial-input'}
    if not required<=coverage or not all(faults.values()):raise ValueError('Missing mux state controls')
    return dict(qualified=False,controlsPassed=True,simulationOutputExactlyEqual=True,normalMuxTrajectoryExactlyEqual=True,observationsPerRun=stages_expected,restoredFaults=sum(faults.values()),faultsByField=faults,coverage=sorted(coverage),
        scope='Allocated MUXZ caches, selection, run history, pending destinations and properly cast queued/executing wrapper associations. Constructor, unselected changes, partial source writes, wide inputs and X/Z selection retain exact continuation; actual field faults restore before execution.',
        notEstablished=['Direct recv_vec4_pv dispatch path','Other logic or real mux payload families','Board integration, class admission and capture budgets','Raw allocation equivalence or general rollback'])


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('c','v'):shutil.copy2(HERE/('fixtures/mux_probe.'+ext),out/('probe.'+ext))
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled','corrupt'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_MUX_PROBE='off' if mode in ('baseline','disabled') else 'on' if mode=='enabled' else 'corrupt');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Native runtime changed')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('mux_probe.py','fixtures/mux_probe.c','fixtures/mux_probe.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed graph assessment')
        print('Allocated mux cache controls and restored faults verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need native runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
