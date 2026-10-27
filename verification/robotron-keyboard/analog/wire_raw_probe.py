#!/usr/bin/env python3
"""Observe exact vec8 cache bytes and faults invisible to legacy strength triplets."""
import argparse,copy,json,os,platform,re,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from net_probe import pointer
from wire_probe import parse as legacy_parse
from strength_encoding_probe import seed
HERE=Path(__file__).resolve().parent
WIDTHS=(1,8,9,80)


def triplet(raw):
    bit=2 if not raw&119 else 0 if raw&136==0 else 1 if raw&136==136 else 3
    return f'{bit}{raw&7}{(raw>>4)&7}'


def parse(lines):
    a=lines[0].split()
    if len(a)!=3 or a[:2]!=['VWB_BEGIN','1']:raise ValueError('Invalid raw-wire header')
    tick=int(a[2]);filters=[]
    for line in lines[1:-1]:
        a=line.split()
        if len(a)!=8 or a[0]!='VWB_FILTER':raise ValueError('Invalid raw-wire row')
        f=dict(id=int(a[1]),node=pointer(a[2]),pointer=pointer(a[3]),vectors=[])
        if min(f[k] for k in ('id','node','pointer'))<=0:raise ValueError('Invalid raw-wire identity')
        for col in (4,6):
            width=int(a[col]);value=a[col+1]
            if width<0 or (not width and value!='-') or (width and (len(value)!=2*width or not re.fullmatch('[0-9a-f]+',value))):raise ValueError('Invalid raw vector')
            f['vectors'].append(bytes.fromhex(value) if width else b'')
        if filters and f['id']<=filters[-1]['id']:raise ValueError('Unordered raw-wire identity')
        filters.append(f)
    if tick<0 or not filters or lines[-1]!=f'VWB_END {len(filters)}':raise ValueError('Incomplete raw inventory')
    for k in ('node','pointer'):
        if len({f[k] for f in filters})!=len(filters):raise ValueError('Aliased raw wire')
    return dict(tick=tick,filters=filters)


def expected(stage,width):
    if stage==0:return [bytes(width),b'']
    if stage==1:return [bytes(width-1)+b'\x88',bytes(width)]
    value=bytes(seed(j%4,3,5) for j in range(width))
    return [value,b'\x88'+value[1:]]


def changed(before,after,identity,field):
    result=copy.deepcopy(before);f=next(f for f in result['filters'] if f['id']==identity)
    vector=bytearray(f['vectors'][field]);index=next(i for i,b in enumerate(vector) if b in (0,136));vector[index]^=136;f['vectors'][field]=bytes(vector)
    if result!=after:raise ValueError('Wrong raw-byte fault or unrelated change')


def review(root):
    receipt=json.loads((root/'run.json').read_text());trajectory=None;faults=0
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed raw-wire native control')
        lines=(root/(mode+'.stdout')).read_text().splitlines();ordinary=[l for l in lines if l.startswith('WIRE_RAW_VALUE ') or '$finish' in l]
        wanted=[f"WIRE_RAW_VALUE {stage} {i} {expected(stage,w)[0 if stage==0 else 1].hex()}" for stage in range(3) for i,w in enumerate(WIDTHS)]
        if ordinary[:-1]!=wanted or len(ordinary)!=13 or '$finish called at 3000 (1ps)' not in ordinary[-1]:raise ValueError('Changed raw-wire continuation')
        lines=[l for l in lines if not l.startswith('WIRE_RAW_VALUE ') and '$finish' not in l];cursor=0;shots=[];bindings={}
        def consume(want):
            nonlocal cursor
            if cursor>=len(lines) or lines[cursor]!=want:raise ValueError('Expected '+want)
            cursor+=1
        def snapshot(prefix,parser):
            nonlocal cursor
            start=cursor
            while cursor<len(lines) and not lines[cursor].startswith(prefix+'_END '):cursor+=1
            if cursor==len(lines):raise ValueError('Incomplete snapshot')
            cursor+=1;return parser(lines[start:cursor])
        for stage in range(3):
            consume(f'WBR_STAGE {stage}')
            if mode in ('enabled','corrupt'):
                consume('WBR_BEFORE');before=snapshot('VWB',parse);consume('WBR_LEGACY');old=snapshot('VWF',legacy_parse)
                if before['tick']!=stage*1000 or old['tick']!=before['tick'] or len(before['filters'])!=4 or len(old['filters'])!=4:raise ValueError('Wrong raw-wire population/time')
                for i,(f,prior) in enumerate(zip(before['filters'],old['filters'])):
                    identity=(f['node'],f['pointer'])
                    if bindings.setdefault(f['id'],identity)!=identity:raise ValueError('Raw wire rebound')
                    if (f['id'],*identity)!=(prior['id'],prior['node'],prior['pointer']) or prior['kind']!=8:raise ValueError('Wrong legacy/raw binding')
                    if f['vectors']!=expected(stage,WIDTHS[i]):raise ValueError('Raw cache differs from stimulus')
                    for vector,name in zip(f['vectors'],('driven','forced')):
                        if prior['vectors'][name]['bits']!=(''.join(map(triplet,vector)) if vector else '-'):raise ValueError('Raw/legacy triplets disagree')
                    if mode=='corrupt':
                        for field,vector in enumerate(f['vectors']):
                            if not any(b in (0,136) for b in vector):continue
                            consume(f"WBR_CHANGED {f['id']} {field}");changed(before,snapshot('VWB',parse),f['id'],field)
                            consume('WBR_RESTORED')
                            if snapshot('VWB',parse)!=before:raise ValueError('Raw fault not restored')
                            consume(f"WBR_COLLISION {f['id']} {field} 1 1");faults+=1
                shots.append([[v.hex() for v in f['vectors']] for f in before['filters']])
            consume(f'WBR_DONE {stage}')
        if cursor!=len(lines):raise ValueError('Extra raw-wire records')
        if shots:
            if trajectory is None:trajectory=shots
            elif trajectory!=shots:raise ValueError('Raw-wire trajectory changed')
    if not faults:raise ValueError('Missing collision faults')
    return dict(qualified=False,controlsPassed=True,rawCacheBytesObserved=True,legacyTripletCollisionDetected=True,restoredFaults=faults,
        originalAndCandidateOutputExactlyEqual=True,widths=list(WIDTHS),
        scope='Exact driven/forced vec8 wire cache bytes, including 0x00/0x88 collisions invisible to legacy triplets; restored faults and native continuation at inline/heap widths. Existing legacy observations are cross-bound to raw records.',
        notEstablished=['Raw strength state in other payload families and unsupported filter subclasses','Compact encoding, operational board integration and general rollback'])


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('cc','v'):shutil.copy2(HERE/('fixtures/wire_raw_probe.'+ext),out/('probe.'+ext))
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled','corrupt'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_WIRE_RAW='off' if mode in ('baseline','disabled') else 'on' if mode=='enabled' else 'corrupt');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Native runtime changed')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('wire_raw_probe.py','net_probe.py','fixtures/wire_raw_probe.cc','fixtures/wire_raw_probe.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed gate assessment')
        print('Native wire_raw cache controls verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need native runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
