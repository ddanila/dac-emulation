#!/usr/bin/env python3
"""Validate all allocated four-state/strength-aware wire filter payloads."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from island_filter_probe import parse_snapshot as parse_strength,changed_snapshot as strength_changed
from net_probe import pointer
HERE=Path(__file__).resolve().parent


def parse(lines):
    a=lines[0].split()
    if len(a)!=3 or a[:2]!=['VWF_BEGIN','1']:raise ValueError('Invalid wire header')
    tick=int(a[2]);filters=[];i=1
    while i<len(lines) and lines[i].startswith('VWF_FILTER '):
        row=lines[i].split();i+=1
        if len(row)!=5:raise ValueError('Invalid filter identity')
        identity=int(row[1]);node=pointer(row[2]);key=pointer(row[3]);kind=int(row[4])
        if identity<=0 or node<=0 or key<=0 or kind not in (4,8) or (filters and identity<=filters[-1]['id']):raise ValueError('Invalid filter allocation')
        if i>=len(lines):raise ValueError('Missing callback heads')
        cb=lines[i].split();i+=1
        if len(cb)!=3 or cb[0]!='VWF_CALLBACKS':raise ValueError('Invalid callback heads')
        body=[]
        while i<len(lines) and not lines[i].startswith(('VWF_FILTER ','VWF_END ')):
            line=lines[i];i+=1
            if kind==4 and line.startswith('VIF_VECTOR '):
                v=line.split()
                if len(v)!=4 or int(v[2])<0 or (int(v[2])==0 and v[3]!='-') or (int(v[2])>0 and (len(v[3])!=int(v[2]) or set(v[3])-set('0123'))):raise ValueError('Invalid four-state wire vector')
                if int(v[2]):v[3]=''.join(bit+'00' for bit in v[3])
                line=' '.join(v)
            body.append(line)
        parsed=parse_strength([f'VIF_BEGIN 1 {tick}',f'VIF_PORT {identity} 1 {row[3]}',*body,'VIF_END 1'])['ports'][0]
        parsed.pop('island');parsed.pop('port')
        if kind==4:
            for v in parsed['vectors'].values():
                if v['size']:v['bits']=v['bits'][::3]
        parsed.update(id=identity,node=node,kind=kind,callbacks=pointer(cb[1]),arrayWords=pointer(cb[2]));filters.append(parsed)
    if tick<0 or not filters or lines[i:]!=[f'VWF_END {len(filters)}'] or len({f['pointer'] for f in filters})!=len(filters):raise ValueError('Incomplete/aliased wire inventory')
    return dict(tick=tick,filters=filters)


def target(snapshot,kind,field):
    for i,f in enumerate(snapshot['filters']):
        if f['kind']!=kind:continue
        if field in (0,4):return i
        if field==3 and f['mask']['size']:return i
        if field==5 and f['linkPointer']:return i
        if field in (1,2,6) and f['vectors']['forced' if field==2 else 'driven']['size']:return i
    return None


def changed(before,after,kind,field):
    i=target(before,kind,field)
    if i is None:raise ValueError('Missing wire fault target')
    expected=copy.deepcopy(before);f=expected['filters'][i]
    if field==0:f['init']^=1
    elif field==4:f['propagate']^=1
    elif field==3:f['mask']['bits']=str(int(f['mask']['bits'][0])^1)+f['mask']['bits'][1:]
    elif field==5:f['link']['destinationPort']^=1
    else:
        v=f['vectors']['forced' if field==2 else 'driven'];bits=v['bits']
        if field in (1,2):v['bits']=('0' if bits[0]=='1' else '1')+('66'+bits[3:] if kind==8 else bits[1:])
        else:
            value,s0,s1=map(int,bits[:3]);s0^=1;s1^=1
            if value==0:s1=s0
            elif value==1:s0=s1
            elif value==2:s0=s1=0
            v['bits']=str(value)+str(s0)+str(s1)+bits[3:]
    if expected!=after:raise ValueError('Wrong wire mutation or unrelated state changed')


def review(root):
    receipt=json.loads((root/'run.json').read_text());output=None;trajectory=None;faults={f'{k}:{f}':0 for k in (4,8) for f in range(6 if k==4 else 7)};coverage=set()
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode']!=0 or (root/(mode+'.stderr')).read_text():raise ValueError('Failed wire control')
        lines=(root/(mode+'.stdout')).read_text().splitlines();ordinary=[l for l in lines if not l.startswith(('VWF_','VIF_','WFM_'))]
        expected=['48 13 1248131248131248','a5 13 12a51312a51312a5','c3 35 34c33534c33534c3','6e 35 346e35346e35346e','c3 35 34c33534c33534c3','6e 35 346e35346e35346e']
        if len(ordinary)!=7 or ordinary[:6]!=[f'VALUE {(i+1)*1000} '+v for i,v in enumerate(expected)] or '$finish called at 6000 (1ps)' not in ordinary[-1]:raise ValueError('Wrong wire continuation')
        if output is None:output=ordinary
        elif output!=ordinary:raise ValueError('Wire observer changed output')
        lines=[l for l in lines if l.startswith(('VWF_','VIF_','WFM_'))];cursor=0;shots=[];pointers={}
        def consume(value):
            nonlocal cursor
            if cursor>=len(lines) or lines[cursor]!=value:raise ValueError('Expected '+value)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(lines) and not lines[cursor].startswith('VWF_END '):cursor+=1
            if cursor==len(lines):raise ValueError('Truncated wire inventory')
            cursor+=1;return parse(lines[start:cursor])
        def canonical(value):
            if value and value not in pointers:pointers[value]=len(pointers)+1
            return pointers[value] if value else 0
        for stage in range(6):
            consume(f'WFM_API {stage} {int(mode!="baseline")}')
            if mode in ('enabled','corrupt'):
                consume('WFM_BEFORE');before=snapshot();consume('WFM_REPEAT')
                if before['tick']!=(stage+1)*1000 or snapshot()!=before:raise ValueError('Wire observer changed state/time')
                for f in before['filters']:
                    coverage.add('kind-'+str(f['kind']))
                    if f['vectors']['driven']['size']>64:coverage.add('wide')
                    if f['mask']['size']:coverage.add('forced-'+str(f['kind']))
                    if f['link']:
                        coverage.add(('linked-' if f['link']['source'] else 'released-')+str(f['kind']))
                if mode=='corrupt':
                    for kind in (4,8):
                        for field in range(6 if kind==4 else 7):
                            if target(before,kind,field) is None:continue
                            consume(f'WFM_CHANGED {kind} {field}');changed(before,snapshot(),kind,field)
                            consume('WFM_RESTORED')
                            if snapshot()!=before:raise ValueError('Wire fault not restored')
                            consume(f'WFM_FAULT {kind} {field} 1 1');faults[f'{kind}:{field}']+=1
                normal=copy.deepcopy(before)
                for f in normal['filters']:
                    for k in ('node','pointer','callbacks','arrayWords','linkPointer'):f[k]=canonical(f[k])
                    if f['link']:
                        for k in ('source','destination'):f['link'][k]=canonical(f['link'][k])
                shots.append(normal)
            consume(f'WFM_DONE {stage}')
        if cursor!=len(lines):raise ValueError('Extra wire observations')
        if shots:
            if trajectory is None:trajectory=shots
            elif trajectory!=shots:raise ValueError('Wire trajectory changed')
    required={'kind-4','kind-8','wide','forced-4','forced-8','linked-4','linked-8','released-4','released-8'}
    if not required<=coverage or not all(faults.values()):raise ValueError('Missing wire payload coverage')
    return dict(qualified=False,controlsPassed=True,simulationOutputExactlyEqual=True,normalWireTrajectoryExactlyEqual=True,restoredFaults=sum(faults.values()),faultsByKindAndField=faults,coverage=sorted(coverage),
        scope='All allocated vec4/vec8 wire filters: initialized drive/force vectors, initialization and force flags/masks/links, and callback/array-word head identities. Native fields are restored before execution.',
        notEstablished=['Callback and array-word list contents','Signal functor and other payload families','Board integration and capture budgets','Raw allocation equivalence or general rollback'])


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('c','v'):shutil.copy2(HERE/('fixtures/wire_probe.'+ext),out/('probe.'+ext))
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled','corrupt'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_WIRE_PROBE='off' if mode in ('baseline','disabled') else 'on' if mode=='enabled' else 'corrupt');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Native runtime changed')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('wire_probe.py','fixtures/wire_probe.c','fixtures/wire_probe.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed graph assessment')
        print('Complete ordinary wire-filter controls and restored faults verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need native runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
