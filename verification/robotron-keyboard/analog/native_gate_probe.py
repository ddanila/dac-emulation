#!/usr/bin/env python3
"""Exact allocated gate caches, inversion and queued/executing ownership."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from net_probe import pointer
from mux_probe import parse as mux_parse
HERE=Path(__file__).resolve().parent


def parse(lines):
    a=lines[0].split()
    if len(a)!=3 or a[:2]!=['VGL_BEGIN','1']:raise ValueError('Invalid gate header')
    tick=int(a[2]);gates=[];events=[]
    for line in lines[1:-1]:
        a=line.split()
        if a[0]=='VGL_GATE':
            if len(a)<11 or events:raise ValueError('Invalid gate row')
            g=dict(id=int(a[1]),node=pointer(a[2]),fun=pointer(a[3]),event=pointer(a[4]),kind=int(a[5]),invert=int(a[6]),pending=pointer(a[7]),inputs=[])
            count=int(a[8])
            if g['kind'] not in range(1,6) or count!=(4 if g['kind']<4 else 1) or g['invert'] not in ((0,1) if g['kind']<4 else (-1,)):raise ValueError('Wrong gate family/fields')
            if len(a)!=9+2*count or min(g[k] for k in ('id','node','fun','event'))<=0 or (gates and g['id']<=gates[-1]['id']):raise ValueError('Invalid gate identity')
            for i in range(count):
                width=int(a[9+2*i]);bits=a[10+2*i]
                if width<=0 or len(bits)!=width or set(bits)-set('0123'):raise ValueError('Invalid gate input vector')
                g['inputs'].append(bits)
            gates.append(g)
        elif a[0]=='VXM_EVENT':events.append(line)
        else:raise ValueError('Unknown gate row')
    if tick<0 or not gates or lines[-1]!=f'VGL_END {len(gates)} {len(events)}':raise ValueError('Incomplete gate image')
    # Reuse strict wrapper grammar and identity validation without interpreting
    # gate payloads as mux state.
    rows=[f"VXM_MUX {g['id']} {hex(g['node'])} {hex(g['fun'])} {hex(g['event'])} {hex(g['pending'])} 0 0 1 0 1 0" for g in gates]
    parsed=mux_parse([f'VXM_BEGIN 1 {tick}',*rows,*events,f'VXM_END {len(gates)} {len(events)}'])
    return dict(tick=tick,gates=gates,events=parsed['events'])


def validate(state):
    keys={g['event'] for g in state['gates']}
    if any(e['event'] not in keys or e['delete'] for e in state['events']):raise ValueError('Foreign gate wrapper')
    for g in state['gates']:
        queued=[e for e in state['events'] if e['event']==g['event'] and e['region']!='executing']
        if g['pending'] not in (0,g['node']) or len(queued)!=int(bool(g['pending'])):raise ValueError('Gate pending/queue mismatch')


def fields(g):return list(range(len(g['inputs'])))+([4] if g['pending'] else [])+([5] if g['kind']<4 else [])


def changed(before,after,identity,field):
    expected=copy.deepcopy(before);g=next((g for g in expected['gates'] if g['id']==identity),None)
    if g is None or field not in fields(g):raise ValueError('Invalid gate fault target')
    if field<4:g['inputs'][field]=('0' if g['inputs'][field][0]=='1' else '1')+g['inputs'][field][1:]
    elif field==4:g['pending']=0
    else:g['invert']^=1
    if expected!=after:raise ValueError('Wrong gate fault or unrelated change')


def oracle():
    result=[]
    for phase in (1,2,4):
        for i,b in enumerate('01101001'):
            bits=b*80
            if phase==2 and i>=4:bits=b*70+'33'+b*8
            if phase==4:bits='3'*80
            result.append(f'GATE_VALUE {phase*1000} {i} {bits}')
    return result


def review(root):
    receipt=json.loads((root/'run.json').read_text());trajectory=None;faults={str(i):0 for i in range(6)};executing=set();pending=set()
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed gate control')
        lines=(root/(mode+'.stdout')).read_text().splitlines();ordinary=[l for l in lines if not l.startswith(('GGM_','VGL_','VXM_'))]
        if ordinary[:-1]!=oracle() or not ordinary or '$finish called at 5000 (1ps)' not in ordinary[-1]:raise ValueError('Gate continuation differs from oracle')
        lines=[l for l in lines if l.startswith(('GGM_','VGL_','VXM_'))];cursor=0;stage=0;shots=[];pointers={};bindings={};wrapper_bindings={}
        def consume(want):
            nonlocal cursor
            if cursor>=len(lines) or lines[cursor]!=want:raise ValueError('Expected '+want)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(lines) and not lines[cursor].startswith('VGL_END '):cursor+=1
            if cursor==len(lines):raise ValueError('Truncated gate state')
            cursor+=1;return parse(lines[start:cursor])
        def canonical(p):
            if p and p not in pointers:pointers[p]=len(pointers)+1
            return pointers[p] if p else 0
        while cursor<len(lines):
            row=lines[cursor].split();callback=int(row[-1])
            if callback not in (0,1):raise ValueError('Invalid callback marker')
            consume(f'GGM_API {stage} {int(mode!="baseline")} {callback}')
            if mode in ('enabled','corrupt'):
                consume('GGM_BEFORE');before=snapshot();consume('GGM_REPEAT')
                if snapshot()!=before:raise ValueError('Gate observer changed state')
                validate(before)
                if [(g['kind'],g['invert']) for g in before['gates']]!=[(1,0),(1,1),(2,0),(2,1),(3,0),(3,1),(4,-1),(5,-1)]:raise ValueError('Missing gate variants')
                for g in before['gates']:
                    identity=tuple(g[k] for k in ('node','fun','event','kind'))
                    if bindings.setdefault(g['id'],identity)!=identity:raise ValueError('Gate binding changed')
                    if any(len(v)!=80 for v in g['inputs']):raise ValueError('Wrong gate width')
                    if g['pending']:pending.add(g['kind'])
                    wanted=[]
                    for port in range(len(g['inputs'])):
                        bits='2'*80 if before['tick']==0 else ('0' if port==0 else '1')*80
                        if before['tick'] in (2000,3000) and port==(2 if g['kind']<4 else 0):bits=bits[:70]+'23'+bits[72:]
                        if before['tick']>=4000:bits='3'*80
                        wanted.append(bits)
                    if g['inputs']!=wanted:raise ValueError('Gate caches differ from stimulus oracle')
                    if stage==0 and (before['tick'] or before['events'] or g['pending'] or any(v!='2'*80 for v in g['inputs'])):raise ValueError('Wrong gate constructor')
                for e in before['events']:
                    if wrapper_bindings.setdefault(e['id'],e['event'])!=e['event']:raise ValueError('Gate wrapper rebound')
                    if e['region']=='executing':executing.add(next(g['kind'] for g in before['gates'] if g['event']==e['event']))
                if mode=='corrupt' and not callback:
                    for g in before['gates']:
                        for field in fields(g):
                            consume(f"GGM_CHANGED {g['id']} {field}");changed(before,snapshot(),g['id'],field)
                            consume('GGM_RESTORED')
                            if snapshot()!=before:raise ValueError('Gate fault not restored')
                            consume(f"GGM_FAULT {g['id']} {field} 1 1");faults[str(field)]+=1
                image=copy.deepcopy(before)
                for g in image['gates']:
                    for k in ('node','fun','event','pending'):g[k]=canonical(g[k])
                for e in image['events']:e['event']=canonical(e['event'])
                shots.append(image)
            consume(f'GGM_DONE {stage}');stage+=1
        if stage!=30:raise ValueError('Wrong gate observation count')
        if shots:
            if trajectory is None:trajectory=shots
            elif trajectory!=shots:raise ValueError('Gate normal trajectory changed')
    if not all(faults.values()) or pending!=set(range(1,6)) or executing!=pending:raise ValueError('Missing gate lifecycle/fault coverage')
    return dict(qualified=False,controlsPassed=True,normalTrajectoryExactlyEqual=True,outputMatchesIndependentOracle=True,
        restoredFaults=sum(faults.values()),faultsByField=faults,observationsPerRun=30,
        scope='Exact AND/NAND, OR/NOR, XOR/XNOR and BUF/NOT allocated caches, inversion and typed queued/executing wrapper associations. Direct partial input dispatch, X/Z and unchanged writes preserve original-runtime output through restored faults.',
        notEstablished=['Other cached-logic subclasses and refusal fixture qualification','Real-input conversion, unequal-width inputs and allocation lifecycle','Board integration, class admission, budgets and general rollback'])


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/gate_probe.'+ext),out/('probe.'+ext))
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled','corrupt'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_GATE_PROBE='off' if mode in ('baseline','disabled') else 'on' if mode=='enabled' else 'corrupt');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Native runtime changed')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('native_gate_probe.py','mux_probe.py','net_probe.py','fixtures/gate_probe.cc','fixtures/gate_probe.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed gate assessment')
        print('Native gate cache controls verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need native runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
