#!/usr/bin/env python3
"""Verify native allocation growth preserves exact raw wire caches and faults."""
import argparse,copy,json,os,platform,re,shutil,subprocess,tempfile
from pathlib import Path
from ttl7406_probe import sha
from wire_raw_probe import parse,triplet,changed,expected as prior_expected
from wire_probe import parse as legacy_parse
from wire_raw_delta_probe import separate
HERE=Path(__file__).resolve().parent
WIDTHS=(1,1,8,9,80)

def expected(stage,index):
    return [bytes(1),b''] if index==0 else prior_expected(stage-1,WIDTHS[index])

def review_dense(root):
    receipt=json.loads((root/'run.json').read_text());trajectory=None;faults=0
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed raw-wire native control')
        lines=(root/(mode+'.stdout')).read_text().splitlines();ordinary=[l for l in lines if l.startswith('WIRE_RAW_VALUE ') or '$finish' in l]
        wanted=[f"WIRE_RAW_VALUE {stage} {i} {expected(stage,i)[0 if i==0 or stage<=1 else 1].hex()}" for stage in range(4) for i,w in enumerate(WIDTHS[:1] if stage==0 else WIDTHS)]
        if ordinary[:-1]!=wanted or len(ordinary)!=17 or '$finish called at 4000 (1ps)' not in ordinary[-1]:raise ValueError('Changed raw-wire continuation')
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
        for stage in range(4):
            consume(f'WBR_STAGE {stage}')
            if mode in ('enabled','corrupt'):
                consume('WBR_BEFORE');before=snapshot('VWB',parse);consume('WBR_LEGACY');old=snapshot('VWF',legacy_parse)
                if before['tick']!=stage*1000 or old['tick']!=before['tick'] or len(before['filters'])!=(1 if stage==0 else 5) or len(old['filters'])!=(1 if stage==0 else 5):raise ValueError('Wrong raw-wire population/time')
                for i,(f,prior) in enumerate(zip(before['filters'],old['filters'])):
                    identity=(f['node'],f['pointer'])
                    if bindings.setdefault(f['id'],identity)!=identity:raise ValueError('Raw wire rebound')
                    if (f['id'],*identity)!=(prior['id'],prior['node'],prior['pointer']) or prior['kind']!=8:raise ValueError('Wrong legacy/raw binding')
                    if f['vectors']!=expected(stage,i):raise ValueError('Raw cache differs from stimulus')
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
        scope='Raw wire filters allocated after an immutable compact reference: constructor caches, driven/forced bytes and hidden collision faults reconstruct exactly and restore before unchanged native continuation.',
        notEstablished=['Raw strength state in other payload families and unsupported filter subclasses','Compact encoding, operational board integration and general rollback'])


def review(root):
    count=full_bytes=delta_bytes=reference_bytes=0
    with tempfile.TemporaryDirectory() as folder:
        copied=Path(folder)
        for p in root.iterdir():
            if p.is_file():shutil.copy2(p,copied/p.name)
        for p in copied.glob('*.stdout'):
            lines,n,full,delta,reference=separate(p.read_text().splitlines())
            p.write_text('\n'.join(lines)+'\n' if lines else '')
            count+=n;full_bytes+=full;delta_bytes+=delta;reference_bytes+=reference
        result=review_dense(copied)
    if not count or min(delta_bytes,reference_bytes,full_bytes)<=0:raise ValueError('Missing raw wire delta evidence')
    result.update(denseAndDeltaExactlyEqual=True,matchedSnapshots=count,denseBytes=full_bytes,deltaBytes=delta_bytes,referenceBytes=reference_bytes)
    result['notEstablished']=['Deletion and freed-storage equivalence','Operational raw-wire board integration and other strength payloads','General rollback']
    result.update(nativePostReferenceAllocation=True,initialFilters=1,finalFilters=5)
    return result


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('cc','v'):shutil.copy2(HERE/(('fixtures/wire_raw_growth.cc' if ext=='cc' else 'fixtures/wire_raw_growth.v')),out/('probe.'+ext))
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
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('wire_raw_growth.py','wire_raw_delta_probe.py','wire_raw_probe.py','net_probe.py','fixtures/wire_raw_growth.cc','fixtures/wire_raw_growth.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed gate assessment')
        print('Raw wire deltas reconstruct exact native cache bytes.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need native runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
