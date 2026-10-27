#!/usr/bin/env python3
"""Qualify native resolver trees with independent driver/tree expectations."""
import argparse,json,lzma,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from resolver_source_contract import layout
HERE=Path(__file__).resolve().parent
PORTS=(1,1,1,2,5,17)
PULLS=(0,0x55,0xdd,0,0x55,0xdd)
WIDTHS=(1,8,9,80)
RAW_INPUTS=(0x33,0xbb,0x55,0xdd,0x66,0xee,0x77,0xff,0x88,0x00,0x88,0x88)

from resolver_probe import parse,changed

def output_text(root,mode):
    path=root/(mode+'.stdout')
    return path.read_text() if path.exists() else lzma.open(str(path)+'.xz','rt').read()

def scalar(a,b):
    # Independent strongest-driver oracle for canonical equal-strength 0/1/X.
    # HiZ returns the other raw encoding, even when both operands are HiZ.
    if not a&0x77:return b
    if not b&0x77:return a
    for v in (a,b):
        if (v&7)!=((v>>4)&7) or v&0x88 not in (0,0x80,0x88):raise ValueError('Outside symmetric-strength oracle')
    sa,sb=a&7,b&7
    if sa!=sb:return a if sa>sb else b
    return a if a==b else (sa*17)|0x80

def resolve(values):
    active=[v for v in values if v]
    if not active:return b''
    if any(len(v)!=len(active[0]) for v in active):raise ValueError('Mismatched stimulus widths')
    out=active[0]
    for value in active[1:]:out=bytes(scalar(a,b) for a,b in zip(out,value))
    return out

def tree(leaves,pull):
    values=list(leaves);level=list(leaves)
    while len(level)>1:
        level=[resolve(level[i:i+4]) for i in range(0,len(level),4)];values.extend(level)
    if values[-1] and pull:values[-1]=bytes(scalar(b,pull) for b in values[-1])
    return values

def review(root):
    receipt=json.loads((root/'run.json').read_text());width=receipt['width'];ordinary_reference=None;faults={};observations=callbacks=0
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native resolver control failed')
        if width not in WIDTHS:raise ValueError('Unadmitted stimulus width')
        lines=output_text(root,mode).splitlines();cursor=stage=0;bindings={};leaves=[[b'']*n for n in PORTS];ordinary=[];drives=[];values=0;phase=0
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
                leaves[core][port]=bytes([0]*(width-1)+[0x66] if phase==1 else [RAW_INPUTS[phase-2]]*width)
                ordinary.append(line);cursor+=1;continue
            if line.startswith('RES_VALUE '):
                _,a,b,c=line.split();p,core=int(a),int(b)
                if p!=phase or bytes.fromhex(c)!=tree(leaves[core],PULLS[core])[-1]:raise ValueError('Output differs from independent driver resolution')
                ordinary.append(line);values+=1;cursor+=1;continue
            if '$finish called at 14000 (1ps)' in line:
                ordinary.append('finish');cursor+=1;continue
            a=line.split()
            if len(a)!=4 or a[:3]!=['RSM_API',str(stage),str(int(mode!='baseline'))] or a[3] not in ('0','1'):raise ValueError('Wrong resolver observation stage')
            callback=int(a[3]);cursor+=1
            if mode in ('enabled','corrupt'):
                consume('RSM_BEFORE');before=snapshot();consume('RSM_REPEAT')
                if snapshot()!=before:raise ValueError('Observer changed state')
                if before['tick']!=phase*1000:raise ValueError('Wrong native time')
                cores=[n for n in before['nodes'] if n['kind']==1];extensions=[n for n in before['nodes'] if n['kind']==2]
                if len(cores)!=len(PORTS) or len(extensions)!=5:raise ValueError('Incomplete resolver population')
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
        if drives!=[(p,i,j) for p in range(1,14) for i,n in enumerate(PORTS) for j in range(n)] or not values or stage!=14+values:raise ValueError('Incomplete native continuation')
        if ordinary_reference is None:ordinary_reference=ordinary
        elif ordinary_reference!=ordinary:raise ValueError('Changed original-runtime continuation')
    if set(faults)!={f'1:{f}' for f in range(7)}|{'2:0','2:1'} or not callbacks:raise ValueError('Missing field/callback controls')
    return dict(qualified=False,controlsPassed=True,width=width,outputAndCachesMatchIndependentOracle=True,originalContinuationExactlyEqual=True,observations=observations,callbackObservations=callbacks,faultsByField=faults,
        scope='Native tri/tri0/tri1 single-input root/leaf aliasing alongside 2/5/17-input cache trees. Partial-first clipped initialization, weak/pull/strong/supply raw 0/1 inputs, equal-strength conflicts, 0x00/0x88 high-impedance transitions, repeated writes and synchronous callbacks preserve independent cache/output expectations and original continuation. All native fault fields restore exactly.',
        notEstablished=['Asymmetric-strength inputs and other raw producer families','Compact strength controls and operational board integration','Freed storage or general rollback'])


def run(candidate,baseline,modules,out,width):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/resolver_strength_inputs.cc' if ext=='cc' else 'fixtures/resolver_strength_inputs.v'),out/('probe.'+ext))
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11','-DPROBE_WIDTH='+str(width),*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled','corrupt'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_RESOLVER_PROBE='off' if mode in ('baseline','disabled') else 'on' if mode=='enabled' else 'corrupt');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Native runtime changed')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(width=width,commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('resolver_strength_inputs.py','resolver_probe.py','resolver_source_contract.py','net_probe.py','fixtures/resolver_strength_inputs.cc','fixtures/resolver_strength_inputs.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


def review_all(root):
    results={str(width):review(root/('width-'+str(width))) for width in WIDTHS}
    return dict(qualified=False,controlsPassed=True,widths=list(WIDTHS),profiles=results,
                scope='Independent symmetric-strength cache/output and original-runtime continuation controls across partial-first initialization, raw HiZ changes, single-input pull aliasing and vector storage boundaries. No operational board qualification.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review_all(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed width assessment')
        print('Resolver width and single-input controls verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need native runtime paths and fresh output')
        a.out.mkdir(exist_ok=False)
        for width in WIDTHS:run(a.candidate,a.baseline,a.modules,a.out/('width-'+str(width)),width)
        (a.out/'assessment.json').write_text(json.dumps(review_all(a.out),indent=2)+'\n')
