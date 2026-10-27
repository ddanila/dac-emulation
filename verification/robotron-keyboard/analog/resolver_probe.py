#!/usr/bin/env python3
"""Qualify native resolver trees with independent driver/tree expectations."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from net_probe import pointer
from resolver_source_contract import layout
HERE=Path(__file__).resolve().parent
PORTS=(2,5,17)
PULLS=(0,0x55,0xdd)

def parse(lines):
    h=lines[0].split()
    if len(h)!=3 or h[:2]!=['VRS_BEGIN','1']:raise ValueError('Invalid resolver header')
    nodes=[];i=1
    while i<len(lines)-1:
        a=lines[i].split();i+=1
        if len(a)<5 or a[0]!='VRS_NODE':raise ValueError('Invalid resolver node')
        n=dict(id=int(a[1]),node=pointer(a[2]),fun=pointer(a[3]),kind=int(a[4]))
        if min(n[k] for k in ('id','node','fun'))<=0 or nodes and n['id']<=nodes[-1]['id']:raise ValueError('Invalid resolver identity')
        if n['kind']==1:
            if len(a)!=11:raise ValueError('Invalid core row')
            n.update(ports=int(a[5]),output=pointer(a[6]),values=pointer(a[7]),allocation=pointer(a[8]),slots=int(a[9]),pull=int(a[10],16),vectors=[])
            if min(n['ports'],n['slots'])<0 or not 0<=n['pull']<=255 or not n['allocation']:raise ValueError('Invalid allocation shape')
            for index in range(n['slots']):
                b=lines[i].split();i+=1
                if len(b)!=4 or b[:2]!=['VRS_SLOT',str(index)]:raise ValueError('Missing cache slot')
                bits=b'' if b[3]=='-' else bytes.fromhex(b[3])
                if int(b[2])!=len(bits):raise ValueError('Invalid cache width')
                n['vectors'].append(bits)
        elif n['kind']==2:
            if len(a)!=7:raise ValueError('Invalid extension row')
            n.update(core=pointer(a[5]),base=int(a[6]))
            if n['base']<0:raise ValueError('Invalid port base')
        else:raise ValueError('Unknown resolver family')
        nodes.append(n)
    if int(h[2])<0 or lines[-1]!=f'VRS_END {len(nodes)}':raise ValueError('Incomplete resolver frame')
    for key in ('node','fun'):
        if len({n[key] for n in nodes})!=len(nodes):raise ValueError('Aliased resolver identity')
    return dict(tick=int(h[2]),nodes=nodes)

def changed(before,after,identity,field,index):
    expected=copy.deepcopy(before);n=next(n for n in expected['nodes'] if n['id']==identity)
    if n['kind']==2:
        if index or field not in (0,1):raise ValueError('Invalid extension fault')
        if field==0:n['core']=0
        else:n['base']^=1
    elif field in (0,1,6):
        value=bytearray(n['vectors'][index])
        if field==0:value[0]=0x66 if value[0]==0xee else 0xee
        elif field==1:value=bytearray(len(value)+1)
        else:
            j=next(j for j,b in enumerate(value) if b in (0,136));value[j]^=136
        n['vectors'][index]=bytes(value)
    elif field==2:n['ports']^=1
    elif field==3:n['output']=0
    elif field==4:n['pull']=0xdd if n['pull']==0 else 0
    elif field==5:n['values']=0
    else:raise ValueError('Invalid resolver fault')
    if expected!=after:raise ValueError('Wrong resolver fault or unrelated state change')

def resolve(values):
    active=[v for v in values if v]
    if not active:return b''
    if any(len(v)!=9 for v in active):raise ValueError('Unexpected stimulus width')
    out=[]
    for bits in zip(*active):
        driven=set(bits)-{0}
        if driven-set((0x66,0xee,0xe6)):raise ValueError('Unmodeled stimulus strength')
        out.append(0 if not driven else next(iter(driven)) if len(driven)==1 else 0xe6)
    return bytes(out)

def tree(leaves,pull):
    values=list(leaves);level=list(leaves)
    while len(level)>1:
        level=[resolve(level[i:i+4]) for i in range(0,len(level),4)];values.extend(level)
    if values[-1]:values[-1]=bytes(pull if b==0 else b for b in values[-1])
    return values

def review(root):
    receipt=json.loads((root/'run.json').read_text());ordinary_reference=None;faults={};observations=callbacks=0
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native resolver control failed')
        lines=(root/(mode+'.stdout')).read_text().splitlines();cursor=stage=0;bindings={};leaves=[[b'']*n for n in PORTS];ordinary=[];drives=[];values=0;phase=0
        def consume(want):
            nonlocal cursor
            if cursor>=len(lines) or lines[cursor]!=want:raise ValueError('Expected '+want)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(lines) and not lines[cursor].startswith('VRS_END '):cursor+=1
            if cursor==len(lines):raise ValueError('Missing resolver footer')
            cursor+=1;return parse(lines[start:cursor])
        while cursor<len(lines):
            line=lines[cursor]
            if line.startswith('RES_DRIVE '):
                _,a,b,c=line.split();phase,core,port=map(int,(a,b,c));drives.append((phase,core,port))
                leaves[core][port]=bytes([0x66]*9 if phase==1 else [0xee]*9 if phase==2 else [0]*8+[0xee] if phase==3 else [0]*9)
                ordinary.append(line);cursor+=1;continue
            if line.startswith('RES_VALUE '):
                _,a,b,c=line.split();p,core=int(a),int(b)
                if p!=phase or bytes.fromhex(c)!=tree(leaves[core],PULLS[core])[-1]:raise ValueError('Output differs from independent driver resolution')
                ordinary.append(line);values+=1;cursor+=1;continue
            if '$finish called at 6000 (1ps)' in line:
                ordinary.append('finish');cursor+=1;continue
            a=line.split()
            if len(a)!=4 or a[:3]!=['RSM_API',str(stage),str(int(mode!='baseline'))] or a[3] not in ('0','1'):raise ValueError('Wrong resolver observation stage')
            callback=int(a[3]);cursor+=1
            if mode in ('enabled','corrupt'):
                consume('RSM_BEFORE');before=snapshot();consume('RSM_REPEAT')
                if snapshot()!=before:raise ValueError('Observer changed state')
                if before['tick']!=phase*1000:raise ValueError('Wrong native time')
                cores=[n for n in before['nodes'] if n['kind']==1];extensions=[n for n in before['nodes'] if n['kind']==2]
                if len(cores)!=3 or len(extensions)!=5:raise ValueError('Incomplete resolver population')
                for i,n in enumerate(cores):
                    expected=tree(leaves[i],PULLS[i])
                    if n['ports']!=PORTS[i] or n['slots']!=layout(PORTS[i])['slots'] or n['pull']!=PULLS[i] or n['vectors']!=expected:raise ValueError('Wrong leaf/branch/root cache')
                    if n['output']!=n['node'] or n['values']!=n['allocation']:raise ValueError('Wrong resolver allocation/output binding')
                expected_ext=[(cores[i]['fun'],base) for i,nports in enumerate(PORTS) for base in range(4,nports,4)]
                if [(n['core'],n['base']) for n in extensions]!=expected_ext:raise ValueError('Wrong extension routing')
                for n in before['nodes']:
                    identity=(n['node'],n['fun'],n['kind'],n.get('allocation'))
                    if bindings.setdefault(n['id'],identity)!=identity:raise ValueError('Resolver allocation rebound')
                observations+=1;callbacks+=callback
                if mode=='corrupt' and not callback:
                    for n in before['nodes']:
                        for field in range(7 if n['kind']==1 else 2):
                            indices=range(n['slots']) if n['kind']==1 and field in (0,1,6) else [0]
                            for index in indices:
                                if n['kind']==1 and field in (0,6):
                                    v=n['vectors'][index]
                                    if not v or field==6 and not any(b in (0,136) for b in v):continue
                                consume(f"RSM_CHANGED {n['id']} {field} {index}");changed(before,snapshot(),n['id'],field,index)
                                consume('RSM_RESTORED')
                                if snapshot()!=before:raise ValueError('Resolver fault not restored')
                                consume(f"RSM_FAULT {n['id']} {field} {index} 1 1")
                                key=f"{n['kind']}:{field}";faults[key]=faults.get(key,0)+1
            consume(f'RSM_DONE {stage}');stage+=1
        if drives!=[(p,i,j) for p in range(1,6) for i,n in enumerate(PORTS) for j in range(n)] or not values or stage!=6+values:raise ValueError('Incomplete native continuation')
        if ordinary_reference is None:ordinary_reference=ordinary
        elif ordinary_reference!=ordinary:raise ValueError('Changed original-runtime continuation')
    if set(faults)!={f'1:{f}' for f in range(7)}|{'2:0','2:1'} or not callbacks:raise ValueError('Missing field/callback controls')
    return dict(qualified=False,controlsPassed=True,outputAndCachesMatchIndependentOracle=True,originalContinuationExactlyEqual=True,observations=observations,callbackObservations=callbacks,faultsByField=faults,scope='Native tri/tri0/tri1 resolver trees with 2/5/17 inputs, extended routing, strong conflicts, fresh-Z partial input replacement, repeated writes and synchronous downstream observation. Raw leaf/branch/root vectors, pull/port/output/allocation fields and extension links have restored faults. Allocation bounds remain stable under pointer/port-count corruption.',notEstablished=['Unsupported-family refusal and supported allocation growth controls','Single-input and other vector widths, additional raw input strengths and wired-logic support','Board binding, compact encoding and integration','General rollback and freed storage'])

def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/resolver_probe.'+ext),out/('probe.'+ext))
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled','corrupt'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_RESOLVER_PROBE='off' if mode in ('baseline','disabled') else 'on' if mode=='enabled' else 'corrupt');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Native runtime changed')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('resolver_probe.py','resolver_source_contract.py','net_probe.py','fixtures/resolver_probe.cc','fixtures/resolver_probe.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed gate assessment')
        print('Native resolver cache-tree controls verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need native runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
