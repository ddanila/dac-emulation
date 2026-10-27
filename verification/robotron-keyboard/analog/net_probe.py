#!/usr/bin/env python3
"""Validate allocated native nodes, tagged links and restored graph/binding faults."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def pointer(s):return 0 if s=='(nil)' else int(s,16)

def link(s):
    a=s.split('/')
    if len(a)!=3:raise ValueError('Invalid tagged link')
    value=(pointer(a[0]),int(a[1]),int(a[2]))
    if min(value)<0 or value[2]>3:raise ValueError('Invalid link fields')
    return value


def parse(lines):
    head=lines[0].split()
    if len(head)!=4 or head[:2]!=['VNG_BEGIN','1']:raise ValueError('Invalid graph header')
    tick,count=map(int,head[2:]);nodes=[]
    for line in lines[1:-1]:
        a=line.split()
        if len(a)!=11 or a[0]!='VNG_NODE':raise ValueError('Invalid graph row')
        node=dict(id=int(a[1]),key=pointer(a[2]),fun=pointer(a[3]),filter=pointer(a[4]),force=int(a[5]),out=link(a[6]),ports=[link(v) for v in a[7:]])
        if node['id']!=len(nodes)+1 or not node['key'] or node['force'] not in (0,1):raise ValueError('Invalid allocation identity')
        nodes.append(node)
    if tick<0 or count<=0 or len(nodes)!=count or lines[-1]!=f'VNG_END {count}' or len({n['key'] for n in nodes})!=count:raise ValueError('Incomplete or aliased allocations')
    return dict(tick=tick,nodes=nodes)


def validate(snapshot):
    nodes={n['id']:n for n in snapshot['nodes']};active=inactive=fanout=0
    for n in nodes.values():
        for key,identity,port in [n['out'],*n['ports']]:
            if not key:
                if identity or port:raise ValueError('Invalid null link')
            elif identity not in nodes or nodes[identity]['key']!=key:raise ValueError('Foreign graph target')
        if n['force']:
            if not n['fun'] or not n['ports'][3][1] or n['ports'][3][2] or n['ports'][2][2]:raise ValueError('Invalid force-helper references')
            active+=bool(n['ports'][2][1]);inactive+=not n['ports'][2][1]
        current=n['out'];seen=set()
        while current[1]:
            _,target,port=current
            if (target,port) in seen:raise ValueError('Cyclic fanout')
            seen.add((target,port));destination=nodes[target]
            if destination['force'] and port!=0:raise ValueError('Force metadata treated as fanout')
            current=destination['ports'][port]
        fanout=max(fanout,len(seen))
    return dict(active=active,inactive=inactive,maxFanout=fanout)


def target(snapshot,field):
    for i,n in enumerate(snapshot['nodes']):
        if field in (0,2,5) and n['out']!=(0,0,0):return i,None
        if field==1 and not n['force']:
            for p,v in enumerate(n['ports']):
                if v!=(0,0,0):return i,p
        if field==3 and n['fun'] and not n['force']:return i,None
        if field==4 and n['filter']:return i,None
    return None


def changed(before,after,field):
    selected=target(before,field)
    if selected is None:raise ValueError('Missing graph fault target')
    expected=copy.deepcopy(before);i,p=selected;n=expected['nodes'][i]
    if field==0:n['out']=(0,0,0)
    elif field==1:n['ports'][p]=(0,0,0)
    elif field==2:n['out']=(n['out'][0],n['out'][1],n['out'][2]^1)
    elif field==3:n['fun']=0
    elif field==4:n['filter']=0
    elif field==5:n['out']=(4,0,0)
    else:raise ValueError('Unknown graph fault')
    if expected!=after:raise ValueError('Wrong graph mutation or unrelated state changed')


def review(root):
    receipt=json.loads((root/'run.json').read_text());output=None;trajectory=None;faults={i:0 for i in range(6)};coverage=set();counts=[]
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode']!=0 or (root/(mode+'.stderr')).read_text():raise ValueError('Failed native graph control')
        lines=(root/(mode+'.stdout')).read_text().splitlines();ordinary=[l for l in lines if not l.startswith(('VNG_','VNM_'))]
        expected=['48 13 1248131248131248','a5 13 12a51312a51312a5','c3 35 34c33534c33534c3','6e 35 346e35346e35346e','c3 35 34c33534c33534c3','6e 35 346e35346e35346e']
        if len(ordinary)!=7 or ordinary[:6]!=[f'VALUE {(i+1)*1000} '+v for i,v in enumerate(expected)] or '$finish called at 6000 (1ps)' not in ordinary[-1]:raise ValueError('Missing or incorrect graph continuation')
        if output is None:output=ordinary
        elif ordinary!=output:raise ValueError('Graph observer changed full output')
        lines=[l for l in lines if l.startswith(('VNG_','VNM_'))];cursor=0;shots=[];pointers={}
        def consume(value):
            nonlocal cursor
            if cursor>=len(lines) or lines[cursor]!=value:raise ValueError('Expected '+value)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(lines) and not lines[cursor].startswith('VNG_END '):cursor+=1
            if cursor==len(lines):raise ValueError('Truncated graph snapshot')
            cursor+=1;return parse(lines[start:cursor])
        def canonical(value):
            if value and value not in pointers:pointers[value]=len(pointers)+1
            return pointers[value] if value else 0
        for stage in range(6):
            consume(f'VNM_API {stage} {int(mode!="baseline")}')
            if mode in ('enabled','corrupt'):
                consume('VNM_BEFORE');before=snapshot();result=validate(before)
                if before['tick']!=(stage+1)*1000:raise ValueError('Wrong graph observation time')
                consume('VNM_REPEAT')
                if snapshot()!=before:raise ValueError('Graph observation changed state')
                if result['active']:coverage.add('active-force-helper')
                if result['inactive']:coverage.add('released-force-helper')
                if result['maxFanout']>1:coverage.add('multiple-destinations')
                if any(not n['out'][1] for n in before['nodes']):coverage.add('no-output')
                if mode=='enabled':counts.append(len(before['nodes']))
                if mode=='corrupt':
                    for field in range(6):
                        if target(before,field) is None:continue
                        consume(f'VNM_CHANGED {field}');changed(before,snapshot(),field)
                        consume('VNM_RESTORED')
                        if snapshot()!=before:raise ValueError('Graph fault not restored')
                        consume(f'VNM_FAULT {field} 1 1');faults[field]+=1
                normal=copy.deepcopy(before)
                for n in normal['nodes']:
                    for k in ('key','fun','filter'):n[k]=canonical(n[k])
                    n['out']=(canonical(n['out'][0]),*n['out'][1:])
                    n['ports']=[(canonical(v[0]),*v[1:]) for v in n['ports']]
                shots.append(normal)
            consume(f'VNM_DONE {stage}')
        if cursor!=len(lines):raise ValueError('Extra graph observations')
        if shots:
            if trajectory is None:trajectory=shots
            elif shots!=trajectory:raise ValueError('Graph trajectory changed')
    if not all(faults.values()) or coverage!={'active-force-helper','released-force-helper','multiple-destinations','no-output'} or counts[1]<=counts[0] or len(set(counts[1:]))!=1:raise ValueError('Missing graph allocation/link coverage')
    return dict(qualified=False,controlsPassed=True,simulationOutputExactlyEqual=True,normalGraphTrajectoryExactlyEqual=True,restoredFaults=sum(faults.values()),faultsByField=faults,coverage=sorted(coverage),allocatedNodesByStage=counts,
        scope='Every handed-out native net allocation, functor/filter binding and tagged output/port link; force-helper creation/reuse/release and restored graph faults. Unknown targets are serialized without dereferencing them.',
        notEstablished=['Functor/filter payload contents and callback state','Board integration and capture/review budgets','Freed storage or general rollback'])


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('c','v'):shutil.copy2(HERE/('fixtures/net_probe.'+ext),out/('probe.'+ext))
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled','corrupt'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_NET_PROBE='off' if mode in ('baseline','disabled') else 'on' if mode=='enabled' else 'corrupt');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Native runtime changed')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('net_probe.py','fixtures/net_probe.c','fixtures/net_probe.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed graph assessment')
        print('Allocated graph controls and restored faults verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need native runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
